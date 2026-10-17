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
    # 粘连的 mid（两个号被拼成一行）拆不对就会取关到意料之外的账号，这一步宁可停。
    bad = [m for m in mids if not m.isdigit()]
    if bad:
        sys.exit("unfollow.txt 里有不是纯数字的行，先清理再跑：\n  " + "\n  ".join(bad[:8])
                 + ("\n  …" if len(bad) > 8 else ""))
    dupes = len(mids) - len(set(mids))
    if dupes:
        print(f"unfollow.txt 里有 {dupes} 个重复 mid，已去重")
        mids = list(dict.fromkeys(mids))
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
    retry_failed = "--retry-failed" in sys.argv
    seen = {str(r.get("mid")): r for r in bili_write.load_log(LOG_JSON)}
    todo = [m for m in mids if m not in seen or (retry_failed and not seen[m].get("ok"))]
    failed = sum(1 for m in mids if m in seen and not seen[m].get("ok"))
    if not todo:
        print(f"unfollow.txt 里的 {len(mids)} 个都已经成功取关过了，没有需要做的。")
        if failed:
            print(f"其中 {failed} 个是之前失败的；要再试一次加 --retry-failed。")
        return

    print(f"待取关清单 {len(mids)} 个（已成功 {len(already)} 个，本次待做 {len(todo)} 个）：")
    for m in todo[:bili_write.BATCH_MAX]:
        print(f"  {m}  {names.get(m, '(不在 following.json 里)')}")
    if len(todo) > bili_write.BATCH_MAX:
        print(f"  … 还有 {len(todo) - bili_write.BATCH_MAX} 个本轮不做")
    if failed and not retry_failed:
        print(f"另有 {failed} 个之前试过并失败的，本次跳过（--retry-failed 可重试）")
    print(f"节奏：每个间隔 {bili_read.WRITE_MIN_INTERVAL:.0f}–{bili_read.WRITE_MAX_INTERVAL:.0f} 秒，"
          f"本批上限 {bili_write.BATCH_MAX} 个，今日已做 {bili_read.used('unfollow')}/{bili_write.DAILY_MAX}")

    if "--yes" not in sys.argv:
        batch = min(len(todo), bili_write.BATCH_MAX)
        ans = input(f"确认取关这 {batch} 个账号？输入 yes 继续：").strip().lower()
        if ans != "yes":
            sys.exit("已取消。")

    headers = {"Cookie": cookie, "User-Agent": bili_read.UA, "Referer": "https://www.bilibili.com/"}
    with httpx.Client(headers=headers, timeout=20, follow_redirects=True) as client:
        count, stopped = bili_write.run(client, jct, mids, names, LOG_JSON, retry_failed=retry_failed)

    if stopped:
        sys.exit(f"{stopped}\n详情见 {LOG_JSON.name}；剩下的等下一批/明天再做。")

    done = sum(1 for r in bili_write.load_log(LOG_JSON) if r.get("ok"))
    print(f"完成：本次 {count} 个，累计成功 {done} / {len(mids)}，详情见 {LOG_JSON.name}")
    if done < len(mids):
        print("还有未完成的：直接再跑一次本脚本即可续做（已成功的自动跳过，"
              "失败项默认不重试，要重试加 --retry-failed）。")


if __name__ == "__main__":
    main()
