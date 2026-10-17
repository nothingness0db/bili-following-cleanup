"""B站接口的统一闸门：串行限速 + 分车道熔断 + 成功响应缓存。

速度参数不是拍脑袋的，参照 bili-sync（同作者的 B 站同步工具）README「风控与限流须知」
里跑在生产环境的包线：列表 250ms、评论 400ms、全局每 250ms 最多 4 个请求、遇风控终止本轮。
本闸门是串行的，0.25–0.5 秒间隔 ≈ 2.5–4 次/秒，落在那个包线内。

- 读 `account` 车道（带 Cookie）：`fetch_following` / `fetch_videos`，0.25–0.4 秒。
- 读 `anon` 车道（不带 Cookie）：`fetch_fans` 的 card / upstat，0.3–0.5 秒
  （另外用 probe.py 实测过：0.2 秒间隔下 card / upstat 仍全过）。
- 写（取关）：`unfollow` / `retry_unfollow`，单独定得慢得多 8–15 秒，因为它改的是
  账号状态而不是读数据，且实测 1.5–3.5 秒串行仍会成片中招；另外还有批上限与日上限。

风控是冷却型、偏 IP 级（bili-sync 实测换凭据无效），所以撞上之后唯一有效的动作是
「停 + 等」，两条车道各有独立暂停状态，互不牵连；但它们不能并行跑——同一个 sqlite
文件的写锁是库级的。成功的响应按 key 缓存，中断后重跑只补缺的部分。
"""
import argparse
import json
import random
import sqlite3
import time
from datetime import date, datetime
from pathlib import Path

import httpx

STATE_FILE = Path(__file__).resolve().parent / ".bili-read-state.sqlite3"

LANES = ("account", "anon")

# 间隔不是拍脑袋定的，参照 bili-sync（同一作者、跑在生产环境的 B 站同步工具）README
# 「风控与限流须知」里验证过的包线：动态/列表接口 250ms、评论 400ms、全局「每 250ms
# 最多 4 个请求」、遇风控终止本轮。本闸门是串行的，0.25–0.4s 间隔 ≈ 2.5–4 次/秒，
# 正好落在它验证过的范围内。
READ_INTERVAL = {
    "account": (0.25, 0.4),
    "anon": (0.3, 0.5),   # 实测 card/upstat 在 0.2s 间隔下仍全过，这里留余量
}

# 写（取关）不走这条路：它改的是账号状态，且实测 1.5–3.5s 串行仍会成片中招，
# 所以单独定得慢得多，另外还有批上限与日上限。
WRITE_MIN_INTERVAL = 8.0
WRITE_MAX_INTERVAL = 15.0

# 冷却：风控是 IP 级冷却型的，bili-sync 的观测是 30 分钟～1 小时自解，换凭据无效。
COOLDOWN = {"account": 30 * 60, "anon": 30 * 60}

MIN_COOLDOWN = COOLDOWN["account"]
MIN_INTERVAL, MAX_INTERVAL = READ_INTERVAL["account"]   # 兼容旧引用

CACHE_TTL = 24 * 60 * 60   # 投稿 / 粉丝：一天内算新鲜
PAGE_TTL = 60 * 60         # 关注列表分页：一小时，避免翻页期间列表变化
DAILY_WRITE_MAX = 100      # 取关这类写操作的每日上限

RISK_CODES = (-352, -412)
RISK_STATUS = (403, 412, 429)
RISK_WORDS = ("风控", "频繁", "访问受限")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


class RiskControlError(RuntimeError):
    """平台风控信号：整批立即停手，绝不重试。"""


class ApiError(RuntimeError):
    """业务错误码或网络故障：单条跳过，不算风控。"""


ApiReadError = ApiError  # 旧名字，保留兼容


class BudgetError(RuntimeError):
    """当天的写操作配额已用完（或本批超过上限）。"""


def connection():
    db = sqlite3.connect(STATE_FILE, timeout=60, isolation_level=None)
    db.execute("CREATE TABLE IF NOT EXISTS gates "
               "(lane TEXT PRIMARY KEY, next_at REAL, paused TEXT, until_at REAL)")
    for lane in LANES:
        db.execute("INSERT OR IGNORE INTO gates VALUES (?, 0, '', 0)", (lane,))
    # 旧版本只有一条全局 gate 记录：把它的暂停状态迁移到 account 车道后丢掉旧表。
    legacy = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='gate'").fetchone()
    if legacy:
        row = db.execute("SELECT next_at, paused, until_at FROM gate WHERE id=1").fetchone()
        if row:
            next_at, paused, until_at = row
            db.execute("UPDATE gates SET next_at=?, paused=?, until_at=? WHERE lane='account'",
                       (next_at or 0, paused or "", until_at or 0))
        db.execute("DROP TABLE gate")
    db.execute("CREATE TABLE IF NOT EXISTS cache (scope TEXT, key TEXT, body TEXT, at REAL, PRIMARY KEY (scope, key))")
    db.execute("CREATE TABLE IF NOT EXISTS counter (day TEXT, kind TEXT, n INTEGER, PRIMARY KEY (day, kind))")
    return db


