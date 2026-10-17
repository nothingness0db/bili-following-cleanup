# bili-following-cleanup

把 B 站「关注列表」整理成可筛选清单，并批量取关。适合关注了几百个人、想按「这人是做什么的」来清理的场景。

> 这是一个 opencode / Claude 技能（也是可直接运行的脚本集）。把本目录放进技能目录即可被 agent 加载使用；或按下面的步骤手动跑脚本。

## 它做什么

1. **拉全量关注** —— 登录态分页读取，导出 JSON/CSV。
2. **判断每个号是做什么的** —— 抓每人最近 6 个投稿标题，由 subagent 给出内容定位标签。
3. **本地网页勾选** —— `selector.html`，搜索/按内容分类/勾选/导出待取关列表。
4. **（可选）分类打分** —— 按 8 种取关判断给类型 + 优先级。
5. **（可选）补粉丝量** —— 免登录接口，辅助判断「信息重复」。
6. **批量取关** —— 带随机延时 + 风控退避与重试。

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
python split_chunks.py          # 交给 subagent 打标 -> labels_XX.json

# 3) 生成勾选网页
python build_selector.py        # 打开 selector.html，勾选后导出 unfollow.txt

# 4) 取关（先不带 --yes 会二次确认）
python unfollow.py
# 若出现 -352 风控：把失败 mid 写入 retry.txt
python retry_unfollow.py
```

## 目录

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
   ├─ split_chunks.py            # 切块给 subagent 打标
   ├─ analyze_split.py           # 切块给 subagent 分类
   ├─ build_selector.py          # 合并 + 生成 selector.html
   ├─ unfollow.py                # 批量取关
   └─ retry_unfollow.py          # 风控失败重试
```

## 安全与合规

- `cookie.txt` 是你的登录凭证，等价于账号密码的一部分：**不要提交、不要分享**。`.gitignore` 已默认忽略。
- 所有运行产出的数据（`*.json`、`selector.html` 等）也已在 `.gitignore` 中。
- 批量取关可能触发 B 站风控（返回 `-352`）。请放慢节奏、控制数量，自行承担账号风险。
- 本项目仅供个人整理自己的关注列表使用。
