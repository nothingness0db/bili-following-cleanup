"""Build a standalone interest graph without changing source data or follows."""
import argparse
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
FRONTEND = BASE.parent / "frontend"


def build(input_path=None, output_path=None):
    source = Path(input_path) if input_path else BASE / "combined.json"
    output = Path(output_path) if output_path else BASE / "map.html"
    rows = None
    if source.exists():
        rows = json.loads(source.read_text(encoding="utf-8-sig"))
        if not isinstance(rows, list):
            raise ValueError("输入应为账号数组（combined.json）")
    elif input_path:
        raise FileNotFoundError(source)
    data = json.dumps(rows, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    html = html.replace('<link rel="stylesheet" href="style.css">', '<style>' + (FRONTEND / "style.css").read_text(encoding="utf-8") + '</style>')
    html = html.replace('<script src="app.js" defer></script>', '<script id="embedded-data" type="application/json">' + data + '</script>\n<script>' + (FRONTEND / "app.js").read_text(encoding="utf-8") + '</script>')
    output.write_text(html, encoding="utf-8")
    print(f"已生成 {output} · {'演示数据' if rows is None else str(len(rows)) + ' 个账号'}")
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", help="关注数据 JSON，默认 scripts/combined.json")
    parser.add_argument("--output", help="输出 HTML，默认 scripts/map.html")
    args = parser.parse_args()
    build(args.input, args.output)
