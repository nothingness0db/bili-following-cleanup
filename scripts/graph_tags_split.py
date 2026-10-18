"""把 20 条投稿标题切成图专用标签的输入块。

图专用标签只喂 `map.html` 的关系图，不改清理分类；最终由 `merge_graph_tags.py`
合并成 `graph_tags.json`，`visualize.py` 会自动读取。

用法：
    python graph_tags_split.py [块数]      # 默认 4 块
"""

import json
import sys
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent
OUT = BASE / "graph_tags"
N = int(sys.argv[1]) if len(sys.argv) > 1 else 4
TITLES = 20


def main():
    rows = json.loads((BASE / "combined.json").read_text(encoding="utf-8"))
    OUT.mkdir(exist_ok=True)
    for old in OUT.glob("input_*.json"):
        old.unlink()

    counts = Counter(tag for row in rows for tag in (row.get("tags") or []))
    seed = [{"tag": tag, "count": n} for tag, n in counts.most_common()]
    (OUT / "tag_seed.json").write_text(
        json.dumps(seed, ensure_ascii=False, indent=1), encoding="utf-8")

    # 按最常访问名次交错切块：每块都覆盖头部/腰部/尾部，标签密度更均匀。
    ordered = sorted(rows, key=lambda r: (r.get("visit_rank") is None,
                                          r.get("visit_rank") or 10 ** 9))
    buckets = [[] for _ in range(N)]
    for i, row in enumerate(ordered):
        buckets[i % N].append(row)

    for i, part in enumerate(buckets):
        if not part:
            continue
        slim = [{
            "mid": str(r["mid"]), "uname": r.get("uname", ""),
            "sign": r.get("sign", ""), "label": r.get("label", ""),
            "tags": r.get("tags") or [], "visit_rank": r.get("visit_rank"),
            "videos": (r.get("videos") or [])[:TITLES],
        } for r in part]
        (OUT / f"input_{i:02d}.json").write_text(
            json.dumps(slim, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"input_{i:02d}.json  {len(slim)} 条")

    print(f"种子标签 {OUT / 'tag_seed.json'}（{len(seed)} 个）")
    print("下一步：每块开一个 subagent，读 tag_seed.json + input_XX.json，"
          "写 out_XX.json（每人 6–10 个带权标签），再跑 merge_graph_tags.py。")


if __name__ == "__main__":
    main()
