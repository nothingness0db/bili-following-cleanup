---
name: bili-following-cleanup
description: Review and clean up a Bilibili (B站) following list end-to-end — read every follow, fetch each up主's recent videos to infer their content niche, classify accounts into unfollow categories with priority, render a local HTML picker, then batch-unfollow through the B站 API with risk-control retries. Use when the user wants to 整理/清理 B站 关注列表, asks "这个 up 是做什么的", or wants to 批量取关 / unfollow Bilibili accounts.
---

# B 站关注列表梳理与批量取关

把「关注列表」变成「可筛选的清单」，再安全地批量取关。这是一条**固定流水线**：拿到 Cookie 后一次跑到底（拉关注 → 抓投稿 → 打标 → 分类 → 补粉丝 → 出网页 → 用户勾选 → 取关 → 重试收尾），只有「用户勾选」一步需要人工介入。打标 / 分类这两步**推荐**用 subagent 并行处理（避免占满主上下文），并非强制。

## 何时使用

- 用户想整理/清理 B 站关注列表、想知道某个关注的人是做什么的、想批量取关。
- 触发关键词：B站 / bilibili / 关注列表 / 取关 / unfollow。

## 核心原则：取关决定权归用户

- agent 只做**拉取、分类、标注、可视化、提供筛选**——把决定权留给使用者。
- **不要**攒出一份「建议取关名单」然后问用户「这些全部取关行不行？」。分类（类型 / 优先级 / 内容 / 粉丝 / 停更）只是给用户在页面里**自己挑**的参考。
- 取关名单**只能来自用户自己勾选导出**（`unfollow.txt`），或用户明确给出的 mid 列表。
- 换句话说：把「帮他看清有哪些、各是什么」做到位，但「取关谁」永远是他按下去的。

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

## 工作流（一次跑到底）

拿到 Cookie 后，agent 应**连续跑完全部步骤**，中途不停下来问「要不要继续」。**唯一的停顿点**是第 6 步「用户勾选」。凡可拆块**本地分析**的环节（打标 / 分类），**同时开一批 subagent**，不要一个个串行。

> **所有联网请求一律串行、低频。** 采集（`fetch_following.py` / `fetch_videos.py` / `fetch_fans.py`）读 3–6 秒一次，取关（`unfollow.py` / `retry_unfollow.py`）写 8–15 秒一次，全部走同一个闸门（`bili_read.py` + `bili_write.py`）、共用一个熔断状态。**不要**为了提速改回多线程 / 提高并发——那正是触发 `-352` 的原因。**并行只用于本地分析（打标 / 分类），不用于打接口。**
>
> 遇风控时脚本会**立即停掉整批**并保存已拿到的进度，不会自动重试、不会换接口续抓。成功的响应会缓存，重跑只补剩下的部分。处置办法见「遇风控怎么办」。

> `build_selector.py` 是幂等的「合并 + 渲染」，每次有新数据产出（打标 / 分类 / 粉丝）后就重跑一次即可。

### 1. 拉全量关注（拿到 UID 列表）
```
python fetch_following.py        # nav 校验登录 -> 分页 x/relation/followings
# 产出 following.json / following.csv（mid、昵称、签名、认证、关注时间、visit_rank）
```
接口用 `order_type=attention` 返回的是**「最常访问」排序**——越靠前你越常点进去。脚本把名次写成 `visit_rank`（1..N），供 4.5 的保护逻辑用。

### 2. 抓每人近期投稿
```
python fetch_videos.py           # 串行低频（走 bili_read）签名调 x/space/wbi/arc/search，取最近 6 个投稿标题
python build_selector.py         # 生成初始 combined.json (+ selector.html)
```

### 3. 打标：每个号是做什么的（不可跳过）
```
python split_chunks.py           # 切成 8 份 chunks/chunk_XX.json
```
**并行开一批 subagent**（推荐，账号少时也可在主上下文直接做）：每个读一份 `chunk_XX.json`，结合昵称/签名/认证/视频标题，为每个号生成 2–14 字中文「内容定位」标签，写 `labels_XX.json`（`mid/uname/label/reason`）。
```
python build_selector.py         # 合并 labels
```

### 4. 分类：类型 + 优先级（不可跳过）
```
python analyze_split.py          # -> chunks_analysis/aXX.json
```
**并行开一批 subagent**：每份按下面 8 类给出 `类型 + 优先级(高/中/低) + 是否建议取关 + 理由`，写 `analyze_out_XX.json`。

