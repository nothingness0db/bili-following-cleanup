"""取关这条写路径的统一入口：批上限、日上限、撞上风控就整批停。

`unfollow.py` 与 `retry_unfollow.py` 都走这里，避免出现两套互相矛盾的退避重试逻辑。
写入一律交给 `bili_read.post_json`：8–15 秒一次、全串行、与采集共用同一个熔断闸门，
所以采集侧一旦暂停，取关也会被一起挡住。
"""
import json
import sys
from pathlib import Path

import bili_read

MODIFY_URL = "https://api.bilibili.com/x/relation/modify"
BATCH_MAX = 50                          # 单次脚本最多取关多少个，防止一口气打死
DAILY_MAX = bili_read.DAILY_WRITE_MAX   # 每天最多取关多少次（跨批次累计），与闸门共用同一个常数
LOGIN_CODES = (-101, -111)


def jct_from(cookie):
    for part in cookie.split(";"):
        if "=" in part:
            name, _, value = part.partition("=")
            if name.strip() == "bili_jct":
                return value.strip()
    sys.exit("Cookie 中找不到 bili_jct（取关需要的 csrf token）。")


def load_log(log_path):
    path = Path(log_path)
    if not path.exists():
        return []
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return []
    return [r for r in rows if isinstance(r, dict)]


def record(rows, entry):
    """按 mid 覆盖式记录，保证日志里每个号只有最新一条。"""
    mid = str(entry.get("mid"))
    rows[:] = [r for r in rows if str(r.get("mid")) != mid]
    rows.append(entry)
    return rows


def unfollow(client, jct, mid):
    return bili_read.post_json(
        client,
        MODIFY_URL,
        form={"fid": mid, "act": "2", "re_src": "11", "csrf": jct},
        headers={"Referer": f"https://space.bilibili.com/{mid}/fans/follow"},
        counter="unfollow",
        daily_max=DAILY_MAX,
    )


def run(client, jct, mids, names, log_path, limit=BATCH_MAX):
    """串行取关。返回 (本次处理的条数, 停止原因或空串)。

    风控 / 登录失效 / 日上限都会立刻停下整批；日志累积保留历史，重跑时自动跳过已成功的，
    所以「补剩下的」就是再跑一次。
    """
    history = load_log(log_path)
    already = {str(r.get("mid")) for r in history if r.get("ok")}
    todo = [str(mid) for mid in mids if str(mid) not in already]
    batch = todo[:limit]
    rest = len(todo) - len(batch)

    if already:
        print(f"日志里已成功取关 {len(already)} 个，本次跳过")
    if rest > 0:
        print(f"本次只做前 {len(batch)} 个（批上限 {limit}），还剩 {rest} 个留到下一批")
    if not batch:
        print("没有需要处理的 mid。")
        return 0, ""

    stopped = ""
    for i, mid in enumerate(batch, 1):
        name = names.get(mid, "")
        try:
            data = unfollow(client, jct, mid)
        except bili_read.RiskControlError as error:
            stopped = f"触发风控，整批已停止：{error}"
            record(history, {"mid": mid, "uname": name, "ok": False, "code": "risk", "message": str(error)})
            bili_read.save_json(log_path, history)
            break
        except bili_read.BudgetError as error:
            stopped = str(error)
            break
        except bili_read.ApiError as error:
            record(history, {"mid": mid, "uname": name, "ok": False, "code": "error", "message": str(error)})
            print(f"[{i}/{len(batch)}] {mid} {name} -> 跳过：{error}")
            bili_read.save_json(log_path, history)
            continue

        code = data.get("code")
        ok = code == 0
        record(history, {"mid": mid, "uname": name, "ok": ok, "code": code, "message": data.get("message")})
        print(f"[{i}/{len(batch)}] {mid} {name} -> " + ("OK" if ok else f"失败 code={code} {data.get('message')}"))
        # 逐条落盘：中途 Ctrl-C 或断电也不会丢已做的记录。
        bili_read.save_json(log_path, history)

        if code in LOGIN_CODES:
            stopped = f"登录态失效（code={code}），已停止。Cookie 可能过期了"
            break

    bili_read.save_json(log_path, history)
    return len(batch), stopped
