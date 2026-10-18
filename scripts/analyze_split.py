"""把 combined.json 切成分类输入块。

分类阶段只读这里生成的 aXX.json；口径固定在 classify_rubric.md，避免每次
重跑时由 agent 临时写 prompt，导致类型定义漂移（例如「社交礼貌关注」消失、
「低频兴趣」变成万能兜底）。

用法：
    python analyze_split.py [块数]      # 默认 4 块
"""

import json
import shutil
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
OUT = BASE / "chunks_analysis"
RECENT_TITLES = 8  # 定位只看最近 8 条；完整 20 条留给按需核对
N = int(sys.argv[1]) if len(sys.argv) > 1 else 4

TYPE_NAMES = ["保留", "退坑遗产", "信息重复", "过期工具人", "社交礼貌关注",
              "内容质量退化", "低频兴趣", "情绪负收益", "历史纪念品",
              "内容转向", "商业内容过多", "账号迁移／失效"]


def tokens(text):
    """粗粒度中文标签相似度：去掉分隔符后取字符二元组。"""
    text = "".join(ch for ch in (text or "") if ch.isalnum() or "\u4e00" <= ch <= "\u9fff")
    return {text[i:i + 2] for i in range(len(text) - 1)} if len(text) > 1 else {text}


def build_similar(rows):
    """跨全部账号找疑似同类：共享细分标签优先，其次标签字面相近。"""
    meta = []
    for r in rows:
        meta.append({
            "mid": str(r["mid"]),
            "uname": r.get("uname", ""),
            "label": r.get("label", ""),
            "tags": set(r.get("tags") or []),
            "tok": tokens(r.get("label", "")),
            "rank": r.get("visit_rank"),
        })

    similar = {m["mid"]: [] for m in meta}
    for i, a in enumerate(meta):
        scored = []
        for j, b in enumerate(meta):
            if i == j or not a["label"] or not b["label"]:
                continue
            if a["label"] in ("资料不足", "待分析") or b["label"] in ("资料不足", "待分析"):
                continue
            shared = a["tags"] & b["tags"]
            union = a["tags"] | b["tags"]
            jaccard = len(shared) / len(union) if union else 0.0
            label_sim = (len(a["tok"] & b["tok"]) / len(a["tok"] | b["tok"])
                         if a["tok"] and b["tok"] else 0.0)
            # 至少要有一个共享细分标签，或标签字面高度接近；同领域宽泛标签不算。
            if not shared and label_sim < 0.3:
                continue
            score = len(shared) * 3 + jaccard + label_sim
            scored.append((score, b, sorted(shared)))
        scored.sort(key=lambda x: -x[0])
        similar[a["mid"]] = [
            {"mid": b["mid"], "uname": b["uname"], "label": b["label"],
             "shared_tags": shared}
            for _, b, shared in scored[:3]
        ]
    return similar


def slim(r, similar, rank_pct, fans_pct):
    videos = r.get("videos") or []
    total = r.get("video_total")
    return {
        "mid": str(r["mid"]),
        "uname": r.get("uname", ""),
        "sign": r.get("sign", ""),
        "official": r.get("official", ""),
        "label": r.get("label", ""),
        "tags": r.get("tags") or [],
        "content_reason": r.get("content_reason") or r.get("reason", ""),
        "confidence": r.get("confidence"),
        "evidence_titles": r.get("evidence_titles") or [],
        "videos": videos[:RECENT_TITLES],
        "video_total": total if isinstance(total, int) else len(videos),
        "last_days": r.get("last_days"),
        "fans": r.get("fans"),
        "visit_rank": r.get("visit_rank"),
        "rank_pct": rank_pct,
        "fans_pct": fans_pct,
        "similar_accounts": similar.get(str(r["mid"]), []),
    }


def percentiles(rows):
    """rank_pct：0=最常访问第 1；1=最后一名。fans_pct：0=粉丝最少；1=最多。"""
    ranks = {str(r["mid"]): r.get("visit_rank") for r in rows}
    valid = [v for v in ranks.values() if isinstance(v, int) and v > 0]
    n = len(valid)
    rank_pct = {}
    for mid, v in ranks.items():
        rank_pct[mid] = round((v - 1) / (n - 1), 3) if isinstance(v, int) and n > 1 else None

    fans = sorted(r["fans"] for r in rows if isinstance(r.get("fans"), int))
    fans_pct = {}
    for r in rows:
        mid, f = str(r["mid"]), r.get("fans")
        if isinstance(f, int) and len(fans) > 1:
            less = sum(1 for x in fans if x < f)
            fans_pct[mid] = round(less / (len(fans) - 1), 3)
        else:
            fans_pct[mid] = None
    return rank_pct, fans_pct


def main():
    rows = json.loads((BASE / "combined.json").read_text(encoding="utf-8"))
    OUT.mkdir(exist_ok=True)
    for old in OUT.glob("a*.json"):
        old.unlink()

    similar = build_similar(rows)
    rank_pct, fans_pct = percentiles(rows)
    all_rows = [{
        "mid": str(r["mid"]), "uname": r.get("uname", ""), "label": r.get("label", ""),
        "tags": r.get("tags") or [], "visit_rank": r.get("visit_rank"),
        "rank_pct": rank_pct.get(str(r["mid"])),
        "fans": r.get("fans"), "fans_pct": fans_pct.get(str(r["mid"])),
        "video_total": r.get("video_total"), "last_days": r.get("last_days"),
    } for r in rows]
    (OUT / "all_accounts.json").write_text(
        json.dumps(all_rows, ensure_ascii=False, indent=1), encoding="utf-8")

    # 兴趣访谈只供人类参考，不再拷进分类输入：分类只看账号本身，
    # 避免「用户说过会看宅舞」变成所有宅舞号一律保留。
    stale_profile = OUT / "interest_profile.json"
    if stale_profile.exists():
        stale_profile.unlink()

    rubric = BASE / "classify_rubric.md"
    if rubric.exists():
        shutil.copy2(rubric, OUT / "classify_rubric.md")

    size = (len(rows) + N - 1) // N
    # 按 visit_rank 交错分块：combined.json 是按「最常访问」排序的，直接切片会让
    # 每块变成不同的「兴趣层」（第 1 块全是常看的、最后一块全是几乎不点的），
    # 各 subagent 的局部基准会漂移。交错后每块都覆盖头部/腰部和尾部。
    ordered = sorted(rows, key=lambda r: (r.get("visit_rank") is None,
                                          r.get("visit_rank") or 10 ** 9))
    buckets = [[] for _ in range(N)]
    for i, row in enumerate(ordered):
        buckets[i % N].append(row)
    for i in range(N):
        part = buckets[i]
        if not part:
            continue
        slim_rows = [slim(r, similar, rank_pct.get(str(r["mid"])), fans_pct.get(str(r["mid"])))
                     for r in part]
        (OUT / f"a{i:02d}.json").write_text(
            json.dumps(slim_rows, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"a{i:02d}.json  {len(part)} 条  ->  {OUT / ('a%02d.json' % i)}")

    print(f"全员索引 {OUT / 'all_accounts.json'}（{len(all_rows)} 条，判重复可跨块对比）")
    print(f"判定口径 {OUT / 'classify_rubric.md'}（每个分类 subagent 都要先读）")
    print("\n下一步：为每个 aXX.json 开一个 subagent，让它读 classify_rubric.md + aXX.json，"
          f"写 analyze_out_{'{XX}'}.json，然后运行 verify_analysis.py。")


if __name__ == "__main__":
    main()