| 类型 | 一句话 | 是否建议取关 |
|---|---|---|
| 1 退坑遗产 | 内容绑在已退出的圈子 | ✅ |
| 2 信息重复 | 同质账号扎堆 | ✅ |
| 3 过期工具人 | 一次性用途已结束 | ✅ |
| 4 社交礼貌关注 | 为关系而关，不看内容 | ✅ |
| 5 内容质量退化 | 越做越水 | ✅ |
| 6 低频兴趣 | 优质但很少看 | ✅ |
| 7 情绪负收益 | 刷到只有负收益 | ✅ |
| 8 历史纪念品 | 舍不得，留个念想 | ❌ |
| 0 保留 | 优质/在用 | ❌ |

**判定口径（开放式框架，可重叠，取最主要的一个）：**

**1 退坑遗产** —— 内容深度绑定某个具体游戏 / 番剧 / 圈子 / CP / 人设，而你已不再玩、不再追、不再混那个圈子。更新对你再无意义，取关也不牵扯任何现实关系。
- 信号：标题几乎全是某个游戏/番剧/团体的专有名词；列表里你已很久没点开它的相关视频。

**2 信息重复** —— 同一个垂类你关注了十几个高度同质的号（如 CS2 切片、偶像翻跳、VOCALOID 翻唱、加密资讯、电影解说），信息互相覆盖、边际价值低。保留你看得最多/质量最高的少数，其余清掉。
- 信号：`label` 高度一致；多个号在发几乎相同的内容；可用「按粉丝」排序，把头部留下、长尾清掉。

**3 过期工具人** —— 当初为某个具体目的而关注：查教程、下资源、领优惠、跟活动/赛事、追某门课、找某个软件用法。问题已解决、活动已结束，账号或停更、或只剩广告/搬运。留着只会污染信息流。
- 信号：教学 / 资源 / 工具 / 搬运 / 带货 / 活动类；内容一次性、没有持续价值。

**4 社交礼貌关注** —— 出于互关、评论互动、线下认识、同学同事、朋友的朋友等关系而关注，但实际不消费其内容。取关本身没问题，但要留意是否会影响现实关系。
- 信号：个人生活号、小透明、内容对你几乎无信息价值。
- 折中：若在意关系，可用 B 站「**悄悄关注**」或仅调低活跃，而不一定硬取关。

**5 内容质量退化** —— 早年确实有价值，如今转向水视频、标题党、广告软广、跟风蹭热度，单位时间的性价比明显下降。
- 信号：近期标题/封面明显博眼球；大量恰饭、切片、搬运；更新频繁但信息量稀薄。

**6 低频兴趣** —— 内容本身不差，只是属于你偶尔才想起的冷门领域，半年未必主动点开一次。清了不心疼、留了也不占太多。
- 信号：垂直且优质，但与你当前的重心关联弱；可借「停更天数」「播放量」辅助判断。

**7 情绪负收益** —— 内容容易引发烦躁、争论、焦虑或对立：时政/键政、性别地域对立、贩卖焦虑、饭圈撕、恐吓式标题党。刷到的净收益为负，越早清越清净。
- 信号：立场输出型、争论型、焦虑营销型内容为主。

**8 历史纪念品** —— 内容未必还看，但因关注了很多年、伴随某段记忆，舍不得取关。**默认保留**；若真想精简，可考虑归档到收藏夹/关注分组而非直接取关。

**0 保留** —— 优质、与当前需求相关、仍在持续消费的账号，或没有明确取关理由。宁可判 0 也不要错杀。

> 说明：这是**开口的思考框架**，一个号可能同时符合多条；让 subagent 选「最主要的那一条」，并在 `reason` 里写清依据。类型 1–7 → `unfollow=true`；类型 8 / 0 → `unfollow=false`。

### 4.5 最常访问保护（不可跳过）

`visit_rank`（来自第 1 步）是「最常访问」名次。**你几乎不可能取关自己最常访问的号**，所以设一条保护线：`build_selector.py` 里 `PROTECT_TOP = 50`，凡 `visit_rank <= 50` 一律**强制** `unfollow=false`，并在 `why` 标注「保护」。

- K 默认 50，可按用户意愿调（越小越激进）。
- 保护是**硬覆盖**：即使分类 subagent 判了类型 1–7，也不会被改回取关。
- 这只是给用户的参考护栏，**不改变**「取关决定权归用户」——用户仍可在页面里自行勾选。

### 5. 补粉丝量（不可跳过）
```
python fetch_fans.py             # 串行低频（走 bili_read）免登录：card 取粉丝/等级，upstat 取播放/点赞 -> 写入 combined.json
python build_selector.py         # 合并分析 + 粉丝 -> 最终 selector.html
```
页面显示 `粉丝 · Lv · 停更天数`，并支持「按粉丝」排序——用于处理「信息重复」：同内容里保粉丝多的、清少的。

