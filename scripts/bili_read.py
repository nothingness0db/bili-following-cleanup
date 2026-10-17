"""B站接口的统一闸门：串行限速 + 全局熔断 + 成功响应缓存。

- 读（GET）每次请求间隔 3–6 秒，写（POST）8–15 秒，全部单线程串行。
- 所有脚本共用同一个 sqlite 闸门：任一脚本撞上风控，整批立刻停手并全部暂停 30 分钟。
- 撞上风控就**只停不重试**：不换接口、不换 UA、不缩短间隔去试探。
- 成功的响应按 key 缓存（投稿按 mid、粉丝按 mid、关注列表按页），重跑时只补还没抓到的
  部分，不会因为中途中断而从头再来。
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

MIN_INTERVAL = 3.0
MAX_INTERVAL = 6.0
WRITE_MIN_INTERVAL = 8.0
WRITE_MAX_INTERVAL = 15.0
MIN_COOLDOWN = 30 * 60

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
    db.execute("CREATE TABLE IF NOT EXISTS gate (id INTEGER PRIMARY KEY, next_at REAL, paused TEXT, until_at REAL)")
    db.execute("INSERT OR IGNORE INTO gate VALUES (1, 0, '', 0)")
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


def _pause(db, reason):
    db.execute("UPDATE gate SET paused=?, until_at=? WHERE id=1", (reason, time.time() + MIN_COOLDOWN))


def _call(client, send, low, high, raise_on_business, counter=None, daily_max=None):
    db = connection()
    data = None
    ok = False
    try:
        # 整个请求期间持有写锁：多个脚本不可能同时打接口。
        db.execute("BEGIN IMMEDIATE")
        next_at, paused, _ = db.execute("SELECT next_at, paused, until_at FROM gate WHERE id=1").fetchone()
        if paused:
            raise RiskControlError(f"已暂停（{paused}）；不会自动恢复或重试")
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
            _pause(db, str(error))
            raise
        except (httpx.HTTPError, ValueError) as error:
            raise ApiError(f"请求失败（{type(error).__name__}），未重试") from error
        finally:
            db.execute(
                "UPDATE gate SET next_at=? WHERE id=1",
                (time.time() + random.uniform(low, high),),
            )
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


def get_json(client, url, params=None, headers=None):
    """读接口：3–6 秒一次，业务错误码抛 ApiError，风控抛 RiskControlError。"""
    return _call(
        client,
        lambda: client.get(url, params=params, headers=headers, timeout=20),
        MIN_INTERVAL,
        MAX_INTERVAL,
        raise_on_business=True,
    )


def post_json(client, url, form=None, headers=None, counter=None, daily_max=DAILY_WRITE_MAX):
    """写接口：8–15 秒一次，附带每日配额；风控仍然立刻停手。

    不对业务错误码抛异常——取关时要拿到 code/message 写日志，由调用方判断。
    """
    return _call(
        client,
        lambda: client.post(url, data=form, headers=headers, timeout=20),
        WRITE_MIN_INTERVAL,
        WRITE_MAX_INTERVAL,
        raise_on_business=False,
        counter=counter,
        daily_max=daily_max,
    )


# ---------------------------------------------------------------- 暂停 / 恢复


def pause(reason):
    db = connection()
    try:
        db.execute("BEGIN IMMEDIATE")
        _pause(db, reason)
        db.commit()
    finally:
        db.close()


def resume():
    """只改本地状态；必须用户明确要求才调用。"""
    db = connection()
    try:
        db.execute("BEGIN IMMEDIATE")
        until = db.execute("SELECT until_at FROM gate WHERE id=1").fetchone()[0]
        if time.time() < until:
            raise RiskControlError("本地最短冷却时间尚未结束；不会请求接口试探恢复")
        db.execute("UPDATE gate SET paused='', until_at=0 WHERE id=1")
        db.commit()
    finally:
        db.close()


def status():
    db = connection()
    try:
        next_at, paused, until = db.execute("SELECT next_at, paused, until_at FROM gate WHERE id=1").fetchone()
    finally:
        db.close()
    if paused:
        print(f"采集/操作已暂停：{paused}")
        print("最早可手动解除：" + datetime.fromtimestamp(until).astimezone().isoformat(timespec="seconds"))
    else:
        print("未暂停：读 3–6 秒一次、写 8–15 秒一次，全串行")
    left = next_at - time.time()
    if left > 0:
        print(f"下一次请求最早也要等 {left:.0f} 秒")
    scopes = cache_stats()
    if scopes:
        print("缓存：" + "、".join(f"{scope} {count} 条" for scope, count in sorted(scopes.items())))
    else:
        print("缓存：空")
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
    parser.add_argument("--resume", action="store_true", help="用户明确要求后，解除本地暂停；不发网络请求")
    parser.add_argument("--forget-cache", nargs="?", const="", metavar="SCOPE", help="丢弃缓存（不指定 scope 则全清），让下次重抓")
    args = parser.parse_args()
    if args.resume:
        try:
            resume()
        except RiskControlError as error:
            parser.exit(2, str(error) + "\n")
        print("已解除本地暂停；不代表平台限制已解除，后续仍按低频采集")
    elif args.forget_cache is not None:
        forget(args.forget_cache or None)
        print("缓存已清空：" + (args.forget_cache or "全部"))
    else:
        status()
