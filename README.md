# bili-following-cleanup

把 B 站「关注列表」整理成可筛选清单，并批量取关。适合关注了几百个人、想按「这人是做什么的」来清理的场景。

> 这是一个 opencode / Claude 技能（也是可直接运行的脚本集）。把本目录放进技能目录即可被 agent 加载使用；或按下面的步骤手动跑脚本。

## 它做什么

一条固定流水线，一次跑到底（只有「用户勾选」需要人工介入）：

1. **拉全量关注** —— 登录态分页读取，导出 JSON/CSV（含「最常访问」名次 `visit_rank`）。
2. **抓投稿** —— 抓每人最近 6 个投稿标题。
3. **打标** —— 生成每个号的内容定位标签（推荐用 subagent 并行）。
4. **分类打分** —— 按 8 种取关判断给类型 + 优先级（推荐用 subagent 并行）。
5. **最常访问保护** —— 用 `visit_rank`（关注页「最常访问」名次）给前 50 名**硬保护**，一律不标建议取关。
6. **补粉丝量** —— 免登录接口，辅助判断「信息重复」。
7. **本地网页勾选** —— `selector.html`，搜索/按内容/类型/优先级勾选/导出待取关列表。
8. **兴趣图谱** —— `visualize.py` 生成 `map.html`：脑回路 / 兴趣星系，拉动右侧「开始清理」进入勾选页面。
9. **批量取关** —— 8–15 秒一个、单批最多 50、每天最多 100，撞上风控**整批停下**，不重试。

## 原则：决定权归用户

工具只负责**分类和呈现**，不替用户决定。agent **不会**攒一份「建议取关名单」再问「全部取关行不行」——分类只是给人**自己挑**的参考，取关名单永远来自使用者自己勾选导出。

## 最常访问保护

关注列表接口用 `order_type=attention` 拿到的就是关注页「**最常访问**」排序（越靠前越常点进去），脚本写成 `visit_rank`。`build_selector.py` 里 `PROTECT_TOP = 50`：`visit_rank <= 50` 的号**强制**不标建议取关。这是一层硬护栏（连分类结果也覆盖），K 可自行调整；它只是参考，最终勾选仍归用户。

## 串行、断路与断点续抓

**所有联网请求串行**：`fetch_*.py` / `unfollow.py` / `retry_unfollow.py` 都走同一个闸门（`bili_read.py` + `bili_write.py`，共用一份 sqlite 状态）。**不会**用多线程并发——并发（`max_workers=4`）是实测触发 `-352` 的原因。

闸门分两条车道，区别不在快慢，而在**风控后果落在谁头上**：

| | `account` 车道（带 Cookie） | `anon` 车道（不带 Cookie） |
|---|---|---|
| 谁走这条 | `fetch_following` / `fetch_videos` / 全部取关 | `fetch_fans`（`card` + `upstat` 公开接口） |
| 间隔 | 读 3–6 秒；写 8–15 秒 | 1–2 秒 |
| 撞风控后果 | **扣账号**，可能连带影响取关、评论 | 扣本机 IP，通常过一阵自动恢复，不动账号 |
| 冷却 | 30 分钟 | 10 分钟 |
| 互相牵连 | 独立暂停状态，谁也不连带谁 | 同左 |
| 单批上限 | 取关 50 个/次脚本 | 不限 |
| 每日上限 | 取关 100 个（跨批次累计） | — |

匿名侧能快多少是**实测**出来的，不是猜的（`python probe.py`，23 个匿名请求逐档加速）：

```
card    间隔 1.5s → 1.0 → 0.7 → 0.5 → 0.3 → 0.2s   全过（中位延迟 60–90ms）
upstat  间隔 1.5s → 1.0 → 0.7 → 0.5 → 0.3 → 0.2s   全过（中位延迟 55–98ms）
```

实测到 0.2 秒都没被挡，但闸门只取 **1–2 秒**（留 5–10 倍余量）——爆量测试说明不了「一天能抽多少」。账号侧**没有**做这类压测：那要真的拿 SESSDATA 去打，风险落在账号上，不值得为跑分冒险。

一旦遇到风控信号（`-352` / `-412` / `HTTP 403·412·429` / 消息含「风控·频繁·访问受限」），脚本会**立即停掉整批**、把**已拿到的部分原子落盘**、并**暂停对应车道**。之后：

- **等**，不要重试 / 换接口 / 改脚本续抓；
- 先做**离线**的事（打标、分类、`build_selector.py`、`visualize.py`，都不发请求）；
- `python bili_read.py` 看两条车道状态与今日已取关数（只读本地，不发请求）；
- 冷却结束后 `python bili_read.py --resume`（或只解一条：`--resume anon`）再重跑对应脚本。

**不用从头再来**：成功的响应按 key 缓存在本地（`scripts/.bili-read-state.sqlite3`，已在 `.gitignore` 里）。

- 投稿 / 粉丝按 **mid** 缓存 24 小时 —— 重跑只补还没抓到的号，已抓的直接读缓存；
- 关注列表按 **页** 缓存 1 小时 —— 断在第 7 页就从第 7 页继续；
- 取关按 **mid** 记在 `unfollow_log.json` —— 重跑自动跳过已成功的，所以「补剩下的」就是再跑一次。

想让某类数据强制重抓：`python bili_read.py --forget-cache videos`（不带 scope 则全清）。

