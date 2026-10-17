import json
import sys
from pathlib import Path

import httpx

import bili_read

BASE = Path(__file__).resolve().parent
SRC = BASE / "combined.json"
H = {"User-Agent": bili_read.UA, "Referer": "https://www.bilibili.com/"}

CARD_URL = "https://api.bilibili.com/x/web-interface/card"
UPSTAT_URL = "https://api.bilibili.com/x/space/upstat"


def fetch(client, mid, hits):
    """两个接口各自按 mid 缓存：半个 mid 做完也能续着补另一半个。"""
    card = bili_read.cached("card", mid)
    if card is None:
        card = bili_read.get_json(client, CARD_URL, {"mid": mid, "photo": "false"}, lane="anon")
        bili_read.store("card", mid, card)
    else:
        hits[0] += 1

    up = bili_read.cached("upstat", mid)
    if up is None:
        up = bili_read.get_json(client, UPSTAT_URL, {"mid": mid}, lane="anon")
        bili_read.store("upstat", mid, up)
    else:
        hits[1] += 1

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
    hits = [0, 0]
    client = httpx.Client(headers=H, timeout=20)
    try:
        for i, r in enumerate(rows):
            try:
                r.update(fetch(client, str(r["mid"]), hits))
            except bili_read.ApiError as error:
                print(f"  跳过 {r.get('mid')}：{error}")
            if (i + 1) % 50 == 0:
                print(f"  {i + 1}/{len(rows)}（缓存命中 {hits[0] + hits[1]} 次）")
    except bili_read.RiskControlError as error:
        bili_read.save_json(SRC, rows)
        sys.exit(f"触发风控，已保存进度并暂停：{error}\n"
                 f"已抓到的下回直接从缓存补剩下的，不用从头再来。")
    finally:
        client.close()
    bili_read.save_json(SRC, rows)
    ok = sum(1 for r in rows if r.get("fans") is not None)
    print(f"完成：{ok}/{len(rows)} 拿到粉丝数（缓存命中 {hits[0] + hits[1]} 次）-> {SRC.name}")


if __name__ == "__main__":
    main()
