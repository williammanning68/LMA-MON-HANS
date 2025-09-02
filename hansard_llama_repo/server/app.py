from fastapi import FastAPI, Query
from pydantic import BaseModel
from typing import List, Optional
import sqlite3, json
from pathlib import Path
from llama import Llama  # your implementation
import os

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "processed" / "hansard.db"

app = FastAPI(title="Hansard Retrieval-Only Chat")

class LookupResult(BaseModel):
    id: str
    date: str
    section: str
    time: str
    speaker: str
    text: str
    source: dict

class ChatRequest(BaseModel):
    question: str
    date: Optional[str] = None
    speaker: Optional[str] = None
    limit: int = 5

class ChatResponse(BaseModel):
    answers: List[LookupResult]
    summary: str

def _connect():
    return sqlite3.connect(str(DB_PATH))

def _lookup(db, speaker=None, date=None, query=None, limit=10):
    sql = """SELECT id,date,section_heading,timestamp_local,speaker_display,text,source_file,line_start,line_end,source_version
             FROM utterances u
             WHERE 1=1"""
    params = []
    if speaker:
        sql += " AND speaker_display LIKE ?"
        params.append(f"%{speaker}%")
    if date:
        sql += " AND date = ?"
        params.append(date)
    if query:
        sql += " AND rowid IN (SELECT rowid FROM utterances_fts WHERE utterances_fts MATCH ?)"
        params.append(query)
    sql += " ORDER BY date, utterance_index LIMIT ?"
    params.append(limit)
    rows = db.execute(sql, params).fetchall()
    out = []
    for rid, d, sec, t, spk, txt, sf, ls, le, sv in rows:
        out.append({
            "id": rid, "date": d, "section": sec, "time": t, "speaker": spk, "text": txt,
            "source": {"file": sf, "line_start": ls, "line_end": le, "version": sv}
        })
    return out

# Lazy global Llama (optional; only used for summary)
LLAMA = None

def _get_llama():
    global LLAMA
    if LLAMA is None:
        ckpt_dir = os.environ.get("LLAMA_CKPT_DIR")
        tok_path = os.environ.get("LLAMA_TOKENIZER_PATH")
        if not ckpt_dir or not tok_path:
            return None
        LLAMA = Llama.build(ckpt_dir=ckpt_dir, tokenizer_path=tok_path, max_seq_len=1024, max_batch_size=2)
    return LLAMA

@app.get("/lookup", response_model=List[LookupResult])
def lookup(speaker: Optional[str] = None,
           date: Optional[str] = None,
           query: Optional[str] = Query(None, description="FTS query, e.g., budget OR surplus"),
           limit: int = 10):
    db = _connect()
    try:
        return _lookup(db, speaker=speaker, date=date, query=query, limit=limit)
    finally:
        db.close()

@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    db = _connect()
    try:
        facts = _lookup(db, speaker=req.speaker, date=req.date, query=req.question, limit=req.limit)
    finally:
        db.close()

    if not facts:
        return ChatResponse(answers=[], summary="Not in dataset.")

    # Compose a strict prompt that forbids inventing facts
    llama = _get_llama()
    if llama is None:
        # No model available: return quotes only
        return ChatResponse(answers=[LookupResult(**f) for f in facts],
                            summary="(Model not configured) See verbatim quotes above.")

    system = ("You are a Hansard summarizer. Summarize ONLY from the provided quotes. "
              "Do not introduce any facts not present. Include no speculation.")
    context = "\n\n".join([f"[{i+1}] {f['speaker']} ({f['date']} {f['time']}, {f['section']}, "
                           f"{f['source']['file']} L{f['source']['line_start']}-{f['source']['line_end']}):\n"
                           f"{f['text']}" for i, f in enumerate(facts)])
    user = f"Question: {req.question}\n\nQuotes:\n{context}\n\nWrite a concise answer using only the quotes above."

    res = llama.chat_completion([
        [{"role":"system","content":system},
         {"role":"user","content":user}]
    ], temperature=0.0, top_p=1.0, max_gen_len=256)

    summary = res[0]["generation"]["content"].strip()
    return ChatResponse(answers=[LookupResult(**f) for f in facts], summary=summary)
