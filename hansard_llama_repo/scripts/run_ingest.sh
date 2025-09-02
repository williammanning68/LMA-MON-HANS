#!/usr/bin/env bash
set -euo pipefail
python -m ingest.parser --in data/raw --out data/processed/utterances.jsonl --version preliminary
python -m ingest.build_db --jsonl data/processed/utterances.jsonl --db data/processed/hansard.db
echo "Done. DB at data/processed/hansard.db"
