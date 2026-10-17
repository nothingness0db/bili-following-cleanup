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
    sql("UPDATE gates SET paused='', until_at=0, next_at=0 WHERE lane='account'")


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
    left = sql("SELECT next_at FROM gates WHERE lane='account'").fetchone()[0] - time.time()
    check("成功后排下一次请求 0.25–0.4 秒后", 0.2 <= left <= 0.45, f"next in {left:.3f}s")

    class Risk:
        def get(self, *a, **k):
            return Response({"code": -352, "message": "请求过于频繁"})

    _, err = run(bili_read.get_json, Risk(), "u")
    check("-352 抛 RiskControlError", err is not None and "code=-352" in err, err)
    paused = sql("SELECT paused FROM gates WHERE lane='account'").fetchone()[0]
    check("闸门被暂停", bool(paused), paused)

    until = sql("SELECT until_at FROM gates WHERE lane='account'").fetchone()[0] - time.time()
    check("冷却 30 分钟（IP 级冷却型风控的观测值）", 1790 <= until <= 1805, f"{until:.0f}s")

    notes = bili_read.resume()
    check("冷却期内 --resume 被拒绝", any("还要等" in n for n in notes), notes)

    sql("UPDATE gates SET until_at=0 WHERE lane='account'")
    bili_read.resume()
    check("冷却结束后可以 resume", sql("SELECT paused FROM gates WHERE lane='account'").fetchone()[0] == "")

    class Http412:
        def get(self, *a, **k):
            return Response({}, status=412)

    _, err = run(bili_read.get_json, Http412(), "u")
    check("HTTP 412 也当风控", err is not None and "412" in err, err)

    # ================================================= 风控码识别
    print("[1a2] 风控码识别：body 里的 -403 也必须算风控")
    for code, expect_risk in [(-352, True), (-403, True), (-412, True), (-509, True), (-404, False), (22001, False)]:
        reset()

        class Coded:
            def __init__(self, c):
                self.c = c

            def get(self, *a, **k):
                return Response({"code": self.c, "message": "" if self.c != -403 else "访问权限不足"})

        _, err = run(bili_read.get_json, Coded(code), "u")
        paused = sql("SELECT paused FROM gates WHERE lane='account'").fetchone()[0] != ""
        is_risk = err is not None and err.startswith("RiskControlError")
        check(f"code={code} -> {'风控' if expect_risk else '普通失败'}", is_risk == expect_risk and paused == expect_risk,
              f"{err} / 暂停={paused}")

    # ================================================= 分车道熔断
    print("[1b] 风控是 IP 级的：任一侧撞上，两条车道一起停")
    reset()

    class AnonRisk:
        def get(self, *a, **k):
            return Response({"code": -352})

    _, err = run(bili_read.get_json, AnonRisk(), "u", lane="anon")
    check("匿名侧撞风控被暂停", "-352" in (err or ""), err)
    check("匿名侧状态为暂停", sql("SELECT paused FROM gates WHERE lane='anon'").fetchone()[0] != "")
    check("账号侧也被连带暂停（同一出口）",
          sql("SELECT paused FROM gates WHERE lane='account'").fetchone()[0] != "")
    _, err = run(bili_read.get_json, Ok(), "u")
    check("被连带后账号侧也确实发不出去", err is not None and "已暂停" in err, err)

    sql("UPDATE gates SET until_at=0")
    check("可以只解除匿名侧", any("已解除" in n for n in bili_read.resume("anon")),
          bili_read.resume("anon"))
    check("解一条不影响另一条",
          sql("SELECT paused FROM gates WHERE lane='account'").fetchone()[0] != "")
    sql("UPDATE gates SET paused='', until_at=0")
    check("两条都解除后账号侧能请求", bili_read.get_json(Ok(), "u")["code"] == 0)

    print("[1c] 旧版全局 gate 记录迁移到 account 车道")
    for path in WORK.glob("state.sqlite3*"):
        path.unlink()
    import sqlite3 as sq
    legacy = sq.connect(bili_read.STATE_FILE, isolation_level=None)
    legacy.execute("CREATE TABLE gate (id INTEGER PRIMARY KEY, next_at REAL, paused TEXT, until_at REAL)")
    legacy.execute("INSERT INTO gate VALUES (1, 0, '旧的风控', 0)")
    legacy.close()
    bili_read.connection().close()
    check("旧暂停状态落到 account 车道",
          sql("SELECT paused FROM gates WHERE lane='account'").fetchone()[0] == "旧的风控")
    check("旧表已删除", not sql("SELECT name FROM sqlite_master WHERE type='table' AND name='gate'"))

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

    def fake_videos(client, url, params=None, **kwargs):
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

    def fake_fans(client, url, params=None, **kwargs):
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

    def fake_following(client, url, params=None, **kwargs):
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

    def fake_following_ok(client, url, params=None, **kwargs):
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
    check("写侧风控暂停 account 车道",
          bool(sql("SELECT paused FROM gates WHERE lane='account'").fetchone()[0]))

    client = PostClient()
    count, stopped = bili_write.run(client, "jct", list(range(60)), names, log)
    check("暂停期间再跑会被挡住", "已暂停" in stopped and client.calls == [], f"{stopped} / calls={client.calls}")

    unpause()
    client = PostClient()
    count, stopped = bili_write.run(client, "jct", list(range(60)), names, log)
    check("续做时跳过已成功的 0 号", "0" not in client.calls, client.calls[:3])
    check("批上限 50", count == 50, count)
    # 0 成功、1 风控、2 在暂停期被挡 —— 三条各一条，之后 C 段补 50 条
    check("日志按 mid 去重累积", len(json.loads(log.read_text(encoding="utf-8"))) == 53,
          len(json.loads(log.read_text(encoding="utf-8"))))
    check("当日计数已累计（含撞风控那次）", bili_read.used("unfollow") == 52, bili_read.used("unfollow"))

    sql("UPDATE counter SET n=? WHERE kind='unfollow'", (bili_write.DAILY_MAX,))
    client = PostClient()
    count, stopped = bili_write.run(client, "jct", list(range(60)), names, log)
    check("日上限到了就干净地停", "上限" in stopped and client.calls == [], f"{stopped} / calls={client.calls}")

    # ================================================= 连片失败熔断
    print("[7] 连片失败熔断：不是「这个号坏了」，是系统性故障")
    reset()
    log = WORK / "unfollow_log.json"
    log.unlink(missing_ok=True)
    client = PostClient([0] + [-404] * 10)
    count, stopped = bili_write.run(client, "jct", list(range(20)), names, log)
    check("连续失败到阈值就停批", "连续" in stopped, stopped)
    check("没有把 20 个全打出去", len(client.calls) == 1 + bili_read.FAIL_STREAK_LIMIT, len(client.calls))
    check("并暂停车道", sql("SELECT paused FROM gates WHERE lane='account'").fetchone()[0] != "")

    reset()
    calls = [0]

    def always_500(client, url, params=None, **kwargs):
        calls[0] += 1
        raise bili_read.ApiError("接口 code=-404，未重试")

    bili_read.get_json = always_500
    fetch_fans.SRC = WORK / "fans_streak.json"
    fetch_fans.SRC.write_text(json.dumps([{"mid": i, "uname": f"f{i}"} for i in range(20)]), encoding="utf-8")
    _, err = run(fetch_fans.main)
    check("读侧连片失败也停批", err is not None and "连续" in err, err)
    check("不会把 20 个全打完", calls[0] == bili_read.FAIL_STREAK_LIMIT, calls[0])
    check("读侧连片失败暂停车道", sql("SELECT paused FROM gates WHERE lane='anon'").fetchone()[0] != "")

    # ================================================= 配额与限速参数
    print("[8] 配额语义与限速参数")
    reset()
    bili_write.BATCH_MAX = bili_write.BATCH_MAX  # noqa: 只是明示未改动

    class Boom:
        def post(self, *a, **k):
            raise __import__("httpx").HTTPError("connection reset")

    count, stopped = bili_write.run(Boom(), "jct", [1], {}, WORK / "boom.json")
    check("传输层失败也占用当日配额（否则不是硬上限）", bili_read.used("unfollow") == 1,
          bili_read.used("unfollow"))
    check("传输层失败不算风控", stopped == "", stopped)

    check("account 读间隔保持 0.25–0.4", bili_read.READ_INTERVAL["account"] == (0.25, 0.4),
          bili_read.READ_INTERVAL["account"])
    check("anon 读间隔保持 0.3–0.5", bili_read.READ_INTERVAL["anon"] == (0.3, 0.5),
          bili_read.READ_INTERVAL["anon"])
    check("写间隔保持 8–15（不能被误配成读间隔）",
          (bili_read.WRITE_MIN_INTERVAL, bili_read.WRITE_MAX_INTERVAL) == (8.0, 15.0),
          (bili_read.WRITE_MIN_INTERVAL, bili_read.WRITE_MAX_INTERVAL))
    check("两条车道冷却都是 30 分钟", bili_read.COOLDOWN == {"account": 1800, "anon": 1800}, bili_read.COOLDOWN)

    # ================================================= schema 自愈
    print("[9] 库停在任何一次建表之间都能自愈")
    reset()
    for path in WORK.glob("state.sqlite3*"):
        path.unlink()
    partial = __import__("sqlite3").connect(bili_read.STATE_FILE, isolation_level=None)
    partial.execute("CREATE TABLE gates (lane TEXT PRIMARY KEY, next_at REAL, paused TEXT, until_at REAL)")
    partial.execute("INSERT INTO gates VALUES ('account', 0, '', 0)")
    partial.execute("INSERT INTO gates VALUES ('anon', 0, '', 0)")
    partial.close()   # 只有 gates，没有 cache / counter
    bili_read.store("videos", "1", {"code": 0})
    check("缺 cache 表也能写缓存", bili_read.cached("videos", "1") == {"code": 0})
    db = bili_read.connection()
    try:
        db.execute("INSERT INTO counter (day, kind, n) VALUES ('2000-01-01', 'unfollow', 1) "
                   "ON CONFLICT(day, kind) DO UPDATE SET n = n + 1")
    finally:
        db.close()
    check("缺 counter 表也能写配额", True)


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