# ---------------------------------------------------------------- 缓存


def fresh(at, ttl=CACHE_TTL):
    return isinstance(at, (int, float)) and 0 <= time.time() - at < ttl


def cached(scope, key, ttl=CACHE_TTL):
    """取缓存；过期或不存在返回 None。读缓存不经过闸门，暂停中也能用来出结果。"""
    db = connection()
    try:
        row = db.execute("SELECT body, at FROM cache WHERE scope=? AND key=?", (scope, str(key))).fetchone()
    finally:
        db.close()
    if not row or not fresh(row[1], ttl):
        return None
    try:
        return json.loads(row[0])
    except ValueError:
        return None


def store(scope, key, body):
    db = connection()
    try:
        db.execute(
            "INSERT OR REPLACE INTO cache (scope, key, body, at) VALUES (?, ?, ?, ?)",
            (scope, str(key), json.dumps(body, ensure_ascii=False), time.time()),
        )
    finally:
        db.close()


def forget(scope=None):
    """丢弃缓存；不传 scope 就清空（用于强制重抓）。"""
    db = connection()
    try:
        if scope:
            db.execute("DELETE FROM cache WHERE scope=?", (scope,))
        else:
            db.execute("DELETE FROM cache")
    finally:
        db.close()


def cache_stats():
    db = connection()
    try:
        return dict(db.execute("SELECT scope, COUNT(*) FROM cache GROUP BY scope").fetchall())
    finally:
        db.close()


# ---------------------------------------------------------------- 配额


def day():
    return date.today().isoformat()


def used(kind):
    db = connection()
    try:
        row = db.execute("SELECT n FROM counter WHERE day=? AND kind=?", (day(), kind)).fetchone()
        return row[0] if row else 0
    finally:
        db.close()


# ---------------------------------------------------------------- 闸门


def _pause(db, lane, reason):
    db.execute("UPDATE gates SET paused=?, until_at=? WHERE lane=?",
               (reason, time.time() + COOLDOWN[lane], lane))


def _call(client, send, lane, low, high, raise_on_business, counter=None, daily_max=None):
    db = connection()
    data = None
    ok = False
    try:
        # 整个请求期间持有写锁：同一车道内多个脚本不可能同时打接口。
        db.execute("BEGIN IMMEDIATE")
        next_at, paused, _ = db.execute(
            "SELECT next_at, paused, until_at FROM gates WHERE lane=?", (lane,)
        ).fetchone()
        if paused:
            raise RiskControlError(f"[{lane}] 已暂停（{paused}）；不会自动恢复或重试")
        if counter and daily_max is not None:
            spent = db.execute("SELECT n FROM counter WHERE day=? AND kind=?", (day(), counter)).fetchone()
            spent = spent[0] if spent else 0
            if spent >= daily_max:
                raise BudgetError(f"今日 {counter} 已做 {spent} 次，达到上限 {daily_max}；今天到此为止")
        delay = next_at - time.time()
        if delay > 0:
            time.sleep(delay)
        try:
            response = send()
            if response.status_code in RISK_STATUS:
                raise RiskControlError(f"HTTP {response.status_code}")
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise ApiError("接口返回格式异常，未重试")
            message = str(data.get("message") or data.get("msg") or "")
            if data.get("code") in RISK_CODES or any(word in message for word in RISK_WORDS):
                raise RiskControlError(f"接口 code={data.get('code')}")
            if raise_on_business and data.get("code") != 0:
                raise ApiError(f"接口 code={data.get('code')}，未重试")
            ok = True
        except RiskControlError as error:
            _pause(db, lane, str(error))
            raise
        except (httpx.HTTPError, ValueError) as error:
            raise ApiError(f"请求失败（{type(error).__name__}），未重试") from error
        finally:
            db.execute("UPDATE gates SET next_at=? WHERE lane=?",
                       (time.time() + random.uniform(low, high), lane))
            if ok and counter:
                db.execute(
                    "INSERT INTO counter (day, kind, n) VALUES (?, ?, 1) "
                    "ON CONFLICT(day, kind) DO UPDATE SET n = n + 1",
                    (day(), counter),
                )
            db.commit()
        return data
    finally:
        db.close()


