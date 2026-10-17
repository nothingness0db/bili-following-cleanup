import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
rows = json.loads((BASE / "combined.json").read_text(encoding="utf-8"))
D = BASE / "chunks_analysis"
D.mkdir(exist_ok=True)
N = 8
size = (len(rows) + N - 1) // N
for i in range(N):
    part = rows[i * size:(i + 1) * size]
    if not part:
        continue
    slim = [{
        "mid": r["mid"], "uname": r["uname"], "sign": r["sign"],
        "official": r["official"], "label": r["label"],
        "last_days": r["last_days"], "videos": r["videos"],
    } for r in part]
    (D / f"a{i:02d}.json").write_text(json.dumps(slim, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"a{i:02d}.json {len(part)}")
