"""合并图专用标签并校验。

输入：`graph_tags/out_*.json`（每个 `{mid, tags:[{tag, weight}]}` 数组）
输出：`graph_tags.json`（`{mid: [{tag, weight}]}`），`visualize.py` 自动读取。

用法：
    python merge_graph_tags.py
"""

import glob
import json
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent
MIN_TAGS, MAX_TAGS = 6, 10
WEIGHT_MIN, WEIGHT_MAX = 0.2, 1.0


def main():
    rows = {str(r["mid"]): r for r in json.loads((BASE / "combined.json").read_text(encoding="utf-8"))}
    merged = {}
    for path in sorted(glob.glob(str(BASE / "graph_tags" / "out_*.json"))):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError(f"{path} 顶层应为数组")
        for item in data:
            mid = str(item["mid"])
            clean, seen = [], set()
            for tag in item.get("tags") or []:
                if isinstance(tag, str):
                    tag, weight = tag, 1.0
                else:
                    tag, weight = tag.get("tag"), tag.get("weight", 1.0)
                tag = str(tag).strip()
                if not tag or tag in seen:
                    continue
                seen.add(tag)
                clean.append({"tag": tag,
                              "weight": round(max(WEIGHT_MIN, min(WEIGHT_MAX, float(weight))), 2)})
            if not MIN_TAGS <= len(clean) <= MAX_TAGS:
                raise ValueError(f"{mid} 标签数 {len(clean)} 不在 {MIN_TAGS}–{MAX_TAGS}")
            if mid not in rows:
                raise ValueError(f"{mid} 不在 combined.json")
            if mid in merged:
                raise ValueError(f"重复 mid {mid}")
            merged[mid] = clean

    missing = set(rows) - set(merged)
    if missing:
        raise ValueError(f"缺 {len(missing)} 个账号：{sorted(missing)[:5]}")
    (BASE / "graph_tags.json").write_text(
        json.dumps(merged, ensure_ascii=False, indent=1), encoding="utf-8")

    all_tags = [t["tag"] for tags in merged.values() for t in tags]
    counts = Counter(all_tags)
    avg = sum(len(v) for v in merged.values()) / len(merged)
    print(f"覆盖 {len(merged)}，平均 {avg:.2f} 个标签/人，"
          f"唯一 {len(counts)}，只出现一次 {sum(1 for n in counts.values() if n == 1)}")
    print("top:", counts.most_common(12))
    print(f"-> {BASE / 'graph_tags.json'}")


if __name__ == "__main__":
    main()
