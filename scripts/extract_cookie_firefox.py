"""Extract Bilibili login cookies from the local Firefox profile into cookie.txt.

Firefox stores cookies in plaintext (cookies.sqlite), which makes this the
easiest browser to pull a session from. Chrome/Edge encrypt their cookie DB
(DPAPI + AES-GCM) and are not handled here — for those, ask the user to paste
the Cookie header manually.

Usage:
    python extract_cookie_firefox.py [output_path]

Default output: ./cookie.txt (next to this script).
"""

import glob
import os
import shutil
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

# Cookies worth carrying for B站 API calls. SESSDATA/bili_jct/DedeUserID are
# required (login + csrf); the rest improve resistance to risk-control (-352).
KEY = ["SESSDATA", "bili_jct", "DedeUserID", "buvid3", "buvid4", "b_nut", "_uuid", "bili_ticket"]
REQUIRED = ["SESSDATA", "bili_jct", "DedeUserID"]


def find_profiles():
    base = os.path.expandvars(r"%APPDATA%\Mozilla\Firefox\Profiles")
    return glob.glob(os.path.join(base, "*", "cookies.sqlite"))


def read_cookies(src):
    tmp = os.path.join(tempfile.gettempdir(), "ff_bili_cookies.sqlite")
    shutil.copy2(src, tmp)
    con = sqlite3.connect(tmp)
    try:
        rows = con.execute(
            "select name, value, expiry from moz_cookies where host like '%bilibili%'"
        ).fetchall()
    finally:
        con.close()
    now = int(time.time())
    best = {}
    for name, value, expiry in rows:
        if name in KEY and (expiry == 0 or expiry > now):
            best[name] = value
    return best


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name("cookie.txt")
    profiles = find_profiles()
    if not profiles:
        sys.exit("未找到 Firefox 的 cookies.sqlite，请改用浏览器手动复制 Cookie。")
    for src in profiles:
        cookies = read_cookies(src)
        if all(k in cookies for k in REQUIRED):
            cookie = "; ".join(f"{k}={cookies[k]}" for k in KEY if k in cookies) + ";"
            out.write_text(
                "# 本地提取的 B 站 Cookie，勿外传 / 勿提交到版本库\n" + cookie + "\n",
                encoding="utf-8",
            )
            print(f"已写入 {out}（字段: {', '.join(k for k in KEY if k in cookies)}）")
            print(f"DedeUserID: {cookies['DedeUserID']}")
            return
    sys.exit("Firefox 配置里没找到完整的 B 站登录 Cookie（缺 SESSDATA/bili_jct/DedeUserID）。")


if __name__ == "__main__":
    main()
