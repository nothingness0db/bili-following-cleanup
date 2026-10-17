"""匿名接口的速率探针：测「不带 Cookie 的请求」能打多快。

用途：`fetch_fans.py` 是免登录的，值得知道它的真实容忍度，好定间隔。

安全边界（重要）：
- **完全不读 cookie.txt**，请求头里也没有任何登录态。最坏的后果是本机 IP 被临时限流，
  不会牵连账号。
- 用不同 mid 轮流请求，避免 CDN 缓存把结果染成「看起来没被限」。
- 一旦出现风控信号立刻停止整轮探测，**不硬顶**。

跑法：
    python probe.py                      # 逐档加速，找到第一档被挡
    python probe.py --endpoint upstat    # 测 /x/space/upstat
    python probe.py --interval 1.0 --count 100   # 定点持续压测
"""
import argparse
import statistics
import sys
import time

import httpx

CARD = "https://api.bilibili.com/x/web-interface/card"
UPSTAT = "https://api.bilibili.com/x/space/upstat"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Referer": "https://www.bilibili.com/"}

# 早期真实账号的 mid，各不相同，避免缓存命中
MIDS = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20,
        21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36]
RISK_CODES = (-352, -412)
RISK_STATUS = (403, 412, 429)

RAMP = [(1.5, 3), (1.0, 4), (0.7, 4), (0.5, 4), (0.3, 4), (0.2, 4)]


def one(client, endpoint, mid):
    url, params = (CARD, {"mid": mid, "photo": "false"}) if endpoint == "card" else (UPSTAT, {"mid": mid})
    started = time.time()
    response = client.get(url, params=params)
    latency = time.time() - started
    if response.status_code in RISK_STATUS:
        return "risk", f"HTTP {response.status_code}", latency
    try:
        data = response.json()
    except ValueError:
        return "bad", f"非 JSON（HTTP {response.status_code}）", latency
    code = data.get("code")
    if code in RISK_CODES:
        return "risk", f"code={code}", latency
    if code != 0:
        return "other", f"code={code}", latency  # 例如 mid 不存在，不算风控
    return "ok", "", latency


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", choices=("card", "upstat"), default="card")
    parser.add_argument("--interval", type=float, help="定点模式：固定间隔（秒）")
    parser.add_argument("--count", type=int, default=30, help="定点模式的请求数")
    args = parser.parse_args()

    if not args.interval:
        total = sum(n for _, n in RAMP)
        print(f"逐档加速探测 {args.endpoint}：{len(RAMP)} 档、共 {total} 个匿名请求")
        print("不带 Cookie，只可能影响本机 IP；出现风控立刻停止。\n")
    else:
        print(f"定点压测 {args.endpoint}：间隔 {args.interval}s × {args.count} 个匿名请求\n")

    plan = [(args.interval, args.count)] if args.interval else RAMP
    tripped = None
    with httpx.Client(headers=HEADERS, timeout=15, follow_redirects=True) as client:
        cursor = 0
        for interval, count in plan:
            latencies, others = [], 0
            outcome = "ok"
            for i in range(count):
                mid = MIDS[cursor % len(MIDS)]
                cursor += 1
                try:
                    kind, detail, latency = one(client, args.endpoint, mid)
                except httpx.HTTPError as error:
                    kind, detail, latency = "bad", type(error).__name__, 0.0
                latencies.append(latency)
                if kind == "ok":
                    pass
                elif kind == "other":
                    others += 1
                elif kind in ("risk", "bad"):
                    outcome = f"{kind}: {detail}"
                    break
                if i + 1 < count:
                    time.sleep(interval)
            middle = statistics.median(latencies) if latencies else 0
            note = f"，{others} 个非风控错误码（mid 可能不存在）" if others else ""
            print(f"  间隔 {interval:>4.1f}s  发了 {len(latencies):>2} 个  "
                  f"中位延迟 {middle * 1000:>5.0f}ms  -> {'全过' if outcome == 'ok' else outcome}{note}")
            if outcome != "ok":
                tripped = (interval, outcome)
                break
            if len(latencies) < count:
                break

    print()
    if tripped:
        interval, outcome = tripped
        print(f"被挡在第一档：间隔 {interval}s（{outcome}）")
        print("结论：匿名请求一样会被 -352 挡，只是后果落在 IP 上（通常过一阵自动恢复），不动账号。")
        return 1
    print("全部档位都过了 —— 这就是本次探测的上限边界之外，真实上限还要更高。")
    print("注意：这只能说明「瞬时容忍度」，测不出「一天能抽多少」。取间隔时别贴着实测边缘用。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
