import json
import random
import sys
import time
from pathlib import Path

import httpx

BASE = Path(__file__).resolve().parent
COOKIE_FILE = BASE / "cookie.txt"
SELECT_FILE = BASE / "unfollow.txt"
FOLLOWING_JSON = BASE / "following.json"
LOG_JSON = BASE / "unfollow_log.json"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


def load_cookie() -> str:
    raw = COOKIE_FILE.read_text(encoding="utf-8")
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    cookie = " ".join(lines)
    if "SESSDATA" not in cookie or "bili_jct" not in cookie:
        sys.exit("cookie.txt 里缺少 SESSDATA 或 bili_jct。")
    return cookie


def get_jct(cookie: str) -> str:
    for part in cookie.split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            if k.strip() == "bili_jct":
                return v.strip()
    sys.exit("Cookie 中找不到 bili_jct（取关需要的 csrf token）。")


def load_selection() -> list:
    if not SELECT_FILE.exists():
        sys.exit(f"缺少 {SELECT_FILE.name}，每行一个要取关的 mid。")
    mids = []
    for ln in SELECT_FILE.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if ln and not ln.startswith("#"):
            mids.append(ln)
    if not mids:
        sys.exit("unfollow.txt 为空。")
    return mids


def load_names() -> dict:
    if not FOLLOWING_JSON.exists():
        return {}
    rows = json.loads(FOLLOWING_JSON.read_text(encoding="utf-8"))
    return {str(r.get("mid")): r.get("uname") for r in rows}


def unfollow_one(client: httpx.Client, jct: str, mid: str) -> dict:
    for attempt in range(4):
        try:
            r = client.post(
                "https://api.bilibili.com/x/relation/modify",
                data={"fid": mid, "act": "2", "re_src": "11", "csrf": jct},
                headers={"Referer": f"https://space.bilibili.com/{mid}/fans/follow"},
            )
        except httpx.HTTPError as e:
            time.sleep(2 + attempt * 2)
            last = {"code": -1, "message": f"网络错误 {e}"}
            continue
        if r.status_code == 412:
            wait = 30 * (attempt + 1)
            print(f"    触发风控 412，等待 {wait}s 重试…")
            time.sleep(wait)
            last = {"code": 412, "message": "risk control"}
            continue
        try:
            data = r.json()
        except Exception:
            last = {"code": r.status_code, "message": r.text[:200]}
            continue
        return data
    return last


def main():
    cookie = load_cookie()
    jct = get_jct(cookie)
    mids = load_selection()
    names = load_names()

    print("即将取关以下账号：")
    for m in mids:
        print(f"  {m}  {names.get(m, '(未知名称)')}")
    if "--yes" not in sys.argv:
        ans = input(f"确认取关这 {len(mids)} 个账号？输入 yes 继续：").strip().lower()
        if ans != "yes":
            sys.exit("已取消。")

    headers = {"Cookie": cookie, "User-Agent": UA, "Referer": "https://www.bilibili.com/"}
    results = []
    with httpx.Client(headers=headers, timeout=20, follow_redirects=True) as client:
        for i, mid in enumerate(mids, 1):
            name = names.get(mid, "")
            data = unfollow_one(client, jct, mid)
            ok = data.get("code") == 0
            results.append({"mid": mid, "uname": name, "ok": ok, "code": data.get("code"), "message": data.get("message")})
            print(f"[{i}/{len(mids)}] {mid} {name} -> {'OK' if ok else '失败 code=' + str(data.get('code')) + ' ' + str(data.get('message'))}")
            if data.get("code") in (-101, -111):
                sys.exit("登录/Cookie 失效，已停止。")
            if i < len(mids):
                time.sleep(random.uniform(1.5, 3.5))

    LOG_JSON.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    done = sum(1 for r in results if r["ok"])
    print(f"完成：成功 {done} / {len(results)}，详情见 {LOG_JSON.name}")


if __name__ == "__main__":
    main()
