"""离线自检：不联网、不真实等待，用假 httpx 驱动真实的闸门与采集/取关脚本。

跑法：python selftest.py     全部通过则退出码 0
会在本目录下建临时目录 .selftest/，跑完自动删掉。
"""
import json
import sys
import time
import types
from pathlib import Path

BASE = Path(__file__).resolve().parent
WORK = BASE / ".selftest"
sys.path.insert(0, str(BASE))


def install_fake_httpx():
    httpx = types.ModuleType("httpx")

    class HTTPError(Exception):
        pass

    class Client:
        def __init__(self, *args, **kwargs):
            pass

        def get(self, *args, **kwargs):
            raise AssertionError("自检期间不应该真的发请求")

        post = get

        def close(self):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    httpx.Client = Client
    httpx.HTTPError = HTTPError
    sys.modules["httpx"] = httpx


install_fake_httpx()

import bili_read          # noqa: E402
import bili_write         # noqa: E402
import fetch_following    # noqa: E402
import fetch_fans         # noqa: E402
import fetch_videos       # noqa: E402

FAILS = []


class Response:
    def __init__(self, payload=None, status=200):
        self.status_code = status
        self._payload = payload if payload is not None else {}

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class PostClient:
    """假 client：按 script 依次返回 code，记录打了哪些 fid。"""

    def __init__(self, script=()):
        self.script = list(script)
        self.calls = []

    def post(self, url, data=None, headers=None, timeout=None):
        self.calls.append(data["fid"])
        code = self.script.pop(0) if self.script else 0
        return Response({"code": code, "message": "0"})


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + (f"  | {detail}" if detail else ""))
    if not cond:
        FAILS.append(name)


class Rows(list):
    def fetchone(self):
        return self[0] if self else None


def sql(statement, args=()):
    """一次性查询：用完立刻关连接，否则 Windows 上删不掉 sqlite 文件。"""
    db = bili_read.connection()
    try:
        return Rows(db.execute(statement, args).fetchall())
    finally:
        db.close()


def reset():
    for path in WORK.glob("state.sqlite3*"):
        path.unlink()
    bili_read.STATE_FILE = WORK / "state.sqlite3"
    bili_read.connection().close()


def unpause():
    sql("UPDATE gate SET paused='', until_at=0, next_at=0 WHERE id=1")


def run(fn, *args, **kwargs):
    """跑脚本，把 SystemExit 和各种异常都收成一条消息。"""
    try:
        return fn(*args, **kwargs), None
    except SystemExit as error:
        return None, str(error)
    except Exception as error:  # noqa: BLE001 - 自检要能看见任何异常
        return None, f"{type(error).__name__}: {error}"


