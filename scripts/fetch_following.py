import csv
import json
import sys
from pathlib import Path

import httpx

import bili_read

BASE = Path(__file__).resolve().parent
COOKIE_FILE = BASE / "cookie.txt"
OUT_JSON = BASE / "following.json"
OUT_CSV = BASE / "following.csv"

NAV_URL = "https://api.bilibili.com/x/web-interface/nav"
FOLLOWINGS_URL = "https://api.bilibili.com/x/relation/followings"
PS = 50


def load_cookie() -> str:
    raw = COOKIE_FILE.read_text(encoding="utf-8")
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    cookie = " ".join(lines)
    if "SESSDATA" not in cookie or "bili_jct" not in cookie:
        sys.exit("cookie.txt 里缺少 SESSDATA 或 bili_jct，请按模板填写。")
    return cookie


def fetch_uid(client: httpx.Client) -> int:
    data = bili_read.get_json(client, NAV_URL)
    if data.get("code") != 0 or not data.get("data", {}).get("isLogin"):
        sys.exit(f"登录校验失败：{data.get('message')}（Cookie 可能过期）")
    return int(data["data"]["mid"])


def fetch_all(client: httpx.Client, uid: int, out: list, hits: list) -> None:
    pn = 1
    while True:
        key = f"{uid}:{pn}"
        # 分页按页缓存（1 小时）：中断后重跑只补没抓到的页，不用从第 1 页重来。
        data = bili_read.cached("following", key, bili_read.PAGE_TTL)
        if data is None:
            data = bili_read.get_json(
                client,
                FOLLOWINGS_URL,
                {"vmid": uid, "pn": pn, "ps": PS, "order": "desc", "order_type": "attention"},
            )
            bili_read.store("following", key, data)
        else:
            hits[0] += 1
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


def unique(rows: list) -> list:
    """翻页中途列表变动可能带来重复 mid；去重并按「最常访问」重排 visit_rank。"""
    seen, out = set(), []
    for row in rows:
        mid = str(row.get("mid"))
        if mid in seen:
            continue
        seen.add(mid)
        out.append(row)
    for rank, row in enumerate(out, 1):
        row["visit_rank"] = rank
    return out


def write_outputs(rows: list) -> None:
    bili_read.save_json(OUT_JSON, rows)  # 原子落盘，不会留下半截 JSON
    with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["mid", "uname"])
        w.writeheader()
        w.writerows(rows)


def main():
    cookie = load_cookie()
    headers = {
        "Cookie": cookie,
        "User-Agent": bili_read.UA,
        "Referer": "https://www.bilibili.com/",
        "Origin": "https://www.bilibili.com",
    }
    rows, hits = [], [0]
    with httpx.Client(headers=headers, timeout=20, follow_redirects=True) as client:
        try:
            uid = fetch_uid(client)
            print(f"登录用户 uid={uid}，开始拉取关注列表…")
            fetch_all(client, uid, rows, hits)
        except bili_read.RiskControlError as error:
            if rows:
                write_outputs(unique(rows))
                print(f"触发风控，已保存已抓的 {len(rows)} 条（清单不完整，冷却后续抓）。")
            sys.exit(f"采集暂停：{error}\n"
                     f"已抓到的页会在 1 小时内缓存，重跑只补剩下的页。")
    rows = unique(rows)
    write_outputs(rows)
    print(f"完成：{len(rows)} 条（{hits[0]} 页来自缓存）-> {OUT_JSON.name} / {OUT_CSV.name}（visit_rank 按「最常访问」排序）")


if __name__ == "__main__":
    main()
