"""分类结果自检：覆盖率、类型映射、布尔一致性与分布异常。

用法：
    python verify_analysis.py

退出码：0 = 通过（可能有警告）；1 = 硬错误（缺人、重复、类型/字段非法）。
"""

import glob
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent
TYPE_NAMES = ["保留", "退坑遗产", "信息重复", "过期工具人", "社交礼貌关注",
              "内容质量退化", "低频兴趣", "情绪负收益", "历史纪念品",
              "内容转向", "商业内容过多", "账号迁移／失效"]
CUT_TYPES = {1, 2, 3, 4, 5, 6, 7, 9, 10, 11}
KEEP_TYPES = {0, 8}
ENTERTAINMENT = ("翻跳", "宅舞", "Cos", "cos", "同人", "翻唱", "舞台", "整活",
                 "Vlog", "vlog", "虚拟主播", "实况", "颜值", "生活", "日常")
INFO = ("教程", "攻略", "战术", "分析", "资讯", "评测", "讲解", "课程",
        "论文", "开发", "编程", "财经", "加密", "解说")


def load_expected():
    all_path = BASE / "chunks_analysis" / "all_accounts.json"
    if all_path.exists():
        rows = json.loads(all_path.read_text(encoding="utf-8"))
    else:
        rows = json.loads((BASE / "combined.json").read_text(encoding="utf-8"))
    return {str(r["mid"]): r for r in rows}