并行只用于**本地分析**（打标 / 分类的 subagent），不用于打接口。

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
python unfollow.py              # 单批 50 个上限；撞风控整批停，不重试
# 剩下的直接再跑一次即可续做（已成功的会自动跳过，不需要手写 retry.txt）
python unfollow.py
```

## 目录

### 关注的形状 · 独立兴趣图谱

这是一层独立的视觉展示，不改变原有筛选、取关脚本和数据。

- **脑回路 / 兴趣星系**：同一份关注数据在两种形态间平滑变换。
- **探索**：缩放、平移、拖动节点；点击兴趣分类、标签或 UP 主查看详情；搜索或随机遇见一个账号。
- **外观**：默认跟随系统自动切换浅色 / 深色，也可手动选择；导出图片使用当前配色。
- **开场聚焦**：镜头推近真实常访问 UP 主，展开头像与名字，再展示关注数量最多的领域和 Agent 从真实分析、评分与投稿中挑选的趣味发现。领域按 UP 主内容标签归类、以全部关注账号数量统计。可跳过，开始探索即停止；缺失数据时省略相应内容。
- **真实头像**：按 UID 从同目录 `following.json` 补齐，只缓存并内嵌常访问第一名和第三段所选账号的头像；下载失败显示名字缩写。
- **第三段发现**：分析 Agent 自行选择账号并写入 `recap_feature.json`，生成时自动读取，也可通过 `--feature` 指定。页面核对原始依据，失配时略过。
- **分享**：纯净画面用于录屏，导出 2400 × 1600 PNG。默认不在图片中显示 UP 主名称。
- **本地运行**：无需安装前端依赖，生成时下载开场头像并内嵌；支持页面内导入 JSON。无数据时显示 728 个明确标注的虚构演示账号。

```bash
python scripts/visualize.py
# 也可指定输入与输出
python scripts/visualize.py --input path/to/combined.json --output interest-map.html
```

生成后直接双击 `scripts/map.html`，开场结束后再显示右侧「开始清理」拉柄；点击或向左拖动，经约 2 秒的黑屏转场进入现有勾选页，导出 `unfollow.txt`。图谱、样式、脚本和勾选页面均内嵌在同一个文件中，无需启动服务；取关仍使用现有脚本。清理页面仅在进入时加载，图谱退场后停止绘制；返回图谱保留当前勾选。支持系统的减少动态效果设置。

默认内嵌输入 JSON 同目录的 `selector.html`，也可用 `--selector` 指定。若勾选页面尚未生成，则隐藏拉柄；独立的 `selector.html` 仍可使用。过场短句为原创，并非游戏原文。

打开 `frontend/index.html` 可体验演示。前端源文件在 `frontend/`，修改后重新运行生成脚本。

数据兼容现有 `combined.json`：`mid`、`uname`、`label`，可选 `tags`、`sign`、`fans`、`last_days`、`videos`、`visit_rank`、`protected`。兴趣大类由内容标签关键词推定；保留原始标签。图谱连线表示账号与标签、标签与兴趣大类，及共享标签的相邻账号。节点位置是视觉布局，不代表实际脑区、人格、观看时间或账号互动。

### 文件结构

```
bili-following-cleanup/
├─ SKILL.md                      # 技能说明（含 agent 向用户索要 Cookie 的话术）
├─ README.md
├─ .gitignore                    # 忽略 cookie.txt 与所有数据文件
└─ scripts/
   ├─ extract_cookie_firefox.py  # 从 Firefox 提取 Cookie
   ├─ bili_read.py               # 闸门：account 车道 3–6s / anon 车道 1–2s、分车道熔断、响应缓存
   ├─ bili_write.py              # 取关写路径：批上限 50、日上限 100、撞风控整批停
   ├─ fetch_following.py         # 拉全量关注（串行，按页缓存续抓）
   ├─ fetch_videos.py            # 抓每人近期投稿（串行，wbi 签名，按 mid 缓存续抓）
   ├─ fetch_fans.py              # 补粉丝/等级/播放（anon 车道，免登录，按 mid 缓存续抓）
   ├─ split_chunks.py            # 切块供打标（推荐 subagent）
   ├─ analyze_split.py           # 切块供分类（推荐 subagent）
   ├─ build_selector.py          # 合并 + 生成 selector.html
   ├─ selftest.py                # 离线自检：不联网跑完闸门/缓存/取关的全部行为
   ├─ probe.py                   # 匿名接口速率探针（不带 Cookie，只影响本机 IP）
   ├─ unfollow.py                # 批量取关
   └─ retry_unfollow.py          # 补做剩下的（与 unfollow.py 同节奏，不额外重试）
```

## 自检

```bash
cd scripts
python selftest.py              # 不联网、不真等，30+ 项断言；退出码 0 表示全部通过
```

## 安全与合规

- `cookie.txt` 是你的登录凭证，等价于账号密码的一部分：**不要提交、不要分享**。`.gitignore` 已默认忽略。
- 所有运行产出的数据（`*.json`、`selector.html` 等）也已在 `.gitignore` 中。
- 批量取关可能触发 B 站风控（返回 `-352`）。脚本已限制节奏（8–15 秒一个、每批 50、每天 100）并在风控时整批停手，但仍请自行承担账号风险。
- 本项目仅供个人整理自己的关注列表使用。
