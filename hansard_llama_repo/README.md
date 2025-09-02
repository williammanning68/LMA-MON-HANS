# Hansard Llama (Deterministic Parse + AI QC + Retrieval-Only Chat)

This repository ingests Hansard TXT files into strict JSONL and a SQLite database with FTS5,
runs an **optional** AI quality-check/annotation pass using your **Llama** implementation,
and serves a retrieval-only chat interface that answers **only** from the database (with citations).

## Key Design
- **Phase 1 — Deterministic parse (source of truth):** Regex/state-machine splits Hansard by headings and bracketed timestamps, extracts speakers, and records verbatim quotes with line spans.
- **Phase 2 — AI QC (optional):** Llama adds lightweight labels: `qa.is_question`, `question_type`, and potential `answer_ids`, plus warnings in `issues`. It never overwrites the raw text.
- **Server — Retrieval-only chat:** `/lookup` for programmatic queries; `/chat` to produce summaries with verbatim quotes + citations. If no rows match, the assistant replies exactly **"Not in dataset."**

## Layout
```
ingest/
  parser.py           # deterministic parser -> JSONL
  build_db.py         # JSONL -> SQLite (with FTS5)
qc/
  ai_qc.py            # optional AI labels + QC using llama
server/
  app.py              # FastAPI: /lookup, /chat
schema/
  utterance.schema.json
data/
  raw/                # drop *.txt Hansard here
  processed/          # JSONL + hansard.db
llama/                # your provided Llama files (copied)
tests/
  test_parser.py
.github/workflows/
  ci.yml
scripts/
  run_ingest.sh
requirements.txt
README.md
```

## Quickstart

1. **Install deps**
   ```bash
   python -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Put Hansard files**
   - Drop `.txt` files in `data/raw/`. For example: `data/raw/House_of_Assembly_Tuesday_19_August_2025.txt`

3. **Ingest**
   ```bash
   python -m ingest.parser --in data/raw --out data/processed/utterances.jsonl
   python -m ingest.build_db --jsonl data/processed/utterances.jsonl --db data/processed/hansard.db
   ```

4. **(Optional) AI QC + annotations**
   ```bash
   # Requires Llama checkpoints and tokenizer
   python -m qc.ai_qc      --db data/processed/hansard.db      --ckpt_dir /path/to/ckpts      --tokenizer_path /path/to/tokenizer.model
   ```

5. **Run the API**
   ```bash
   uvicorn server.app:app --reload --port 8000
   ```
   - `GET http://localhost:8000/lookup?speaker=Dean%20Winter&date=2025-08-19`
   - `POST http://localhost:8000/chat` with `{"question": "What did the Premier say about budget repair on 2025-08-19?"}`

## Guardrails
- The server always returns at least one **verbatim quote with line ranges and source file** for factual claims.
- If retrieval yields zero rows → the server answers: **"Not in dataset."**

## CI
On each push, CI runs: parse → schema-validate → build DB → basic tests. It fails on hard errors (schema violations, ordering issues).

## Credits
- Uses the Llama code you provided (see `llama/`).
