import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
rows = json.loads((BASE / "following_videos.json").read_text(encoding="utf-8"))
CHUNK_DIR = BASE / "chunks"
CHUNK_DIR.mkdir(exist_ok=True)
N = 8
size = (len(rows) + N - 1) // N
for i in range(N):
    part = rows[i * size:(i + 1) * size]
    if not part:
        continue
    (CHUNK_DIR / f"chunk_{i:02d}.json").write_text(
        json.dumps(part, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"chunk_{i:02d}.json  {len(part)} 条")
