import csv
import json
import random
import re
import sys
import time
from pathlib import Path

import httpx

BASE = Path(__file__).resolve().parent
COOKIE_FILE = BASE / "cookie.txt"
OUT_JSON = BASE / "following.json"
OUT_CSV = BASE / "following.csv"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


def load_cookie() -> str:
    raw = COOKIE_FILE.read_text(encoding="utf-8")
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    cookie = " ".join(lines)
    if "SESSDATA" not in cookie or "bili_jct" not in cookie:
        sys.exit("cookie.txt 里缺少 SESSDATA 或 bili_jct，请按模板填写。")
    return cookie


def parse_cookie(cookie: str):
    jar = {}
    for part in cookie.split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            jar[k.strip()] = v.strip()
    return jar


def fetch_uid(client: httpx.Client) -> int:
    nav = client.get("https://api.bilibili.com/x/web-interface/nav")
    data = nav.json()
    if data.get("code") != 0 or not data.get("data", {}).get("isLogin"):
        sys.exit(f"登录校验失败：{data.get('message')}（Cookie 可能过期）")
    return int(data["data"]["mid"])


def fetch_all(client: httpx.Client, uid: int) -> list:
    out = []
    pn = 1
    while True:
        url = "https://api.bilibili.com/x/relation/followings"
        params = {"vmid": uid, "pn": pn, "ps": 50, "order": "desc", "order_type": "attention"}
        r = client.get(url, params=params)
        if r.status_code == 412:
            sys.exit("触发风控 412，请稍后再试（降低频率）。")
        data = r.json()
        if data.get("code") != 0:
            sys.exit(f"接口返回错误 code={data.get('code')} msg={data.get('message')}")
        page = data.get("data", {})
        items = page.get("list", []) or []
        for it in items:
            out.append(
                {
                    "mid": it.get("mid"),
                    "uname": it.get("uname"),
                    "sign": it.get("sign"),
                    "face": it.get("face"),
                    "vip": it.get("vip", {}).get("vipStatus") if isinstance(it.get("vip"), dict) else None,
                    "official": (it.get("official_verify") or {}).get("desc"),
                    "official_type": (it.get("official_verify") or {}).get("type"),
                    "mtime": it.get("mtime"),
                    "visit_rank": len(out) + 1,
                    "space": f"https://space.bilibili.com/{it.get('mid')}",
                }
            )
        print(f"  第 {pn} 页：累计 {len(out)} / 共 {page.get('total', '?')}")
        total = page.get("total", 0)
        if not items or len(out) >= total:
            break
        pn += 1
        time.sleep(random.uniform(0.8, 1.6))
    return out


def main():
    cookie = load_cookie()
    headers = {
        "Cookie": cookie,
        "User-Agent": UA,
        "Referer": "https://www.bilibili.com/",
        "Origin": "https://www.bilibili.com",
    }
    with httpx.Client(headers=headers, timeout=20, follow_redirects=True) as client:
        uid = fetch_uid(client)
        print(f"登录用户 uid={uid}，开始拉取关注列表…")
        rows = fetch_all(client, uid)

    OUT_JSON.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["mid", "uname"])
        w.writeheader()
        w.writerows(rows)
    print(f"完成：{len(rows)} 条 -> {OUT_JSON.name} / {OUT_CSV.name}（visit_rank 按「最常访问」排序）")


if __name__ == "__main__":
    main()
