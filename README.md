# bili-following-cleanup

把 B 站「关注列表」整理成可筛选清单，并批量取关。适合关注了几百个人、想按「这人是做什么的」来清理的场景。

> 这是一个 opencode / Claude 技能（也是可直接运行的脚本集）。把本目录放进技能目录即可被 agent 加载使用；或按下面的步骤手动跑脚本。

## 它做什么

一条固定流水线，一次跑到底（只有「用户勾选」需要人工介入）：

1. **拉全量关注** —— 登录态分页读取，导出 JSON/CSV。
2. **抓投稿** —— 抓每人最近 6 个投稿标题。
3. **打标** —— 生成每个号的内容定位标签（推荐用 subagent 并行）。
4. **分类打分** —— 按 8 种取关判断给类型 + 优先级（推荐用 subagent 并行）。
5. **补粉丝量** —— 免登录接口，辅助判断「信息重复」。
6. **本地网页勾选** —— `selector.html`，搜索/按内容/类型/优先级勾选/导出待取关列表。
7. **独立兴趣图谱** —— `visualize.py` 生成 `map.html`：脑回路 / 兴趣星系 / 兴趣指纹，探索标签与 UP 主，导出高清图片。
8. **批量取关** —— 带随机延时 + 风控退避与重试。

## 原则：决定权归用户

工具只负责**分类和呈现**，不替用户决定。agent **不会**攒一份「建议取关名单」再问「全部取关行不行」——分类只是给人**自己挑**的参考，取关名单永远来自使用者自己勾选导出。

## 环境

- Python 3，`pip install httpx`
- 浏览器已登录 B 站

## 快速开始

```bash
cd scripts

# 1) 取 Cookie：本机有 Firefox 时直接提取（明文 cookies.sqlite）
python extract_cookie_firefox.py
#    Chrome/Edge 用户需手动：F12 -> 网络 -> 任意 api.bilibili.com 请求 -> Cookie 头，粘进 cookie.txt

# 2) 拉关注 + 抓投稿
python fetch_following.py
python fetch_videos.py
python split_chunks.py          # 再打标（推荐用 subagent）-> labels_XX.json

# 3) 出图：勾选网页 + 关注星图
python build_selector.py        # 打开 selector.html，勾选后导出 unfollow.txt
python visualize.py             # 打开 map.html（独立兴趣图谱）

# 4) 取关（先不带 --yes 会二次确认）
python unfollow.py
# 若出现 -352 风控：把失败 mid 写入 retry.txt
python retry_unfollow.py
```

## 目录

### 关注的形状 · 独立兴趣图谱

这是一层独立的视觉展示，不改变原有筛选、取关脚本和数据。

- **脑回路 / 兴趣星系 / 兴趣指纹**：同一份关注数据在三种形态间平滑变换。
- **探索**：缩放、平移、拖动节点；点击兴趣分类、标签或 UP 主查看详情；搜索或随机遇见一个账号。
- **分享**：纯净画面用于录屏，导出 2400 × 1600 PNG。默认不在图片中显示 UP 主名称。
- **本地运行**：无需安装前端依赖，没有外部请求；支持页面内导入 JSON。无数据时显示 728 个明确标注的虚构演示账号。

```bash
python scripts/visualize.py
# 也可指定输入与输出
python scripts/visualize.py --input path/to/combined.json --output interest-map.html
```

直接打开生成的 `scripts/map.html`，或打开 `frontend/index.html` 体验演示。前端源文件在 `frontend/`，修改后重新运行生成脚本。

数据兼容现有 `combined.json`：`mid`、`uname`、`label`，可选 `tags`、`sign`、`fans`、`last_days`、`videos`。兴趣大类由内容标签关键词推定；保留原始标签。图谱连线表示账号与标签、标签与兴趣大类，及共享标签的相邻账号；指纹的螺旋线只表示视觉排列。节点位置是视觉布局，不代表实际脑区、人格、观看时间或账号互动。

### 文件结构

```
bili-following-cleanup/
├─ SKILL.md                      # 技能说明（含 agent 向用户索要 Cookie 的话术）
├─ README.md
├─ .gitignore                    # 忽略 cookie.txt 与所有数据文件
└─ scripts/
   ├─ extract_cookie_firefox.py  # 从 Firefox 提取 Cookie
   ├─ fetch_following.py         # 拉全量关注
   ├─ fetch_videos.py            # 抓每人近期投稿（wbi 签名）
   ├─ fetch_fans.py              # 补粉丝/等级/播放（免登录）
   ├─ split_chunks.py            # 切块供打标（推荐 subagent）
   ├─ analyze_split.py           # 切块供分类（推荐 subagent）
   ├─ build_selector.py          # 合并 + 生成 selector.html
   ├─ unfollow.py                # 批量取关
   └─ retry_unfollow.py          # 风控失败重试
```

## 安全与合规

- `cookie.txt` 是你的登录凭证，等价于账号密码的一部分：**不要提交、不要分享**。`.gitignore` 已默认忽略。
- 所有运行产出的数据（`*.json`、`selector.html` 等）也已在 `.gitignore` 中。
- 批量取关可能触发 B 站风控（返回 `-352`）。请放慢节奏、控制数量，自行承担账号风险。
- 本项目仅供个人整理自己的关注列表使用。
