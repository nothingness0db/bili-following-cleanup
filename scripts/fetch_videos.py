import hashlib
import json
import random
import re
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx

BASE = Path(__file__).resolve().parent
SRC = BASE / "following.json"
OUT = BASE / "following_videos.json"
COOKIE_FILE = BASE / "cookie.txt"
PS = 6

TAB = [46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
       33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
       61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
       36, 20, 34, 44, 52]

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def load_cookie():
    raw = COOKIE_FILE.read_text(encoding="utf-8")
    return " ".join(l.strip() for l in raw.splitlines() if l.strip() and not l.strip().startswith("#"))


class Wbi:
    def __init__(self, client):
        self.client = client
        self.key = None

    def refresh(self):
        w = self.client.get("https://api.bilibili.com/x/web-interface/nav").json()["data"]["wbi_img"]
        img = w["img_url"].rsplit("/", 1)[-1].split(".")[0]
        sub = w["sub_url"].rsplit("/", 1)[-1].split(".")[0]
        self.key = "".join((img + sub)[i] for i in TAB)[:32]

    def signed(self, params):
        p = dict(params)
        p["wts"] = int(time.time())
        q = urllib.parse.urlencode(sorted(p.items()))
        p["w_rid"] = hashlib.md5((q + self.key).encode()).hexdigest()
        return p


lock = threading.Lock()
done = [0]
client = httpx.Client(
    headers={"User-Agent": UA, "Referer": "https://space.bilibili.com/", "Cookie": load_cookie()},
    timeout=20,
)
wbi = Wbi(client)
wbi.refresh()


def fetch(row):
    mid = row["mid"]
    for attempt in range(3):
        try:
            p = wbi.signed({"mid": mid, "ps": PS, "pn": 1, "order": "pubdate", "platform": "web"})
            r = client.get("https://api.bilibili.com/x/space/wbi/arc/search", params=p)
            if r.status_code == 412:
                time.sleep(5 * (attempt + 1)); continue
            d = r.json()
            if d.get("code") == -352:
                with lock:
                    wbi.refresh()
                time.sleep(1); continue
            vlist = ((d.get("data") or {}).get("list") or {}).get("vlist") or []
            return {
                "mid": mid,
                "uname": row.get("uname"),
                "sign": row.get("sign"),
                "official": row.get("official"),
                "videos": [
                    {"title": v.get("title"), "play": v.get("play"), "created": v.get("created")}
                    for v in vlist[:PS]
                ],
                "code": d.get("code"),
            }
        except Exception:
            time.sleep(1 + attempt)
    return {"mid": mid, "uname": row.get("uname"), "sign": row.get("sign"),
            "official": row.get("official"), "videos": [], "code": "failed"}


def main():
    rows = json.loads(SRC.read_text(encoding="utf-8"))
    results = [None] * len(rows)
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(fetch, r): i for i, r in enumerate(rows)}
        for fut in as_completed(futs):
            i = futs[fut]
            results[i] = fut.result()
            with lock:
                done[0] += 1
                if done[0] % 50 == 0:
                    print(f"  {done[0]}/{len(rows)}")
    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    ok = sum(1 for r in results if r.get("videos"))
    print(f"完成：{ok}/{len(rows)} 拿到投稿 -> {OUT.name}")


if __name__ == "__main__":
    main()
