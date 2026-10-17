import json
import sys
from pathlib import Path

import httpx

import bili_read
import bili_write

BASE = Path(__file__).resolve().parent
COOKIE_FILE = BASE / "cookie.txt"
SELECT_FILE = BASE / "unfollow.txt"
FOLLOWING_JSON = BASE / "following.json"
LOG_JSON = BASE / "unfollow_log.json"


def load_cookie() -> str:
    raw = COOKIE_FILE.read_text(encoding="utf-8")
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    cookie = " ".join(lines)
    if "SESSDATA" not in cookie or "bili_jct" not in cookie:
        sys.exit("cookie.txt 里缺少 SESSDATA 或 bili_jct。")
    return cookie


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


def main():
    cookie = load_cookie()
    jct = bili_write.jct_from(cookie)
    mids = load_selection()
    names = load_names()

    already = {str(r.get("mid")) for r in bili_write.load_log(LOG_JSON) if r.get("ok")}
    todo = [m for m in mids if str(m) not in already]
    if not todo:
        print(f"unfollow.txt 里的 {len(mids)} 个都已经成功取关过了，没有需要做的。")
        return

    print(f"待取关清单 {len(mids)} 个（已成功 {len(already)} 个，本次待做 {len(todo)} 个）：")
    for m in todo[:bili_write.BATCH_MAX]:
        print(f"  {m}  {names.get(m, '(未知名称)')}")
    if len(todo) > bili_write.BATCH_MAX:
        print(f"  … 还有 {len(todo) - bili_write.BATCH_MAX} 个本轮不做")
    print(f"节奏：每个间隔 {bili_read.WRITE_MIN_INTERVAL:.0f}–{bili_read.WRITE_MAX_INTERVAL:.0f} 秒，"
          f"本批上限 {bili_write.BATCH_MAX} 个，今日已做 {bili_read.used('unfollow')}/{bili_write.DAILY_MAX}")

    if "--yes" not in sys.argv:
        batch = min(len(todo), bili_write.BATCH_MAX)
        ans = input(f"确认取关这 {batch} 个账号？输入 yes 继续：").strip().lower()
        if ans != "yes":
            sys.exit("已取消。")

    headers = {"Cookie": cookie, "User-Agent": bili_read.UA, "Referer": "https://www.bilibili.com/"}
    with httpx.Client(headers=headers, timeout=20, follow_redirects=True) as client:
        count, stopped = bili_write.run(client, jct, mids, names, LOG_JSON)

    if stopped:
        sys.exit(f"{stopped}\n详情见 {LOG_JSON.name}；剩下的等下一批/明天再做。")

    done = sum(1 for r in bili_write.load_log(LOG_JSON) if r.get("ok"))
    print(f"完成：本次 {count} 个，累计成功 {done} / {len(mids)}，详情见 {LOG_JSON.name}")
    if done < len(mids):
        print("还有未完成的：直接再跑一次本脚本即可续做（已成功的会自动跳过）。")


if __name__ == "__main__":
    main()
