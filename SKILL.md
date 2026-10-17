---
name: bili-following-cleanup
description: Review and clean up a Bilibili (B站) following list end-to-end — read every follow, fetch each up主's recent videos to infer their content niche, classify accounts into unfollow categories with priority, render a local HTML picker, then batch-unfollow through the B站 API with risk-control retries. Use when the user wants to 整理/清理 B站 关注列表, asks "这个 up 是做什么的", or wants to 批量取关 / unfollow Bilibili accounts.
---

# B 站关注列表梳理与批量取关

把「关注列表」变成「可筛选的清单」，再安全地批量取关。全程脚本化，判断类工作（打标/分类）**推荐**用 subagent 来做，以免占满主上下文——但并非强制，量少时也可在主上下文里直接完成。

## 何时使用

- 用户想整理/清理 B 站关注列表、想知道某个关注的人是做什么的、想批量取关。
- 触发关键词：B站 / bilibili / 关注列表 / 取关 / unfollow。

## 运行环境

- Python 3 + `httpx`。
- 一个工作目录（放下面这些脚本），脚本内所有路径都相对脚本自身，可整体搬移。
- 登录 **Cookie**，必须含 `SESSDATA`、`bili_jct`、`DedeUserID`（再带 `buvid3/buvid4/b_nut` 更抗风控）。

## 第一步：获取 Cookie（agent 话术）

`bili_jct` 是取关接口的 csrf，`DedeUserID` 是你的 mid，`SESSDATA` 是登录态——三者缺一不可。

**方案 A（推荐，本机有 Firefox 时）：agent 自己提取，不问用户要明文。**
运行 `python scripts/extract_cookie_firefox.py`，它会从 Firefox 的 `cookies.sqlite`（明文）里取 B 站 Cookie 写入 `cookie.txt`。
若用户用的是 Chrome/Edge（Cookie 经过 DPAPI 加密，脚本不处理），转向方案 B。

**方案 B：向用户索要。** 直接输出下面这段话（把 `cookie.txt` 路径换成实际工作目录）：

> 我需要你的 B 站登录 Cookie 才能读取关注列表并取关。获取方式：浏览器登录 B 站 → F12 → 网络(Network) → 刷新页面 → 点任意 `api.bilibili.com` 请求 → 请求头里的 `Cookie` 一行 → 整行复制发我。
>
> 需要包含 `SESSDATA`、`bili_jct`、`DedeUserID`。它等同于你的登录凭证，我只写进本地 `cookie.txt`、不会输出明文或上传；任务结束后你可以改密码/退出登录让它失效，或让我删除该文件。

拿到后写入 `cookie.txt`（单行 `k=v; k=v; ...`，`#` 开头为注释）。

> ⚠️ 无论哪种方式：`cookie.txt` 已在 `.gitignore` 中，**绝不能提交到版本库或发到任何外部服务**。

## 工作流

在含脚本的工作目录下依次执行。

### 1. 拉全量关注
```
python fetch_following.py        # nav 校验登录 -> 分页 x/relation/followings
# 产出 following.json / following.csv（mid、昵称、签名、认证、关注时间）
```

### 2. 判断每个号是做什么的
```
python fetch_videos.py           # wbi 签名调 x/space/wbi/arc/search，取最近 6 个投稿标题
# 产出 following_videos.json
python split_chunks.py           # 切成 8 份 chunks/chunk_XX.json
```
再对每个 `chunk_XX.json` 打标：结合昵称/签名/认证/视频标题，为每个号生成一个 2–14 字中文「内容定位」标签，写 `labels_XX.json`（字段 `mid/uname/label/reason`）。
- **推荐用 subagent**（`task` 工具）逐份处理：几百个账号，避免主上下文被视频标题塞满。**不强制**——账号少时直接在主上下文里打标即可。

### 3. 合并 + 人工筛选（本地网页）
```
python build_selector.py         # 合并 -> combined.json + selector.html
```
`selector.html` 数据内嵌、无需联网，双击打开：搜索 / 按内容分类 / 勾选 / **导出 unfollow.txt**（下载 + 复制剪贴板）。交给用户确认要取关谁。

