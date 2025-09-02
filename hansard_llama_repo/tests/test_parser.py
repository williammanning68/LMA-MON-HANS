from ingest.parser import parse_file
from pathlib import Path

def test_parse_smoke(tmp_path):
    sample = "[11.28 a.m.]\nELECTION OF SPEAKER\nMr ROCKLIFF (Braddon - Premier) - I move -\nThat Mrs Jacquie Petrusma do take the Chair of this House as Speaker.\nMotion agreed to.\n"
    p = tmp_path / "sample.txt"
    p.write_text(sample, encoding="utf-8")
    recs = parse_file(p, date_hint="2025-08-19", version_hint="preliminary")
    assert any(r["speech_type"]=="speech" for r in recs)
    assert any(r["speech_type"]=="procedure" for r in recs)
