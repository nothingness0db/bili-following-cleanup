"""Build a standalone interest graph without changing source data or follows."""
import argparse
import base64
import hashlib
import json
import math
import os
from pathlib import Path
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

BASE = Path(__file__).resolve().parent
FRONTEND = BASE.parent / "frontend"


def numeric(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def visit_rank(row):
    value = numeric(row.get("visit_rank"))
    return value if value is not None and value > 0 and value.is_integer() else None


def avatar_mime(data):
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    raise ValueError("头像不是 JPEG、PNG 或 WebP")


def avatar_url_allowed(url):
    parts = urlsplit(url)
    return (parts.scheme == "https" and not parts.username and not parts.password
            and any(parts.hostname == host or (parts.hostname or "").endswith("." + host)
                    for host in ("hdslb.com", "biliimg.com")))


def prepare_avatars(rows, source, feature=None):
    """Join genuine avatars by UID; embed only the two opening portraits."""
    following_path = source.with_name("following.json")
    faces = {}
    if following_path.is_file():
        following = json.loads(following_path.read_text(encoding="utf-8-sig"))
        if isinstance(following, list):
            faces = {str(row.get("mid")): row.get("face") for row in following if isinstance(row, dict)}
    rows = [dict(row) for row in rows]
    for row in rows:
        if not row.get("face") and faces.get(str(row.get("mid"))):
            row["face"] = faces[str(row.get("mid"))]
    ranked = sorted((row for row in rows if visit_rank(row) is not None), key=visit_rank)
    first = ranked[0] if ranked else None
    pick = next((row for row in rows if isinstance(feature, dict)
                 and str(row.get("mid")) == str(feature.get("mid"))), None)
    featured = ([first] if first else []) + ([pick] if pick and pick is not first else [])
    cache = BASE / ".avatar-cache"
    for row in featured:
        url = row.get("face")
        if not isinstance(url, str) or not avatar_url_allowed(url):
            continue
        try:
            cache.mkdir(exist_ok=True)
            path = cache / (hashlib.sha256(url.encode()).hexdigest() + ".img")
            if path.is_file():
                data = path.read_bytes()
            else:
                request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urlopen(request, timeout=8) as response:
                    if not avatar_url_allowed(response.url):
                        raise ValueError("头像重定向地址无效")
                    data = response.read(2 * 1024 * 1024 + 1)
            if len(data) > 2 * 1024 * 1024:
                raise ValueError("头像超过 2 MB")
            mime = avatar_mime(data)
            path.write_bytes(data)
            row["avatar_data"] = "data:" + mime + ";base64," + base64.b64encode(data).decode("ascii")
        except (OSError, ValueError) as error:
            print(f"头像缓存跳过 {row.get('mid')}: {error}")
    return rows


def build(input_path=None, output_path=None, selector_path=None, feature_path=None):
    source = Path(input_path) if input_path else BASE / "combined.json"
    output = Path(output_path) if output_path else BASE / "map.html"
    selector = Path(selector_path) if selector_path else source.with_name("selector.html")
    feature_source = Path(feature_path) if feature_path else source.with_name("recap_feature.json")
    feature = None
    if feature_source.is_file():
        feature = json.loads(feature_source.read_text(encoding="utf-8-sig"))
    elif feature_path:
        raise FileNotFoundError(feature_source)
    rows = None
    if source.exists():
        rows = json.loads(source.read_text(encoding="utf-8-sig"))
        if not isinstance(rows, list):
            raise ValueError("输入应为账号数组（combined.json）")
        rows = prepare_avatars(rows, source, feature)
    elif input_path:
        raise FileNotFoundError(source)
    data = json.dumps(rows, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    feature_data = json.dumps(feature, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    html = html.replace('<script id="recap-feature" type="application/json">null</script>', '<script id="recap-feature" type="application/json">' + feature_data + '</script>')
    if selector.is_file():
        selector_document = json.dumps(selector.read_text(encoding="utf-8-sig"), ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
        html = html.replace('<script id="selector-document" type="application/json">null</script>', '<script id="selector-document" type="application/json">' + selector_document + '</script>')
        try:
            selector_url = quote(os.path.relpath(selector.resolve(), output.resolve().parent).replace(os.sep, "/"), safe="/")
        except ValueError:  # Different Windows drives.
            selector_url = selector.resolve().as_uri()
        html = html.replace(' data-selector-ready="pending" hidden', ' data-selector-ready="true" hidden')
        html = html.replace('__SELECTOR_URL__', selector_url)
    else:
        html = html.replace('__SELECTOR_URL__', '#')
    html = html.replace('<link rel="stylesheet" href="style.css">', '<style>' + (FRONTEND / "style.css").read_text(encoding="utf-8") + '</style>')
    html = html.replace('<link id="dark-theme" rel="stylesheet" href="theme-dark.css" media="(prefers-color-scheme: dark)">', '<style id="dark-theme" media="(prefers-color-scheme: dark)">' + (FRONTEND / "theme-dark.css").read_text(encoding="utf-8-sig") + '</style>')
    html = html.replace('<script src="app.js" defer></script>', '<script id="embedded-data" type="application/json">' + data + '</script>\n<script>' + (FRONTEND / "app.js").read_text(encoding="utf-8") + '</script>')
    html = html.replace('<script src="recap.js" defer></script>', '<script>' + (FRONTEND / "recap.js").read_text(encoding="utf-8") + '</script>')
    output.write_text(html, encoding="utf-8")
    print(f"已生成 {output} · {'演示数据' if rows is None else str(len(rows)) + ' 个账号'}")
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", help="关注数据 JSON，默认 scripts/combined.json")
    parser.add_argument("--output", help="输出 HTML，默认 scripts/map.html")
    parser.add_argument("--selector", help="勾选页面，默认与输入 JSON 同目录的 selector.html")
    parser.add_argument("--feature", help="Agent 挑选的第三段发现，默认与输入 JSON 同目录的 recap_feature.json")
    args = parser.parse_args()
    build(args.input, args.output, args.selector, args.feature)
