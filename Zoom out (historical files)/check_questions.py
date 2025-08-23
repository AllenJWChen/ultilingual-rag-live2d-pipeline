import sys, json, pathlib

path = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "data/questions.jsonl")
ok = bad = 0
first_bad = None

with path.open("r", encoding="utf-8") as f:
    for i, line in enumerate(f, 1):
        rec = json.loads(line)
        n = len(rec.get("questions", []))
        if n == 11:
            ok += 1
        else:
            bad += 1
            if first_bad is None:
                first_bad = (i, n, rec.get("source"), rec.get("page"))

print(f"lines={ok+bad}, OK={ok}, BAD={bad}")
if first_bad:
    i, n, src, pg = first_bad
    print(f"example BAD line #{i}: questions={n}, source={src}, page={pg}")
