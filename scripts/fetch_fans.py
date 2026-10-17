import json
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx

BASE = Path(__file__).resolve().parent
SRC = BASE / "combined.json"
H = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.bilibili.com/"}

lock = threading.Lock()
done = [0]


def get(client, url, params):
    for attempt in range(4):
        try:
            r = client.get(url, params=params, timeout=15)
            if r.status_code == 412:
                time.sleep(4 * (attempt + 1)); continue
            return r.json()
        except Exception:
            time.sleep(1 + attempt)
    return {}


def fetch(client, mid):
    card = get(client, "https://api.bilibili.com/x/web-interface/card", {"mid": mid, "photo": "false"})
    time.sleep(random.uniform(0.1, 0.35))
    up = get(client, "https://api.bilibili.com/x/space/upstat", {"mid": mid})
    c = (card.get("data") or {}).get("card") or {}
    d = up.get("data") or {}
    return {
        "fans": c.get("fans"),
        "friends": c.get("attention"),
        "level": (c.get("level_info") or {}).get("current_level"),
        "views": (d.get("archive") or {}).get("view") if d else None,
        "likes": d.get("likes"),
    }


def main():
    rows = json.loads(SRC.read_text(encoding="utf-8"))
    results = [None] * len(rows)
    with httpx.Client(headers=H) as client:
        with ThreadPoolExecutor(max_workers=4) as ex:
            futs = {ex.submit(fetch, client, r["mid"]): i for i, r in enumerate(rows)}
            for fut in as_completed(futs):
                i = futs[fut]
                info = fut.result()
                results[i] = info
                with lock:
                    done[0] += 1
                    if done[0] % 50 == 0:
                        print(f"  {done[0]}/{len(rows)}")
    for r, info in zip(rows, results):
        r.update(info)
    SRC.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    ok = sum(1 for r in rows if r.get("fans") is not None)
    print(f"完成：{ok}/{len(rows)} 拿到粉丝数 -> combined.json")


if __name__ == "__main__":
    main()