def main():
    if WORK.exists():
        for path in sorted(WORK.rglob("*"), reverse=True):
            path.unlink() if path.is_file() else path.rmdir()
    WORK.mkdir(parents=True, exist_ok=True)
    time.sleep = lambda seconds: None  # 限速照算，只是不真的等

    # ================================================= 闸门本身
    print("[1] 闸门：限速 + 风控熔断")
    reset()

    class Ok:
        def get(self, *a, **k):
            return Response({"code": 0})

    check("正常请求返回数据", bili_read.get_json(Ok(), "u")["code"] == 0)
    left = sql("SELECT next_at FROM gate").fetchone()[0] - time.time()
    check("成功后排下一次请求 3–6 秒后", 2.9 <= left <= 6.05, f"next in {left:.1f}s")

    class Risk:
        def get(self, *a, **k):
            return Response({"code": -352, "message": "请求过于频繁"})

    _, err = run(bili_read.get_json, Risk(), "u")
    check("-352 抛 RiskControlError", err is not None and "code=-352" in err, err)
    paused = sql("SELECT paused FROM gate").fetchone()[0]
    check("闸门被暂停", bool(paused), paused)

    until = sql("SELECT until_at FROM gate").fetchone()[0] - time.time()
    check("冷却 30 分钟", 1790 <= until <= 1805, f"{until:.0f}s")

    _, err = run(bili_read.resume)
    check("冷却期内 --resume 被拒绝", err is not None and "尚未结束" in err, err)

    sql("UPDATE gate SET until_at=0 WHERE id=1")
    bili_read.resume()
    check("冷却结束后可以 resume", sql("SELECT paused FROM gate").fetchone()[0] == "")

    class Http412:
        def get(self, *a, **k):
            return Response({}, status=412)

    _, err = run(bili_read.get_json, Http412(), "u")
    check("HTTP 412 也当风控", err is not None and "412" in err, err)

    # ================================================= 缓存
    print("[2] 缓存：命中与过期")
    reset()
    bili_read.store("videos", "123", {"code": 0, "videos": [1]})
    check("store / cached 往返", bili_read.cached("videos", "123") == {"code": 0, "videos": [1]})
    sql("UPDATE cache SET at = at - 90000")
    check("超过 TTL 视为未命中", bili_read.cached("videos", "123") is None)

    # ================================================= 投稿续抓
    print("[3] fetch_videos：中断后只补剩下的")
    reset()
    src = WORK / "following.json"
    src.write_text(json.dumps([{"mid": i, "uname": f"v{i}", "sign": "", "official": None} for i in range(5)]),
                   encoding="utf-8")
    fetch_videos.SRC, fetch_videos.OUT = src, WORK / "following_videos.json"
    fetch_videos.COOKIE_FILE = WORK / "cookie.txt"
    fetch_videos.COOKIE_FILE.write_text("SESSDATA=x; bili_jct=y", encoding="utf-8")

    calls, state = [], {"n": 0}

    def fake_videos(client, url, params=None):
        if url.endswith("nav"):
            return {"code": 0, "data": {"wbi_img": {"img_url": "https://i0/x/" + "a" * 32 + ".png",
                                                    "sub_url": "https://i0/x/" + "b" * 32 + ".png"}}}
        calls.append(params["mid"])
        state["n"] += 1
        if state["n"] == 3:
            raise bili_read.RiskControlError("接口 code=-352")
        return {"code": 0, "data": {"list": {"vlist": [{"title": "t", "play": 1, "created": 2}]}}}

    bili_read.get_json = fake_videos
    _, err = run(fetch_videos.main)
    check("第 3 个中招 → 整批停", err is not None and "风控" in err, err)
    check("中断前只打了 3 个", len(calls) == 3, calls)
    first = json.loads(fetch_videos.OUT.read_text(encoding="utf-8"))
    check("输出覆盖全部 5 行", [r["code"] for r in first] == [0, 0, "pending", "pending", "pending"],
          [r["code"] for r in first])

    unpause()
    calls.clear()
    _, err = run(fetch_videos.main)
    check("重跑成功", err is None, err)
    check("重跑只请求剩下 3 个（没从头来）", calls == [2, 3, 4], calls)
    second = json.loads(fetch_videos.OUT.read_text(encoding="utf-8"))
    check("5 行都补齐了", all(r.get("videos") for r in second), [len(r.get("videos") or []) for r in second])

    # ================================================= 粉丝续抓
    print("[4] fetch_fans：card 已缓存时只补 upstat")
    reset()
    fans_src = WORK / "combined.json"
    fans_src.write_text(json.dumps([{"mid": "42", "uname": "f"}]), encoding="utf-8")
    fetch_fans.SRC = fans_src
    bili_read.store("card", "42", {"code": 0, "data": {"card": {"fans": 100, "attention": 5,
                                                              "level_info": {"current_level": 3}}}})
    urls = []

    def fake_fans(client, url, params=None):
        urls.append(url)
        return {"code": 0, "data": {"archive": {"view": 42}, "likes": 7}}

    bili_read.get_json = fake_fans
    _, err = run(fetch_fans.main)
    check("只请求了 upstat", err is None and urls == [fetch_fans.UPSTAT_URL], urls)
    row = json.loads(fans_src.read_text(encoding="utf-8"))[0]
    check("粉丝数从缓存补齐", row["fans"] == 100 and row["views"] == 42, row)

    # ================================================= 关注列表按页续抓
    print("[5] fetch_following：按页缓存续抓 + 去重")
    reset()
    fetch_following.OUT_JSON, fetch_following.OUT_CSV = WORK / "fl.json", WORK / "fl.csv"
    fetch_following.COOKIE_FILE = WORK / "cookie.txt"
    pages = []

    def fake_following(client, url, params=None):
        if url.endswith("nav"):
            return {"code": 0, "data": {"isLogin": True, "mid": 999}}
        pages.append(params["pn"])
        if params["pn"] == 3:
            raise bili_read.RiskControlError("接口 code=-352")
        return {"code": 0, "data": {"total": 150,
                                    "list": [{"mid": params["pn"] * 1000 + i, "uname": f"u{i}"} for i in range(50)]}}

    bili_read.get_json = fake_following
    _, err = run(fetch_following.main)
    check("第 3 页中招 → 停", err is not None and "-352" in err, err)
    check("已抓的 100 条落了盘", len(json.loads(fetch_following.OUT_JSON.read_text(encoding="utf-8"))) == 100)

    unpause()
    pages.clear()

    def fake_following_ok(client, url, params=None):
        if url.endswith("nav"):
            return {"code": 0, "data": {"isLogin": True, "mid": 999}}
        pages.append(params["pn"])
        return {"code": 0, "data": {"total": 150,
                                    "list": [{"mid": params["pn"] * 1000 + i, "uname": f"u{i}"} for i in range(50)]}}

    bili_read.get_json = fake_following_ok
    _, err = run(fetch_following.main)
    check("重跑成功", err is None, err)
    check("只请求了第 3 页", pages == [3], pages)
    final = json.loads(fetch_following.OUT_JSON.read_text(encoding="utf-8"))
    check("150 条、无重复、visit_rank 连续",
          len(final) == 150 and len({r["mid"] for r in final}) == 150
          and [r["visit_rank"] for r in final] == list(range(1, 151)),
          f"{len(final)} 条")

    # ================================================= 写侧闸门
    print("[6] 取关：遇风控整批停、批上限、日上限、续做")
    reset()
    log = WORK / "unfollow_log.json"
    names = {str(m): f"n{m}" for m in range(60)}

    client = PostClient([0, -352])
    count, stopped = bili_write.run(client, "jct", list(range(60)), names, log)
    check("第 2 个中招 → 整批停", "风控" in stopped and client.calls == ["0", "1"], f"{stopped} / calls={client.calls}")
    rows = json.loads(log.read_text(encoding="utf-8"))
    check("日志落盘、已成功的不丢", [r["ok"] for r in rows] == [True, False], [r["ok"] for r in rows])
    check("写侧风控同样暂停全局闸门",
          bool(sql("SELECT paused FROM gate").fetchone()[0]))

    client = PostClient()
    count, stopped = bili_write.run(client, "jct", list(range(60)), names, log)
    check("暂停期间再跑会被挡住", "已暂停" in stopped and client.calls == [], f"{stopped} / calls={client.calls}")

    unpause()
    client = PostClient()
    count, stopped = bili_write.run(client, "jct", list(range(60)), names, log)
    check("续做时跳过已成功的 0 号", 0 not in client.calls, client.calls[:3])
    check("批上限 50", count == 50, count)
    check("日志按 mid 去重累积", len(json.loads(log.read_text(encoding="utf-8"))) == 51,
          len(json.loads(log.read_text(encoding="utf-8"))))
    check("当日计数已累计", bili_read.used("unfollow") == 51, bili_read.used("unfollow"))

    sql("UPDATE counter SET n=? WHERE kind='unfollow'", (bili_write.DAILY_MAX,))
    client = PostClient()
    count, stopped = bili_write.run(client, "jct", list(range(60)), names, log)
    check("日上限到了就干净地停", "上限" in stopped and client.calls == [], f"{stopped} / calls={client.calls}")

    # ================================================= 收尾
    for path in sorted(WORK.rglob("*"), reverse=True):
        path.unlink() if path.is_file() else path.rmdir()
    WORK.rmdir()

    print()
    if FAILS:
        print(f"{len(FAILS)} 项失败：" + "、".join(FAILS))
        return 1
    print("全部通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
