import json
import random
import sys
import time
from pathlib import Path

import httpx

BASE = Path(__file__).resolve().parent
COOKIE_FILE = BASE / "cookie.txt"
RETRY_FILE = BASE / "retry.txt"
LOG_JSON = BASE / "retry_log.json"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def load_cookie():
    raw = COOKIE_FILE.read_text(encoding="utf-8")
    return " ".join(l.strip() for l in raw.splitlines() if l.strip() and not l.strip().startswith("#"))


def get_jct(cookie):
    for part in cookie.split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            if k.strip() == "bili_jct":
                return v.strip()
    sys.exit("no bili_jct")


def unfollow(client, jct, mid):
    for attempt in range(8):
        try:
            r = client.post(
                "https://api.bilibili.com/x/relation/modify",
                data={"fid": mid, "act": "2", "re_src": "11", "csrf": jct},
                headers={"Referer": f"https://space.bilibili.com/{mid}/fans/follow"},
            )
        except httpx.HTTPError as e:
            time.sleep(5 + attempt * 3)
            continue
        if r.status_code == 412:
            time.sleep(20 * (attempt + 1))
            continue
        d = r.json()
        if d.get("code") == -352:
            wait = random.uniform(25, 45) + attempt * 10
            print(f"    -352 风控，等待 {wait:.0f}s 重试({attempt+1}/8)")
            time.sleep(wait)
            continue
        return d
    return {"code": -352, "message": "still risk-controlled"}


def main():
    cookie = load_cookie()
    jct = get_jct(cookie)
    mids = [l.strip() for l in RETRY_FILE.read_text(encoding="utf-8").splitlines() if l.strip()]
    print(f"重试 {len(mids)} 个，先等待 30s 降低风控…")
    time.sleep(30)
    headers = {"Cookie": cookie, "User-Agent": UA, "Referer": "https://www.bilibili.com/"}
    results = []
    with httpx.Client(headers=headers, timeout=20, follow_redirects=True) as client:
        for i, mid in enumerate(mids, 1):
            d = unfollow(client, jct, mid)
            ok = d.get("code") == 0
            results.append({"mid": mid, "ok": ok, "code": d.get("code")})
            print(f"[{i}/{len(mids)}] {mid} -> {'OK' if ok else '失败 '+str(d.get('code'))}")
            if i < len(mids):
                time.sleep(random.uniform(8, 16))
    LOG_JSON.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"重试完成：成功 {sum(1 for r in results if r['ok'])}/{len(results)}")


if __name__ == "__main__":
    main()
