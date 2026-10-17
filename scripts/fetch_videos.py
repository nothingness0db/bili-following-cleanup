import hashlib
import json
import sys
import time
import urllib.parse
from pathlib import Path

import httpx

import bili_read

BASE = Path(__file__).resolve().parent
SRC = BASE / "following.json"
OUT = BASE / "following_videos.json"
COOKIE_FILE = BASE / "cookie.txt"
PS = 6

SEARCH_URL = "https://api.bilibili.com/x/space/wbi/arc/search"
NAV_URL = "https://api.bilibili.com/x/web-interface/nav"

TAB = [46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
       33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
       61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
       36, 20, 34, 44, 52]


def load_cookie():
    raw = COOKIE_FILE.read_text(encoding="utf-8")
    return " ".join(l.strip() for l in raw.splitlines() if l.strip() and not l.strip().startswith("#"))


class Wbi:
    def __init__(self, client):
        self.client = client
        self.key = None

    def refresh(self):
        w = bili_read.get_json(self.client, NAV_URL)["data"]["wbi_img"]
        img = w["img_url"].rsplit("/", 1)[-1].split(".")[0]
        sub = w["sub_url"].rsplit("/", 1)[-1].split(".")[0]
        self.key = "".join((img + sub)[i] for i in TAB)[:32]

    def signed(self, params):
        p = dict(params)
        p["wts"] = int(time.time())
        q = urllib.parse.urlencode(sorted(p.items()))
        p["w_rid"] = hashlib.md5((q + self.key).encode()).hexdigest()
        return p


def blank(row, code):
    return {"mid": row.get("mid"), "uname": row.get("uname"), "sign": row.get("sign"),
            "official": row.get("official"), "videos": [], "code": code}


def main():
    rows = json.loads(SRC.read_text(encoding="utf-8"))
    previous = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else []
    previous = {str(r.get("mid")): r for r in previous if r.get("code") == 0}
    results, pending = [], []
    hits = 0
    streak = 0
    # 先填满本地结果：前置 NAV 被挡时，也不能丢掉后面尚未遍历的缓存或旧投稿。
    for i, row in enumerate(rows):
        mid = str(row.get("mid"))
        body = bili_read.cached("videos", mid)
        if body is not None:
            hits += 1
        else:
            pending.append(i)
            body = previous.get(mid) or blank(row, "pending")
        result = dict(body)
        result.update({key: row.get(key) for key in ("mid", "uname", "sign", "official")})
        results.append(result)
    if not pending:
        bili_read.save_json(OUT, results)
        print(f"完成：{len(rows)} 个账号全部使用缓存，未请求接口 -> {OUT.name}")
        return

    cookie = load_cookie()
    client = httpx.Client(
        headers={"User-Agent": bili_read.UA, "Referer": "https://space.bilibili.com/", "Cookie": cookie},
        timeout=20,
    )
    try:
        try:
            wbi = Wbi(client)
            wbi.refresh()
        except bili_read.ApiError as error:
            sys.exit(f"拿不到 wbi 签名密钥：{error}（Cookie 可能有问题）")
        for i in pending:
            row = rows[i]
            mid = str(row.get("mid"))
            try:
                params = wbi.signed({"mid": row["mid"], "ps": PS, "pn": 1, "order": "pubdate", "platform": "web"})
                d = bili_read.get_json(client, SEARCH_URL, params)
                vlist = ((d.get("data") or {}).get("list") or {}).get("vlist") or []
                results[i] = {
                    "mid": row.get("mid"), "uname": row.get("uname"), "sign": row.get("sign"),
                    "official": row.get("official"),
                    "videos": [
                        {"title": v.get("title"), "play": v.get("play"), "created": v.get("created")}
                        for v in vlist[:PS]
                    ],
                    "code": d.get("code"),
                }
                bili_read.store("videos", mid, results[i])  # 只缓存成功的，失败的下次会重抓
            except bili_read.ApiError as error:
                if results[i].get("code") != 0:
                    results[i] = blank(row, "error")
                streak += 1
                print(f"  跳过 {mid}：{error}")
                if streak >= bili_read.FAIL_STREAK_LIMIT:
                    bili_read.pause(f"连续 {streak} 个投稿请求失败，像系统性故障：{error}")
                    raise bili_read.RiskControlError(
                        f"连续 {streak} 个请求失败（不是单个号的问题，像是 Cookie 失效 / wbi 失效 / 认不出的风控）")
            else:
                streak = 0
            if (i + 1) % 50 == 0:
                print(f"  {i + 1}/{len(rows)}（其中 {hits} 个用缓存）")
    except bili_read.RiskControlError as error:
        bili_read.save_json(OUT, results)
        sys.exit(f"触发风控，已保存进度并暂停：{error}\n"
                 f"已抓到的下回直接从缓存补剩下的，不用从头再来。")
    finally:
        client.close()
    bili_read.save_json(OUT, results)
    ok = sum(1 for r in results if r.get("videos"))
    print(f"完成：{ok}/{len(rows)} 拿到投稿（其中 {hits} 个来自缓存）-> {OUT.name}")


if __name__ == "__main__":
    main()