### 5.5 生成图谱与开场

开场三段：常访问第一名的头像与名字 → 关注数量最多的领域 → Agent 挑选的一个有意思的发现，最后回到全景。领域按 UP 主内容标签归类，以全部关注账号数量统计，不能称为访问量最多的领域。

第三段由完成分析的 Agent 阅读关注列表、评分/优先级、分析理由、访问名次和投稿标题后自行选一个 UP 主。选择有具体趣味的反差、独特创作或意外联系，写一句针对这份列表的短评；可以像熟人一样轻轻调侃。不要固定挑粉丝最少或名次最高的账号，不套“小众宝藏”等统一称号，也不要把清理优先级当作品质量评分。人物和投稿必须来自实际数据，不能捏造观看经历或私人关系。

写入与 `combined.json` 同目录的 `recap_feature.json`（个人产物，不提交）：

```json
{
  "mid": "被选中的真实 UID",
  "title": "贴合这次发现的短标题",
  "text": "围绕真实关注与投稿写的一句短评",
  "evidence": [
    {"mid": "引用账号的真实 UID", "label": "原始标签", "priority": "原始优先级", "video_titles": ["引用的原始投稿标题"]}
  ]
}
```

`evidence` 包含被选账号；若短评联系了其他账号，也列出相关依据。`visit_rank` 可按实际数据附上。页面检查依据是否匹配当前数据，缺失或过期时略过第三段，不用固定规则补一个。

```bash
python visualize.py              # 自动读取 recap_feature.json，生成独立 map.html
```

镜头聚焦真实节点后展开头像。头像优先取账号自身的 `face`，缺失时按 UID 从同目录 `following.json` 补齐；只缓存并内嵌常访问第一名和第三段所选账号的头像，生成后可离线显示。下载失败显示名字缩写，不用虚构头像。`visit_rank` 是名次，不是访问次数或年度观看量。

开场不阻挡操作，可跳过；开始探索即结束开场。开场结束、镜头回稳后才显示右侧「开始清理」拉柄并做一次提示，重播期间再次隐藏。进入清理的黑屏转场总时长约 2 秒。保持现有清理与取关逻辑。

### 6. 用户勾选（唯一的人工停顿点）
先打开 `map.html` 查看关注图谱，点击或向左拉动右侧「开始清理」拉柄，经黑屏过场进入现有勾选界面。`map.html` 已内嵌数据与勾选页面，直接双击打开即可，无需启动 HTTP 服务；不要为了这个流程搭建服务器。`selector.html` 保留为独立入口。

打开 `selector.html`（数据内嵌、免联网）：搜索 / 按内容 / 按类型 / 按优先级 / 按粉丝 / 按停更任意组合筛选，由用户**自己勾选** → **导出 unfollow.txt**（下载 + 复制剪贴板）。

> ⚠️ 这一步**必须等用户自己挑**。不要替他勾、不要问「我帮你把建议的那批全取关好吗？」——按上面的核心原则来。

### 7. 执行取关
```
python unfollow.py --yes         # POST x/relation/modify, act=2, 8–15s 一个 -> unfollow_log.json
```
取关侧同样受闸门约束（`bili_write.py`）：**单批最多 50 个、每天最多 100 个**，撞上 `-352` / `HTTP 412` **立刻停掉整批**，不做任何退避重试。

**续做就是再跑一次**，不用手写 `retry.txt`：
```
python unfollow.py               # 日志里已成功的自动跳过，接着做剩下的
python retry_unfollow.py         # 只想补 retry.txt 里那批时用，节奏与上面完全一致
```

> 被风控挡下时**不要**换接口、缩短间隔或改脚本绕过——只会让账号状态更糟。等冷却结束、`python bili_read.py --resume` 之后再继续。

### 8. 收尾
```
python build_selector.py         # 已成功取关的自动从清单/页面剔除
```

## 关键接口与坑

