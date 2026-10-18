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

## 三层：通用口径 / 这份列表的修正 / 运行产物

- **通用口径**：`scripts/classify_rubric.md`。只写 0–11 类的证据和相对分位（`rank_pct` / `fans_pct`），不写具体账号、不用「150 名 / 10 万粉」这种按某一份列表调出来的绝对数字。
- **这份列表的人工修正**：`scripts/overrides.json`。按 `mid` 覆盖类型/优先级/理由，`build_selector.py` 最后应用；只对这份列表生效，不进入通用口径，也不影响别人。
- **运行产物**：`analyze_out_*.json`、`combined.json`、`selector.html` 等。这些是本次跑出来的数据，不是 skill 规则。

> 想让 skill 适配另一份关注列表，不要改 `classify_rubric.md` 去写那个人/那份列表的例子；改 `overrides.json`，或调 `build_selector.py` 的 `PROTECT_TOP` 这类配置。

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

拿到 Cookie 后，agent 应**连续跑完全部步骤**，中途不停下来问「要不要继续」。**默认只有第 6 步「用户勾选」一个停顿点**；3.5「兴趣访谈」是可选的，只给人类看，不进入分类。凡可拆块**本地分析**的环节（打标 / 分类），**同时开一批 subagent**，不要一个个串行。

> **所有联网请求一律串行。** 间隔参照 bili-sync（同作者的 B 站同步工具）实测包线：列表 250ms、评论 400ms、全局「每 250ms 最多 4 个请求」。本闸门串行 0.25–0.5 秒 ≈ 2.5–4 次/秒，落在包线内。写（取关）单独定得慢（8–15 秒）+ 批/日上限，因为它改的是账号状态。**不要**改回多线程并发——旧版 4 线程零间隔 ≈20 次/秒，是包线的 5 倍。**并行只用于本地分析（打标 / 分类），不用于打接口。**
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
python fetch_videos.py           # 串行低频（走 bili_read）签名调 x/space/wbi/arc/search，单次取最近 20 个投稿标题
python build_selector.py         # 生成初始 combined.json (+ selector.html)
```

20 条里，**定位只用最近 8 条**（`analyze_split.py` 会切出这 8 条）；完整 20 条留给「内容转向 / 商业占比 / 质量退化」的按需核对。不要为了省 context 把所有账号的 20 条都反复读一遍，也不要只看 3–5 条摘要就下判断。

### 3. 打标：每个号是做什么的（不可跳过）
```
python split_chunks.py           # 切成 8 份 chunks/chunk_XX.json
```
**并行开一批 subagent**（推荐，账号少时也可在主上下文直接做）：每个读一份 `chunk_XX.json`，结合昵称/签名/认证/视频标题，为每个号生成 2–14 字中文「内容定位」和 3–5 个具体内容标签（资料不足时可更少），写 `labels_XX.json`（`mid/label/tags/content_reason/confidence/evidence_titles`）。统一同义标签，避免仅用「游戏」「科技」等宽泛大类。内容标签不包含清理评价。**打标这轮读全 20 条标题**；下一轮分类会用最近 8 条原始标题 + 摘要，需要时再查完整列表。
```
python build_selector.py         # 合并 labels
```

### 3.5 兴趣访谈（可选）：只给人类参考，不进入分类

> **默认可以跳过这一节。** 它产出的 `interest_profile.json` 不进入分类输入；分类 subagent 不要读它，也不要用「用户说过喜欢某个细分」当保留理由。它只供 agent 和用户自己看，最多影响优先级。

数据进来后先看大盘：用 `combined.json` 的 `tags` 找出占比最大的几个兴趣簇，默认取到覆盖约 60–70% 账号为止。**只问大簇，不逐号问**；一次问完。

**先用「最常访问」预筛**：对每个大簇，按细分标签的来访名次排序。名次靠前（进入前 100–150）的细分是候选保留；名次全线靠后、没人进前 150 的细分可以标记为「大概率不看」，但仍要在分类时逐号确认（停更/失效/纪念品另算）。

对访问靠前、你还在犹豫的细分，问用户：**「这个领域，你喜欢它的哪部分？」**——多选，允许自由补充，细分要够具体（知识类分 财经/投资/科普/历史/哲学/社会观察；二次元分 Cos/翻跳/同人/舞台/动画杂谈/虚拟主播；游戏分 实况/攻略/赛事/评测/独立游戏；音乐分 翻唱/原创/虚拟歌手/器乐）。

写 `interest_profile.json`：

```json
{ "二次元": {"keep": ["翻跳/宅舞", "舞台/现场记录"],
             "未表态逐号判": ["Cos（妆造/写真）", "同人创作"]},
  "计算机/AI/数码": {"keep": ["科技资讯", "AI研究/论文"]} }