### 4.（可选）类型 + 优先级分析
```
python analyze_split.py          # -> chunks_analysis/aXX.json
```
再对每份 `aXX.json` 分类：按下面 8 类给每个号 `类型 + 优先级(高/中/低) + 是否建议取关 + 理由`，写 `analyze_out_XX.json`。
- **推荐用 subagent**（`task` 工具）逐份处理；**不强制**，账号少时也可直接做。

| 类型 | 含义 |
|---|---|
| 1 退坑遗产 | 游戏/番剧/圈子的内容，已不感兴趣 |
| 2 信息重复 | 同类关注了十几个，留质量最高的 |
| 3 过期工具人 | 为某教程/资源/活动关注，现已无用 |
| 4 社交礼貌关注 | 互关/互动/线下认识，但不想看内容 |
| 5 内容质量退化 | 以前有价值，现在只剩水视频/广告/跟风 |
| 6 低频兴趣 | 内容不差，但半年想不起来 |
| 7 情绪负收益 | 刷到只会烦躁/争论/浪费注意力 |
| 8 历史纪念品 | 只因关注多年舍不得取关 |
| 0 保留 | 优质或相关，无需取关 |

再跑一次 `build_selector.py` 合并（页面出现「类型 / 优先级」筛选与「勾选全部建议」）。

### 5.（可选）补粉丝量
```
python fetch_fans.py             # 公开接口，免登录：card 取粉丝/等级，upstat 取播放/点赞
python build_selector.py         # 页面显示 粉丝 · Lv · 停更天数，并支持「按粉丝」排序
```
用途：处理「信息重复」——同内容里保粉丝多的、清少的。

### 6. 执行取关
把要取关的 mid 每行一个写进 `unfollow.txt`（或从 selector.html 导出）。
```
python unfollow.py               # 默认交互确认
python unfollow.py --yes         # POST x/relation/modify, act=2, 随机延时 1.5–3.5s, 412 退避
# 产出 unfollow_log.json
```
若批量出现 `code=-352`（风控），把失败的 mid 写入 `retry.txt` 后放慢重试：
```
python retry_unfollow.py         # 8–16s 间隔，-352 退避 25–45s，最多重试 8 次
# 产出 retry_log.json
```
最后重跑 `build_selector.py`，已成功取关的会自动从清单/页面剔除。

## 关键接口与坑

- 关注列表：`GET x/relation/followings?vmid=&pn=&ps=50`（需登录 Cookie）。
- 用户资料：`GET x/web-interface/card?mid=`、`GET x/space/upstat?mid=`（免登录）。
- 投稿列表：`GET x/space/wbi/arc/search`，**需要 wbi 签名**（`nav` → `img_key/sub_key` 按 Mixin 表重排取前 32 位 → `md5(sorted_query + wts + key)`），实测**必须带登录 Cookie**，否则 `-352`。
- 取关：`POST x/relation/modify`，表单 `fid / act=2 / re_src=11 / csrf=<bili_jct>`。
- **风控 -352**：批量取关**可能**成片触发（实测一次 137 个里 26 个中招，另一次 81 个全过）；**放慢节奏**，失败后等待重试通常能补齐。
- **粘连的 mid**：从聊天/别处复制的列表常把多个 mid 粘成一行（如 `4902922711257000280` = `490292271` + `1257000280`）。导入前必须拆开，并用 `following.json` 校验「不在关注列表」的项。
- **隐私**：`cookie.txt` 与所有 `*.json` 数据都在 `.gitignore` 里；发布前确认没被 tracked。

## 文件产出速查

| 文件 | 来源 | 内容 |
|---|---|---|
| `cookie.txt` | 提取/用户提供 | 登录 Cookie（敏感） |
| `following.json/.csv` | fetch_following.py | 全量关注 |
| `following_videos.json` | fetch_videos.py | 每人近期投稿标题 |
| `labels_XX.json` | 打标（推荐 subagent） | 内容定位标签 |
| `combined.json` | build_selector.py | 合并后的主数据 |
| `selector.html` | build_selector.py | 勾选网页 |
| `analyze_out_XX.json` | 分类（推荐 subagent） | 类型/优先级 |
| `unfollow.txt` | 用户/网页导出 | 待取关 mid 列表 |
| `unfollow_log.json` | unfollow.py | 取关结果 |
| `retry_log.json` | retry_unfollow.py | 风控重试结果 |