- 关注列表：`GET x/relation/followings?vmid=&pn=&ps=50`（需登录 Cookie）。
- **最常访问排序 / `visit_rank`**：`GET x/relation/followings?...&order=desc&order_type=attention` —— `attention` 即关注页「**最常访问**」（按访问频率）；默认 / `order_type=visit` 才是按**关注时间**，别用错。返回的是**全量关注的名次**（1..N），不是只有前几十个。
- 用户资料：`GET x/web-interface/card?mid=`、`GET x/space/upstat?mid=`（免登录）。
- 投稿列表：`GET x/space/wbi/arc/search`，**需要 wbi 签名**（`nav` → `img_key/sub_key` 按 Mixin 表重排取前 32 位 → `md5(sorted_query + wts + key)`），实测**必须带登录 Cookie**，否则 `-352`。
- 取关：`POST x/relation/modify`，表单 `fid / act=2 / re_src=11 / csrf=<bili_jct>`。
- **风控 -352**：批量取关**可能**成片触发（实测一次 137 个里 26 个中招，另一次 81 个全过）。脚本侧已限制为每批 50 / 每天 100 并**遇风控整批停手**；剩下的分次补，不要一次冲完。读写两侧的处置见「遇风控怎么办」。
- **粘连的 mid**：从聊天/别处复制的列表常把多个 mid 粘成一行（如 `4902922711257000280` = `490292271` + `1257000280`）。导入前必须拆开，并用 `following.json` 校验「不在关注列表」的项。
- **隐私**：`cookie.txt` 与所有 `*.json` 数据都在 `.gitignore` 里；发布前确认没被 tracked。

## 遇风控怎么办

`bili_read.py` 是**所有联网请求**的统一闸门：**单线程串行 + 读 3–6 秒 / 写 8–15 秒 + 全局熔断**（`fetch_*.py`、`unfollow.py`、`retry_unfollow.py` 共用同一个 sqlite 状态，通过 `bili_write.py` 走同一条闸门）。任何一次请求一旦碰到风控信号（`code=-352` / `-412`、`HTTP 403/412/429`，或消息含「风控 / 频繁 / 访问受限」），会：

1. **立刻停掉整个批次**，不再动后面的账号；
2. 把**已拿到的部分原子落盘**（`save_json`），本地打标 / 分类 / 出页面都能继续用这部分；
3. 把闸门**暂停 30 分钟**并打印原因——采集与取关一起被挡住。

**已拿到的不会白费**：成功的响应按 key 缓存在 `scripts/.bili-read-state.sqlite3`（已 gitignore）。

- 投稿 / 粉丝按 **mid** 缓存 24 小时：重跑只补没抓到的号；
- 关注列表按 **页** 缓存 1 小时：断在第 7 页就从第 7 页继续；
- 取关按 **mid** 记在 `unfollow_log.json`：重跑自动跳过已成功的。

暂停后**该做什么**：

- **等。** 不重试、不换接口、不改脚本去补抓、不试探——这些都是绕过熔断，只会更糟。
- **做离线的事**：拿已落盘的数据跑打标 / 分类 / `build_selector.py` / `visualize.py`（全程不发请求）。
- 查闸门状态与今日已取关数：`python bili_read.py`（只读本地，不发请求）。
- 冷却结束后，`python bili_read.py --resume` 再重跑对应脚本——**只补剩下的部分**，不用从头再来。
- `--resume` 只解除「本地暂停」，**不代表平台已放过**，仍需维持低频。
- 要强制重抓某类数据：`python bili_read.py --forget-cache videos`（不带 scope 全清）。

> 铁律：联网请求**只走串行低频**，并发（如 `max_workers=4`）正是实测触发 `-352` 的原因；出问题就**停**、就**等**。并行仅用于本地分析（打标 / 分类）。

## 自检

```
python selftest.py               # 离线跑：不联网、不真等，30+ 项断言，退出码 0 = 全通过
```
改了闸门 / 缓存 / 取关脚本之后先跑这个，别拿真账号当测试环境。

## 文件产出速查

| 文件 | 来源 | 内容 |
|---|---|---|
| `cookie.txt` | 提取/用户提供 | 登录 Cookie（敏感） |
| `bili_read.py` | — | 统一闸门：限速 + 全局熔断 + 响应缓存（`--resume` / `--forget-cache`） |
| `bili_write.py` | — | 取关写路径：批上限 50、日上限 100、撞风控整批停 |
| `.bili-read-state.sqlite3` | bili_read.py | 闸门状态与缓存（本地、已 gitignore） |
| `selftest.py` | — | 离线自检：不联网验证闸门/缓存/取关行为 |
| `following.json/.csv` | fetch_following.py | 全量关注（含 `visit_rank` 最常访问名次） |
| `following_videos.json` | fetch_videos.py | 每人近期投稿标题 |
| `labels_XX.json` | 打标（推荐 subagent） | 内容定位标签 |
| `combined.json` | build_selector.py | 合并后的主数据 |
| `selector.html` | build_selector.py | 勾选网页 |
| `map.html` | visualize.py | 关注图谱与清理过场，内嵌数据和勾选页面 |
| `analyze_out_XX.json` | 分类（推荐 subagent） | 类型/优先级 |
| `unfollow.txt` | 用户/网页导出 | 待取关 mid 列表 |
| `unfollow_log.json` | unfollow.py | 取关结果 |
| `retry_log.json` | retry_unfollow.py | 补做结果 |