def main():
    expected = load_expected()
    files = sorted(glob.glob(str(BASE / "analyze_out_*.json")))
    if not files:
        sys.exit("没有找到 analyze_out_*.json")

    rows, errors, warnings = [], [], []
    short_reasons = []
    for path in files:
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception as error:  # noqa: BLE001
            errors.append(f"{Path(path).name}: 不是合法 JSON（{error}）")
            continue
        if not isinstance(data, list):
            errors.append(f"{Path(path).name}: 顶层不是数组")
            continue
        rows.extend((str(r.get("mid")), r, Path(path).name) for r in data)

    seen = Counter(mid for mid, _, _ in rows)
    for mid, n in seen.items():
        if n > 1:
            errors.append(f"mid {mid} 出现 {n} 次")
    missing = set(expected) - set(seen)
    extra = set(seen) - set(expected)
    if missing:
        errors.append(f"缺 {len(missing)} 个账号：{sorted(missing)[:8]}")
    if extra:
        errors.append(f"多出 {len(extra)} 个不在关注列表的 mid：{sorted(extra)[:8]}")

    for mid, r, name in rows:
        t = r.get("type")
        if not isinstance(t, int) or isinstance(t, bool) or not 0 <= t < len(TYPE_NAMES):
            errors.append(f"{name} {mid}: type 非法 {t!r}")
            continue
        if r.get("type_name") != TYPE_NAMES[t]:
            errors.append(f"{name} {mid}: type_name {r.get('type_name')!r} 应为 {TYPE_NAMES[t]!r}")
        if r.get("priority") not in ("高", "中", "低"):
            errors.append(f"{name} {mid}: priority 非法 {r.get('priority')!r}")
        if not isinstance(r.get("unfollow"), bool):
            errors.append(f"{name} {mid}: unfollow 不是布尔值 {r.get('unfollow')!r}")
        elif r["unfollow"] != (t in CUT_TYPES):
            errors.append(f"{name} {mid}: unfollow={r['unfollow']} 与类型 {t} 的策略不一致")
        if t == 2 and not (r.get("comparison_mids") or []):
            errors.append(f"{name} {mid}: 类型 2 缺少 comparison_mids")
        reason = r.get("reason") or ""
        if len(reason) < 30:
            short_reasons.append(mid)

    if short_reasons:
        warnings.append(
            f"{len(short_reasons)} 条 reason 少于 30 字（如 {', '.join(short_reasons[:5])}）："
            "理由要能让人核对，不要写模板短语")

    if errors:
        print("硬错误：")
        for e in errors[:40]:
            print("  ✗", e)
        if len(errors) > 40:
            print(f"  … 共 {len(errors)} 条")
        sys.exit(1)

    cnt = Counter(r["type"] for _, r, _ in rows)
    total = len(rows)
    print(f"\n覆盖 {len(seen)} / {len(expected)}，类型分布：")
    for t in range(len(TYPE_NAMES)):
        n = cnt.get(t, 0)
        print(f"  {t:>2} {TYPE_NAMES[t]:<8} {n:>4}  {n / total:>6.1%}"
              f"  {'切' if t in CUT_TYPES else '留'}")
    unfollow = sum(1 for _, r, _ in rows if r["unfollow"])
    print(f"\n建议取关 {unfollow} / {total}（{unfollow / total:.1%}）")

    # ---- 分布护栏：这些不是硬错误，但都是上次实际翻车的地方 ----
    def share(t):
        return cnt.get(t, 0) / total

    if cnt.get(4, 0) == 0:
        low_fans = [m for m, r in expected.items()
                    if isinstance(r.get("fans"), int) and r["fans"] <= 300]
        if len(low_fans) >= 5:
            warnings.append(
                f"类型 4 为 0，但有 {len(low_fans)} 个粉丝 ≤300 的账号——"
                "「社交礼貌关注」很可能整类被漏掉")
    if max(cnt.values()) / total > 0.45:
        t = cnt.most_common(1)[0][0]
        warnings.append(f"类型 {t} {TYPE_NAMES[t]} 占 {share(t):.1%}，超过 45%：像兜底桶")
    if share(0) < 0.20:
        warnings.append(f"保留只占 {share(0):.1%}，低于 20%：可能把「常看且没毛病」的号误切")
    if share(0) > 0.55:
        warnings.append(f"保留占 {share(0):.1%}，高于 55%：初评可能过于保守")
    if share(6) > 0.50:
        warnings.append(f"低频兴趣占 {share(6):.1%}，超过 50%：检查是否拿不准就塞 6，或没有用更具体的类型")

    dead = [r for _, r, _ in rows if r["type"] == 11]
    if dead:
        days = [expected[m].get("last_days") for m, r, _ in rows
                if r["type"] == 11 and isinstance(expected.get(m, {}).get("last_days"), int)]
        if days and statistics.median(days) < 365:
            warnings.append(
                f"类型 11 有 {len(dead)} 个，但停更天数中位数 {statistics.median(days):.0f} 天"
                "（<365）：不要把「停更几个月」判成账号失效")
    if share(2) > 0.20:
        warnings.append(f"信息重复占 {share(2):.1%}，超过 20%：确认只用于信息/知识型")

    bad2 = [m for m, r, _ in rows
            if r["type"] == 2
            and any(k in ((expected.get(m, {}).get("label") or "")
                          + " " + (expected.get(m, {}).get("sign") or ""))
                    for k in ENTERTAINMENT)
            and not any(k in ((expected.get(m, {}).get("label") or "")
                              + " " + (expected.get(m, {}).get("sign") or ""))
                        for k in INFO)]
    if bad2:
        warnings.append(f"有 {len(bad2)} 个娱乐/创作类账号被判成信息重复（类型 2 只用于信息/知识型）")

    weird4 = [m for m, r, _ in rows
              if r["type"] == 4
              and isinstance(expected.get(m, {}).get("fans"), int)
              and expected[m]["fans"] > 100000
              and (expected[m].get("video_total") or 0) > 500]
    if weird4:
        warnings.append(f"有 {len(weird4)} 个粉丝 >10 万、投稿 >500 的账号被判社交礼貌关注，建议复核")

    # 分块漂移：某块某类型占比远高于整体，说明 subagent 口径不一致
    by_file = defaultdict(Counter)
    for _, r, name in rows:
        by_file[name][r["type"]] += 1
    for name, c in sorted(by_file.items()):
        n = sum(c.values())
        for t, k in c.items():
            if n >= 30 and k / n > 0.55 and share(t) < 0.35:
                warnings.append(f"{name}: 类型 {t} 占 {k / n:.0%}，整体仅 {share(t):.0%}——分块口径漂移")

    print("\n自检：")
    if warnings:
        print(f"⚠ {len(warnings)} 条警告（建议复核，不阻塞）")
        for w in warnings:
            print("  -", w)
    else:
        print("✓ 无警告")

    report = {
        "total": total,
        "counts": {TYPE_NAMES[t]: cnt.get(t, 0) for t in range(len(TYPE_NAMES))},
        "unfollow": unfollow,
        "warnings": warnings,
    }
    (BASE / "chunks_analysis" / "verify_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n报告 -> {BASE / 'chunks_analysis' / 'verify_report.json'}")


if __name__ == "__main__":
    main()
