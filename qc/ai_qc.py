import argparse, json, sqlite3
from pathlib import Path
from typing import List, Dict, Any
from llama import Llama  # uses your provided implementation

SYSTEM = """You label parliamentary utterances with Q&A metadata.
Rules:
- You NEVER change or paraphrase the text.
- is_question: true only if the utterance is an information-seeking question addressed to someone.
- question_type: one of ["information","rhetorical","procedural"].
- addressee_role: a role if explicitly addressed (e.g., "Premier", "Minister for Health"), else null.
- answer_ids: up to 3 following utterance IDs that likely answer this question (may be empty).
- answer_match: null|direct|partial|challenge.
- answer_confidence: 0..1.
Return strict JSON only.
"""

USER_TEMPLATE = """Date: {date}
Section: {section}
Time: {time}
Speaker: {speaker}
Text:
\"\"\"
{text}
\"\"\"

Context (next 8 utterances):
{context}

Output schema:
{{
  "is_question": <true|false>,
  "question_type": "information"|"rhetorical"|"procedural"|null,
  "addressee_role": "<role or null>",
  "answer_ids": ["<id>", ...],
  "answer_match": "direct"|"partial"|"challenge"|null,
  "answer_confidence": 0.0
}}
"""

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--ckpt_dir", required=True)
    ap.add_argument("--tokenizer_path", required=True)
    ap.add_argument("--limit", type=int, default=200)
    args = ap.parse_args()

    generator = Llama.build(
        ckpt_dir=args.ckpt_dir,
        tokenizer_path=args.tokenizer_path,
        max_seq_len=1024,
        max_batch_size=2,
    )

    db = sqlite3.connect(args.db)
    cur = db.cursor()
    rows = cur.execute("""
      SELECT id, date, section_heading, timestamp_local, speaker_display, text,
             (SELECT group_concat(id,' | ')
              FROM (SELECT id FROM utterances u2
                    WHERE u2.rowid > u.rowid
                    ORDER BY u2.rowid LIMIT 8))
      FROM utterances u ORDER BY rowid LIMIT ?
    """, (args.limit,)).fetchall()

    dialogs = []
    ids = []
    for rid, date, section, time, speaker, text, ctx in rows:
        user = USER_TEMPLATE.format(
            date=date, section=section, time=time, speaker=speaker,
            text=text, context=(ctx or ""))
        dialogs.append([{"role":"system","content":SYSTEM},
                        {"role":"user", "content": user}])
        ids.append(rid)

    results = generator.chat_completion(dialogs, temperature=0.0, top_p=1.0, max_gen_len=256)
    for (rid, res) in zip(ids, results):
        content = res["generation"]["content"].strip()
        try:
            data = json.loads(content)
        except Exception:
            # skip bad JSON
            continue
        db.execute("""INSERT OR REPLACE INTO qa_annotations
          (id,is_question,question_type,addressee_role,answer_ids,answer_match,answer_confidence)
          VALUES (?,?,?,?,?,?,?)""",
          (
            rid,
            1 if data.get("is_question") else 0,
            data.get("question_type"),
            data.get("addressee_role"),
            json.dumps(data.get("answer_ids") or []),
            data.get("answer_match"),
            float(data.get("answer_confidence") or 0.0),
          )
        )
    db.commit()
    db.close()
    print("QC annotations completed.")

if __name__ == "__main__":
    main()