def get_json(client, url, params=None, headers=None, lane="account"):
    """读接口。lane='anon' 用于不带 Cookie 的公开接口。"""
    low, high = READ_INTERVAL[lane]
    return _call(
        client,
        lambda: client.get(url, params=params, headers=headers, timeout=20),
        lane,
        low,
        high,
        raise_on_business=True,
    )


def post_json(client, url, form=None, headers=None, counter=None, daily_max=DAILY_WRITE_MAX):
    """写接口：固定走 account 车道，8–15 秒一次，附带每日配额。

    不对业务错误码抛异常——取关时要拿到 code/message 写日志，由调用方判断。
    """
    return _call(
        client,
        lambda: client.post(url, data=form, headers=headers, timeout=20),
        "account",
        WRITE_MIN_INTERVAL,
        WRITE_MAX_INTERVAL,
        raise_on_business=False,
        counter=counter,
        daily_max=daily_max,
    )


# ---------------------------------------------------------------- 暂停 / 恢复


def pause(reason, lane="account"):
    db = connection()
    try:
        db.execute("BEGIN IMMEDIATE")
        _pause(db, lane, reason)
        db.commit()
    finally:
        db.close()


def resume(lane=None):
    """只改本地状态；必须用户明确要求才调用。返回每个车道的结果说明。"""
    lanes = [lane] if lane else list(LANES)
    notes = []
    for name in lanes:
        db = connection()
        try:
            db.execute("BEGIN IMMEDIATE")
            paused, until = db.execute(
                "SELECT paused, until_at FROM gates WHERE lane=?", (name,)
            ).fetchone()
            if not paused:
                notes.append(f"{name}：本来就没暂停")
            elif time.time() < until:
                left = (until - time.time()) / 60
                notes.append(f"{name}：冷却还没结束，还要等 {left:.0f} 分钟")
            else:
                db.execute("UPDATE gates SET paused='', until_at=0 WHERE lane=?", (name,))
                notes.append(f"{name}：已解除")
            db.commit()
        finally:
            db.close()
    return notes


def status():
    db = connection()
    try:
        rows = db.execute("SELECT lane, next_at, paused, until_at FROM gates").fetchall()
    finally:
        db.close()
    for lane, next_at, paused, until in rows:
        low, high = READ_INTERVAL[lane]
        head = f"[{lane}] 读 {low:g}–{high:g}s、冷却 {COOLDOWN[lane] / 60:.0f} 分钟"
        if paused:
            when = datetime.fromtimestamp(until).astimezone().isoformat(timespec="seconds")
            print(f"{head} —— 已暂停：{paused}（最早 {when} 可手动解除）")
        else:
            print(f"{head} —— 未暂停")
        left = next_at - time.time()
        if left > 0:
            print(f"        下一次请求最早也要等 {left:.0f} 秒")
    scopes = cache_stats()
    print("缓存：" + ("、".join(f"{scope} {count} 条" for scope, count in sorted(scopes.items())) if scopes else "空"))
    print(f"今日写操作：{used('unfollow')} / {DAILY_WRITE_MAX}")


# ---------------------------------------------------------------- 工具


def save_json(path, data):
    """原子落盘：先写 .tmp 再替换，中断不会留下半截 JSON。"""
    path = Path(path)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resume", nargs="?", const="", metavar="LANE",
                        help="用户明确要求后解除本地暂停；不指定车道则解全部（不发网络请求）")
    parser.add_argument("--forget-cache", nargs="?", const="", metavar="SCOPE",
                        help="丢弃缓存（不指定 scope 则全清），让下次重抓")
    args = parser.parse_args()
    if args.resume is not None:
        target = args.resume or None
        if target and target not in LANES:
            parser.exit(2, f"车道只能是 {'/'.join(LANES)}\n")
        notes = resume(target)
        for note in notes:
            print(note)
        if all("还要等" in note for note in notes):
            parser.exit(2, "本地最短冷却时间尚未结束；不会请求接口试探恢复\n")
        print("解除的只是本地暂停，不代表平台已放过，仍需维持低频")
    elif args.forget_cache is not None:
        forget(args.forget_cache or None)
        print("缓存已清空：" + (args.forget_cache or "全部"))
    else:
        status()
