import argparse, json, sqlite3, os
from pathlib import Path

DDL = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;

CREATE TABLE IF NOT EXISTS utterances(
  id TEXT PRIMARY KEY,
  date TEXT,
  chamber TEXT,
  section_heading TEXT,
  timestamp_local TEXT,
  utterance_index INTEGER,
  speaker_display TEXT,
  speaker_name TEXT,
  speaker_electorate TEXT,
  speaker_role TEXT,
  speech_type TEXT,
  text TEXT,
  line_start INTEGER, line_end INTEGER,
  source_file TEXT,
  source_version TEXT,
  source_sha256 TEXT
);

CREATE VIRTUAL TABLE IF NOT EXISTS utterances_fts USING fts5(
  text, content='utterances', content_rowid='rowid'
);

CREATE TRIGGER IF NOT EXISTS utterances_ai AFTER INSERT ON utterances BEGIN
  INSERT INTO utterances_fts(rowid, text) VALUES (new.rowid, new.text);
END;
CREATE TRIGGER IF NOT EXISTS utterances_ad AFTER DELETE ON utterances BEGIN
  INSERT INTO utterances_fts(utterances_fts, rowid, text) VALUES ('delete', old.rowid, old.text);
END;
CREATE TRIGGER IF NOT EXISTS utterances_au AFTER UPDATE ON utterances BEGIN
  INSERT INTO utterances_fts(utterances_fts, rowid, text) VALUES ('delete', old.rowid, old.text);
  INSERT INTO utterances_fts(rowid, text) VALUES (new.rowid, new.text);
END;

CREATE TABLE IF NOT EXISTS qa_annotations(
  id TEXT PRIMARY KEY,
  is_question INTEGER,
  question_type TEXT,
  addressee_role TEXT,
  answer_ids TEXT,       -- JSON array
  answer_match TEXT,
  answer_confidence REAL
);

"""

def main():
  ap = argparse.ArgumentParser()
  ap.add_argument("--jsonl", required=True, help="JSONL from parser")
  ap.add_argument("--db", required=True, help="Output SQLite DB")
  args = ap.parse_args()

  db = sqlite3.connect(args.db)
  db.executescript(DDL)

  with open(args.jsonl, "r", encoding="utf-8") as f:
      for line in f:
          rec = json.loads(line)
          db.execute(
            """INSERT OR REPLACE INTO utterances
               (id,date,chamber,section_heading,timestamp_local,utterance_index,
                speaker_display,speaker_name,speaker_electorate,speaker_role,
                speech_type,text,line_start,line_end,source_file,source_version,source_sha256)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
              rec["id"], rec["date"], rec.get("chamber",""),
              rec.get("section_heading",""), rec.get("timestamp_local","00:00"),
              rec["utterance_index"],
              rec["speaker"].get("display",""), rec["speaker"].get("name"),
              rec["speaker"].get("electorate"), rec["speaker"].get("role"),
              rec["speech_type"], rec["text"], rec["source"]["line_start"], rec["source"]["line_end"],
              rec["source"]["file"], rec["source"]["version"], rec["source"].get("sha256")
            )
          )
  db.commit()
  db.close()
  print(f"Built DB at {args.db}")

if __name__ == "__main__":
  main()
