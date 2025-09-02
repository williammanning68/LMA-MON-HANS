import argparse, json, re, sys, hashlib
from pathlib import Path
from datetime import datetime
import regex as regex_lib
from jsonschema import validate, Draft202012Validator

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schema" / "utterance.schema.json"
SCHEMA = json.loads(Path(SCHEMA_PATH).read_text())

# Patterns for headings, timestamps, speakers, and procedures
TIME_RE = re.compile(r"\[(\d{1,2})\.(\d{2})\s*(a\.m\.|p\.m\.)\]", re.IGNORECASE)
HEADING_RE = re.compile(r"^[A-Z][A-Z '’\-\u2013\u2014&]+$")  # crude but works for Hansard headings
SPEAKER_LINE_RE = re.compile(r"^([A-Z][a-z'.\- ]+)\s+\(([A-Za-z ]+)\s*-\s*([^)]+)\)\s*-\s*(.*)$")
SPEAKER_SIMPLE_RE = re.compile(r"^([A-Z][A-Za-z'.\- ]+)\s*-\s*(.*)$")
PROCEDURE_LINES = [
    "Motion agreed to.",
    "Motion negatived.",
    "The SPEAKER -",
    "The SPEAKER:",
]

def normalize_time(match):
    h, m, ap = match.groups()
    h = int(h) % 12
    if ap.lower().startswith('p'):
        h += 12
    return f"{h:02d}:{m}"

def sha256_of_text(text:str)->str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()

def parse_file(path:Path, date_hint:str=None, version_hint:str="unknown"):
    raw = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    file_hash = sha256_of_text("\n".join(raw))
    records = []
    current_heading = ""
    current_time = None
    utterance_index = 0

    # try infer date from file name if not provided
    if not date_hint:
        m = re.search(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", path.name)
        if m:
            day, mon, year = m.groups()
            try:
                dt = datetime.strptime(f"{day} {mon} {year}", "%d %B %Y")
                date_hint = dt.strftime("%Y-%m-%d")
            except:
                date_hint = None

    for ln, line in enumerate(raw, start=1):
        line_stripped = line.strip()

        # Time marker?
        t = TIME_RE.search(line_stripped)
        if t:
            current_time = normalize_time(t)
            continue

        # Heading?
        if HEADING_RE.match(line_stripped) and len(line_stripped) < 120:
            current_heading = line_stripped.title()
            continue

        # Procedure?
        if line_stripped in PROCEDURE_LINES or line_stripped.startswith("The SPEAKER"):
            rec = {
                "id": f"{path.stem}-{ln}-{ln}",
                "date": date_hint or "",
                "chamber": "House of Assembly",
                "section_heading": current_heading or "",
                "timestamp_local": current_time or "",
                "utterance_index": utterance_index,
                "speaker": {"display":"", "name": None, "electorate": None, "role": None},
                "speech_type": "procedure",
                "text": line_stripped,
                "qa": {},
                "issues": [],
                "source": {"file": path.name, "version": version_hint, "line_start": ln, "line_end": ln, "sha256": file_hash}
            }
            records.append(rec)
            utterance_index += 1
            continue

        # Speaker line or continuation?
        m = SPEAKER_LINE_RE.match(line_stripped)
        if m:
            display_name, electorate_or_div, role_or_div, remainder = m.groups()
            rec = {
                "id": f"{path.stem}-{ln}-{ln}",
                "date": date_hint or "",
                "chamber": "House of Assembly",
                "section_heading": current_heading or "",
                "timestamp_local": current_time or "",
                "utterance_index": utterance_index,
                "speaker": {"display": display_name.strip(), "name": None, "electorate": electorate_or_div.strip(), "role": role_or_div.strip()},
                "speech_type": "speech",
                "text": remainder.strip(),
                "qa": {},
                "issues": [],
                "source": {"file": path.name, "version": version_hint, "line_start": ln, "line_end": ln, "sha256": file_hash}
            }
            records.append(rec)
            utterance_index += 1
            continue

        m2 = SPEAKER_SIMPLE_RE.match(line_stripped)
        if m2:
            display_name, remainder = m2.groups()
            rec = {
                "id": f"{path.stem}-{ln}-{ln}",
                "date": date_hint or "",
                "chamber": "House of Assembly",
                "section_heading": current_heading or "",
                "timestamp_local": current_time or "",
                "utterance_index": utterance_index,
                "speaker": {"display": display_name.strip(), "name": None, "electorate": None, "role": None},
                "speech_type": "speech",
                "text": remainder.strip(),
                "qa": {},
                "issues": [],
                "source": {"file": path.name, "version": version_hint, "line_start": ln, "line_end": ln, "sha256": file_hash}
            }
            records.append(rec)
            utterance_index += 1
            continue

        # Continuation lines: append to last speech if exists and is speech
        if records and line_stripped and not HEADING_RE.match(line_stripped):
            last = records[-1]
            # Fuse into previous speech paragraph
            last["text"] = (last["text"] + " " + line_stripped).strip()
            last["source"]["line_end"] = ln

    # Validate
    validator = Draft202012Validator(SCHEMA)
    out = []
    for rec in records:
        # fill missing, basic normalizations
        if not rec["timestamp_local"]:
            rec["timestamp_local"] = "00:00"
        if not rec["date"]:
            rec["date"] = "1970-01-01"
        errors = sorted(validator.iter_errors(rec), key=lambda e: e.path)
        if errors:
            rec["issues"].extend([f"schema:{e.message}" for e in errors])
        out.append(rec)

    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="indir", required=True, help="Folder with *.txt Hansard files")
    ap.add_argument("--out", dest="outfile", required=True, help="Output JSONL path")
    ap.add_argument("--version", dest="version", default="preliminary", help="preliminary|final|unknown")
    args = ap.parse_args()

    indir = Path(args.indir)
    outfile = Path(args.outfile)
    outfile.parent.mkdir(parents=True, exist_ok=True)

    total = 0
    with outfile.open("w", encoding="utf-8") as f:
        for p in sorted(indir.glob("*.txt")):
            recs = parse_file(p, version_hint=args.version)
            for r in recs:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
                total += 1
    print(f"Wrote {total} records to {outfile}")

if __name__ == "__main__":
    main()