```

**它只是给人看的笔记，不是分类规则**：

- `keep` / `drop` / 「没提到」都**不能直接产生类型**；同一个细分里逐号看这个号本身：最近在做什么、做得怎么样、你实际点不点。
- 用户说「会看某类」只说明这个大类可以留意，不代表每个该类的号都保留（小团/同好号如果本身不突出，照样 4 或 6）。
- 分类阶段**不要读 `interest_profile.json`**；`analyze_split.py` 也不再把它拷进 `chunks_analysis/`。

> 访问名次只是排序线索，不替用户做决定；它也不能单独证明一个号值得保留——`visit_rank` 靠前但内容同质/更新停滞的号，仍然可以 6/2/5。

### 4. 分类：类型 + 优先级（不可跳过）

```bash
python analyze_split.py          # -> chunks_analysis/aXX.json（默认 4 块）+ all_accounts.json
```

**并行开一批 subagent**：每个读一份 `chunks_analysis/aXX.json`，并先读 `scripts/classify_rubric.md`（判定口径唯一来源）；需要时读 `chunks_analysis/all_accounts.json`（判信息重复要跨块对比）。每个写 `analyze_out_XX.json`。

> 不要每次重跑时临时写一套 rubric。`classify_rubric.md` 是写死的口径；要改口径就改这个文件，让所有块读到同一版。

```bash
python verify_analysis.py        # 覆盖率/类型映射/unfollow 一致性 + 分布护栏
```

硬错误（缺人、重复 mid、类型非法、unfollow 与类型不符）必须修；警告要逐条看，尤其是下面这几条——它们正是上一次翻车的地方：

- **类型 4 为 0**，但列表里有粉丝很少的个人号 → 「社交礼貌关注」被整类漏掉；
- **类型 6 超过 50%** → 又变成「拿不准就塞低频」的兜底桶；
- **类型 11 的停更天数中位数 < 365** → 把「停更几个月」误判成账号失效；
- **类型 2 出现娱乐/创作类** → 违反「信息重复只用于信息/知识型」。

| 类型 | 一句话 | 建议取关 |
|---|---|---|
| 0 保留 | 有正向保留证据 | ❌ |
| 1 退坑遗产 | 具体游戏 / 软件 / 工具 / 圈子已退坑 | ✅ |
| 2 信息重复 | **信息型**账号互相覆盖 | ✅ |
| 3 过期工具人 | 一次性用途已结束 | ✅ |
| 4 社交礼貌关注 | 个人小号 / 小团同好 / 关系号，关系成本 | ✅（优先级低） |
| 5 内容质量退化 | 越做越水 | ✅ |
| 6 低频兴趣 | 内容不差，但你几乎不点 | ✅ |
| 7 情绪负收益 | 刷到只有负收益 | ✅ |
| 8 历史纪念品 | 舍不得，留个念想 | ❌ |
| 9 内容转向 | 现在方向与当初不同 | ✅ |
| 10 商业内容过多 | 推广/带货/引流占比高 | ✅ |
| 11 账号迁移／失效 | 旧号停用、迁移或已失效 | ✅ |

判定顺序（先硬事实，后内容口味）：**11 失效 > 4 个人小号 > 10 商业 > 1 退坑 > 3 工具 > 9 转向 > 5 退化 > 2 重复 > 6 低频 > 8 纪念**。0 不在这条链里：先看这个号**本身**有没有正向保留证据（`rank_pct <= 0.35` 且近期在更 / 有具体在追的系列 / 正在用的工具 / 现实需求），有就判 0；没有才往下找取关类型。**「用户说过喜欢这个细分」不算证据。**

几条最容易写错的边界：

- **20 条标题的用法**：定位只看最近 8 条（输入里的 `videos`）；判断 9 转向 / 10 商业 / 5 退化时，再按 mid 查 `following_videos.json` 的完整 20 条。不要因为只看 8 条就猜历史。
- **1 / 3 / 6 的区别**：1 是「某个具体游戏 / 软件 / 工具 / 圈子，你已经不玩、不用了」；3 是「只为办一件事关注，事已办完」；6 是「账号还在正常产出，你只是很少点」。泛游戏杂谈、泛工具合集、泛科技资讯不判 1；还在更新的工具号不判 3。
- **4 是可观察的**：`fans_pct <= 0.25` 且投稿 ≤6，或 `fans_pct <= 0.10` 且 `rank_pct >= 0.55`，或签名/标签是个人生活/日常且无稳定垂类；**小体量同好/团号**（某个企划的翻跳团、翻唱团、同角色 cover，粉丝相对同领域偏少、内容同质化）也算 4。粉丝少但垂类稳定、更新正常、用户也常点的小众创作者 → 0/6，不是 4。理由里写「关系成本 / 同好可替代，确认不是熟人再取」。
- **6 必须有「很少看」的证据**：`rank_pct >= 0.60` 或停更 > 180 天，且内容没有明显缺陷。**不能**只凭「用户没提过这个领域」或「定位不清」判 6，更不能当兜底。
- **2 只用于信息/知识型**（资讯/财经/加密/评测/解说/教程/攻略/同源切片）；翻跳、Cos、同人、翻唱、舞台、整活、Vlog、虚拟主播、游戏实况**永不判 2**。必须写 `comparison_mids`，并且只切名次更靠后的那个。
- **11 只给 ≥365 天或明确注销/迁移**；停更 2–6 个月按 6/8/0 判。
- **9/10 需要证据**：转向要有新旧对照，商业要看到品牌/优惠/课程/APP 的高密度。没有证据就按现在的内容判。

完整口径、反例和输出字段见 `scripts/classify_rubric.md`。

### 4.5 最常访问保护（不可跳过）

`visit_rank`（来自第 1 步）是「最常访问」名次。**你几乎不可能取关自己最常访问的号**，所以设一条保护线：`build_selector.py` 里 `PROTECT_TOP = 50`，凡 `visit_rank <= 50` 一律**强制** `unfollow=false`，并在 `why` 标注「保护」。

- K 默认 50，可按用户意愿调（越小越激进）。
- 保护是**硬覆盖**：即使分类 subagent 判了取关类型，也不会被改回取关。
- 这只是给用户的参考护栏，**不改变**「取关决定权归用户」——用户仍可在页面里自行勾选。

### 5. 补粉丝量（不可跳过）
```
python fetch_fans.py             # anon 车道 0.3–0.5s（免登录）：card 取粉丝/等级，upstat 取播放/点赞 -> 写入 combined.json
python build_selector.py         # 合并分析 + 粉丝 -> 最终 selector.html
```
页面显示 `粉丝 · Lv · 停更天数`，并支持「按粉丝」排序——用于处理「信息重复」：同内容里保粉丝多的、清少的。

### 5.5 生成图谱与开场

**图专用标签（可选，但推荐）**：清理分类用的 3–5 个标签不够撑图。用 20 条标题另生成一套 6–10 个带权标签，只喂图谱，不改分类：

```bash
python graph_tags_split.py       # -> graph_tags/input_XX.json + tag_seed.json
# 每块开一个 subagent：读 tag_seed + input_XX -> graph_tags/out_XX.json
python merge_graph_tags.py       # -> graph_tags.json（visualize.py 自动读取）
python visualize.py
```

图里的连线取**权重最高的 6 个标签**算加权余弦；少见标签权重更高；账号除了互相弹簧，还会被自己的标签节点吸引（`tag gravity`）。只看至少两个账号共享的标签节点，单人标签只留在详情里，避免图被孤立小点塞满。

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
python unfollow.py --retry-failed  # 连上次失败的也重试（默认不重试，免得永久失败的号卡住队首）
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
- **风控 -352**：批量取关**可能**成片触发（实测一次 137 个里 26 个中招，另一次 81 个全过）。脚本侧已限制为每批 50 / 每天 100 并**遇风控整批停手**；剩下的分次补，不要一次冲完。风控偏 **IP 级冷却型**——换 Cookie 无效，只能等（bili-sync 观测 30 分钟～1 小时自解）。处置见「遇风控怎么办」。
- **粘连的 mid**：从聊天/别处复制的列表常把多个 mid 粘成一行（如 `4902922711257000280` = `490292271` + `1257000280`）。导入前必须拆开，并用 `following.json` 校验「不在关注列表」的项。
- **隐私**：`cookie.txt` 与所有 `*.json` 数据都在 `.gitignore` 里；发布前确认没被 tracked。

## 遇风控怎么办

`bili_read.py` 是**所有联网请求**的统一闸门：**单线程串行 + 分车道限速 + 分车道熔断**（`fetch_*.py`、`unfollow.py`、`retry_unfollow.py` 共用同一个 sqlite 状态，通过 `bili_write.py` 走同一条闸门）。

车道按**风控后果落在谁头上**划分，不按快慢：

| | `account`（带 Cookie） | `anon`（不带 Cookie） | 写（取关） |
|---|---|---|---|
| 谁走这条 | `fetch_following` / `fetch_videos` | `fetch_fans` | `unfollow` / `retry_unfollow` |
| 间隔 | 0.25–0.4s | 0.3–0.5s | 8–15s |
| 冷却 | 30 分钟 | 30 分钟 | 30 分钟 |
| 上限 | — | — | 50/批、100/天（按实际发出的请求数计） |

数字来源：bili-sync 的「风控与限流须知」——动态/列表 250ms、评论 400ms、全局每 250ms 最多 4 个请求。本闸门串行 0.25–0.5s ≈ 2.5–4 次/秒，落在它的包线内。旧速率探针已停用，不用真实接口压测来验证修改。

**读写为什么差这么多**：读接口的风控是冷却型、偏 IP 级（bili-sync 实测 `-403` 换 Cookie 无效，只能等），摊开请求就能过；写（取关）改的是账号状态，且实测 1.5–3.5 秒串行仍会成片中招。

任何一次请求一旦碰到风控信号（`code=-352` / `-412`、`HTTP 403/412/429`，或消息含「风控 / 频繁 / 访问受限」），会：

1. **立刻停掉整个批次**，不再动后面的账号（`-403 访问权限不足` / `-509` 也算风控，不只是 `-352`）；
2. 把**已拿到的部分原子落盘**（`save_json`）。投稿保留已有成功结果；关注列表未抓完整时只写 `following.partial.json`，不替换正式 JSON/CSV；
3. **两条车道一起暂停**，本地最短冷却 30 分钟并打印原因；冷却后也不会自动恢复。

**已拿到的不会白费**：成功的响应按 key 缓存在 `scripts/.bili-read-state.sqlite3`（已 gitignore）。

- 投稿 / 粉丝按 **mid** 缓存 24 小时：重跑只补没抓到的号。投稿刷新失败保留旧成功结果，全命中缓存时不请求接口，也不需要 Cookie；
- 关注列表按 **页** 缓存 1 小时：中断只写 `following.partial.json`，完整抓取成功后才替换 `following.json/.csv`；
- 取关按 **mid** 记在 `unfollow_log.json`：重跑自动跳过已成功的。

暂停后**该做什么**：

- **等。** 不重试、不换接口、不改脚本去补抓、不试探——这些都是绕过熔断，只会更糟。
- **做离线的事**：拿已落盘的数据跑打标 / 分类 / `build_selector.py`（不发请求）。`visualize.py` 会下最多 2 个头像，严格说不是零请求。
- 查两条车道状态与今日已取关数：`python bili_read.py`（只读本地，不发请求）。
- 冷却结束后，`python bili_read.py --resume`（只解一条：`--resume anon`）再重跑对应脚本——**只补剩下的部分**，不用从头再来。
- `--resume` 只解除「本地暂停」，**不代表平台已放过**，仍需维持低频。
- 要强制重抓某类数据：`python bili_read.py --forget-cache videos`（不带 scope 全清）。

> 铁律：联网请求**只走串行**。旧版 4 线程零间隔 ≈20 次/秒，是 bili-sync 实测包线（4 次/秒）的 5 倍，是 `-352` 最可疑的来源——但没有对照实验能证明它单独成立（串行 1.5–3.5 秒的取关同样会成片中招）。出问题就**停**、就**等**，换 Cookie 没用。并行仅用于本地分析（打标 / 分类）。

## 自检

```
python selftest.py               # 离线跑：不联网、不真等，退出码 0 = 全通过
```
改了闸门 / 缓存 / 取关脚本之后先跑 `selftest.py`，别拿真账号当测试环境。

## 文件产出速查

| 文件 | 来源 | 内容 |
|---|---|---|
| `cookie.txt` | 提取/用户提供 | 登录 Cookie（敏感） |
| `bili_read.py` | — | 统一闸门：限速 + 全局熔断 + 响应缓存（`--resume` / `--forget-cache`） |
| `bili_write.py` | — | 取关写路径：批上限 50、日上限 100、撞风控整批停 |
| `.bili-read-state.sqlite3` | bili_read.py | 闸门状态与缓存（本地、已 gitignore） |
| `selftest.py` | — | 离线自检：不联网验证闸门/缓存/取关行为 |
| `probe.py` | — | 已停用的旧入口，不发送请求 |
| `following.json/.csv` | fetch_following.py | 完整采集后才替换的全量关注（含 `visit_rank`） |
| `following.partial.json` | fetch_following.py | 中断进度，`complete=false`，不当作完整列表 |
| `following_videos.json` | fetch_videos.py | 每人近期投稿标题 |
| `labels_XX.json` | 打标（推荐 subagent） | 内容定位标签 |
| `classify_rubric.md` | — | **分类判定唯一口径**：类型判据、反例、输出字段 |
| `chunks_analysis/aXX.json` | analyze_split.py | 分类输入（最近 8 条标题 + 粉丝/`rank_pct`/`fans_pct`/相似账号） |
| `chunks_analysis/all_accounts.json` | analyze_split.py | 全员瘦身表，判信息重复时跨块对比 |
| `overrides.json` | 用户/Agent 手工修正 | 按 mid 覆盖这份列表的类型/优先级/理由；不进 skill 口径，已 gitignore |
| `combined.json` | build_selector.py | 合并后的主数据 |
| `selector.html` | build_selector.py | 勾选网页 |
| `map.html` | visualize.py | 关注图谱与清理过场，内嵌数据和勾选页面 |
| `graph_tags_split.py` | — | 切图专用标签输入（20 条标题，每人 6–10 个带权标签） |
| `graph_tags/out_XX.json` | 图标签 subagent | 每块图专用标签 |
| `merge_graph_tags.py` | — | 合并校验 -> `graph_tags.json` |
| `graph_tags.json` | merge_graph_tags.py | 图专用标签（`visualize.py` 自动读取；个人数据，已 gitignore） |
| `analyze_out_XX.json` | 分类（推荐 subagent） | 类型/优先级 |
| `verify_analysis.py` | — | 分类自检：覆盖率 + 分布护栏（类型 4 为 0、6 过大、11 误判等） |
| `unfollow.txt` | 用户/网页导出 | 待取关 mid 列表 |
| `unfollow_log.json` | unfollow.py | 取关结果 |
| `retry_log.json` | retry_unfollow.py | 补做结果 |
