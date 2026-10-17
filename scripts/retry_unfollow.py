import sys
from pathlib import Path

import httpx

import bili_read
import bili_write

BASE = Path(__file__).resolve().parent
COOKIE_FILE = BASE / "cookie.txt"
RETRY_FILE = BASE / "retry.txt"
LOG_JSON = BASE / "retry_log.json"


def load_cookie():
    raw = COOKIE_FILE.read_text(encoding="utf-8")
    return " ".join(l.strip() for l in raw.splitlines() if l.strip() and not l.strip().startswith("#"))


def main():
    cookie = load_cookie()
    jct = bili_write.jct_from(cookie)
    if not RETRY_FILE.exists():
        sys.exit("缺少 retry.txt（每行一个要补的 mid）。")
    mids = [l.strip() for l in RETRY_FILE.read_text(encoding="utf-8").splitlines() if l.strip()]
    if not mids:
        sys.exit("retry.txt 为空。")

    print(f"补做 {len(mids)} 个。节奏与 unfollow.py 完全相同：{bili_read.WRITE_MIN_INTERVAL:.0f}–"
          f"{bili_read.WRITE_MAX_INTERVAL:.0f} 秒一次、批上限 {bili_write.BATCH_MAX}、"
          f"今日已做 {bili_read.used('unfollow')}/{bili_write.DAILY_MAX}")
    print("不再做内部退避重试：撞上风控就整批停，等冷却后手动 --resume 再跑。")

    headers = {"Cookie": cookie, "User-Agent": bili_read.UA, "Referer": "https://www.bilibili.com/"}
    with httpx.Client(headers=headers, timeout=20, follow_redirects=True) as client:
        count, stopped = bili_write.run(client, jct, mids, {}, LOG_JSON)

    if stopped:
        sys.exit(f"{stopped}\n详情见 {LOG_JSON.name}；剩下的等下一批/明天再做。")

    done = sum(1 for r in bili_write.load_log(LOG_JSON) if r.get("ok"))
    print(f"完成：本次 {count} 个，累计成功 {done} / {len(mids)}，详情见 {LOG_JSON.name}")
    if done < len(mids):
        print("还有未完成的：直接再跑一次本脚本即可续做（已成功的会自动跳过）。")


if __name__ == "__main__":
    main()
