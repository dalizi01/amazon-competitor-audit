---
name: amazon-competitor-audit
description: 亚马逊竞品分析并填入金山文档（kdocs）「运营难度分析」表格。覆盖 ASIN 筛选、基础数据列、竞品主图嵌入（DISPIMG 单元格内嵌）、广告数据（广告组数/SP广告词/自然词）、卖点翻译、机会点、运营手段八点判定（广告/合并评论/Vine/刷单/品牌/站外/老带新/上架时间早）。当用户说「竞品分析」「运营难度」「八点分析」「把竞品填进 kdocs/金山表格」「选品调研」「竞品主图嵌入」时使用。依赖：用户本机装有卖家精灵的 Chrome 内核浏览器（360/Chrome/Edge，带 CDP 调试端口）、Python3+openpyxl、kdocs 访问通道（优先 MCP，或用 kdocs-cli）；卖家精灵与 kdocs 需保持登录态。
---

# 亚马逊竞品分析 → kdocs「运营难度分析」表

标准作业流程。目标产物：一张 N 个竞品 × 16 列的分析表，其中「运营手段」列是按固定 8 个维度做的实证判定。

## 0. 环境常量（先确认，各机器路径可能不同）

```
浏览器     : 任意 Chrome 内核（360se / Chrome / Edge），必须带 --remote-debugging-port=9222 启动
CDP 端口   : 127.0.0.1:9222
kdocs-cli  : 用 `kdocs-cli`（见脚本 kdocs_sheet.py 的 KDOCS_CLI 环境变量 / PATH 探测）
Python     : python3（需 openpyxl）
脚本目录   : <skill>/scripts/
```

**scripts/ 清单（7 个脚本）**

| 脚本 | 作用 |
|---|---|
| `cdp360.py` | Chrome 内核浏览器 CDP 客户端（raw socket，握手不发 Origin；`Browser(port=)` 可换端口） |
| `ss_review.py` | 评论采集：Vine / 各站点评论数 / 近30天评论数（含 `wait_ready` 探测 + Vine 扫描兜底） |
| `ss_variants.py` | 插件「变体对比」采集：父体各变体上架时间 + 近30天销量(父体)（判定 #7 老带新、#4 刷单分母） |
| `kdocs_sheet.py` | kdocs 写入 / 逐行校验 / 清行 / 行高（0-based；`_find_kdocs` 自动定位 CLI） |
| `setup_env.py` | 环境自检：Python / openpyxl / kdocs 通道 / CDP / 登录态提示（`--install` 自动装 openpyxl） |
| `xlsx_fix.py` | 修卖家精灵 xlsx 的 `editAs="undefined"`（`load_workbook_safe`） |
| `gen_html.py` | 八点判定可视化汇总 HTML |

**可移植配置（不必改代码）**
- 浏览器路径：环境变量 `BROWSER_EXE` 指定；否则脚本自动探测 360se/chrome/msedge。
- kdocs 访问：**优先用当前 agent 环境的 kdocs MCP 工具**（如 `mcp__jinshanwendang__*`）读写表格，不依赖 kdocs-cli。`kdocs_sheet.py` 只是 CLI 封装，仅当用命令行读写时才需要 kdocs-cli（环境变量 `KDOCS_CLI` 指定，否则自动探测 PATH / 常见路径）。
- CDP 端口默认 9222，可改脚本里的 `PORT`。

**环境准备（新机器 / 新 agent 第一次跑，先做）**
1. 运行自检脚本，缺什么会给出指引：
   ```
   python <skill>/scripts/setup_env.py           # 只读自检
   python <skill>/scripts/setup_env.py --install # 自检 + 自动 pip install openpyxl
   ```
2. 常见缺失的处理：
   - **openpyxl 未装** → `python -m pip install openpyxl`（或 `setup_env.py --install`）。
   - **kdocs-cli 未找到** → 只要环境有 kdocs MCP（`mcp__jinshanwendang__*`）就不影响，读写表格走 MCP；脚本 `kdocs_sheet.py` 仅在你坚持用 CLI 时才需要装 kdocs-cli。
   - **CDP 端口 9222 未监听** → Chrome/Edge **单实例锁**是主因：浏览器正在运行时已占住「默认 profile」，再带调试端口去启动同一 profile 的进程**不会新建实例**，而是把参数转发给已在跑的旧实例——旧实例没有调试端口，所以 9222 起不来。两种启动法二选一：
     - **[复用已登录浏览器，保留登录态]**：先**彻底退出所有浏览器窗口**（含后台/启动加速进程），再带调试端口启动**默认 profile**（不加 `--user-data-dir`）：
       ```
       "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --remote-debugging-port=9222
       "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222
       ```
       这样 CDP 连的就是你平时登录卖家精灵/Amazon 的实例，登录态直接可用。
     - **[独立调试 profile，不打扰在用浏览器（skill 默认）]**：另开独立窗口 + 调试端口，登录态需在该窗口手动登录一次（此后持久保存）：
       ```
       "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir=C:\cdp-profile
       "C:\Users\<你>\AppData\Roaming\360se6\Application\360se.exe" --remote-debugging-port=9222
       ```
       360 是单实例锁，需同一进程启动+抓取（见脚本注释）。
   - **登录态（强前置）** → 关键是**CDP 连上的那个实例必须承载登录态**：
     - 用默认 profile（方案一）→ 已登录，直接用；
     - 用独立 profile（方案二）→ 无登录态，需用户手动扫码/登录一次卖家精灵 `sellersprite.com/v3/`、Amazon、kdocs（登录态持久保存在该 profile，不用每次重登）。
     agent 的浏览器接管（`interaction_request_action`）常被系统拒绝，不要依赖它，直接请用户在那个调试窗口登录。

**前置检查（必须全绿才开工）**
1. `python <skill>/scripts/setup_env.py` 输出无「缺」项。
2. **调试浏览器已登录卖家精灵**（`sellersprite.com/v3/`）：广告 + 评论都要；**未登录时第 4 个 ASIN 起会被风控拦截、跳转登录页**（见 §5）。由用户手动扫码登录。
3. **调试浏览器已登录 Amazon**（`amazon.com`，用于抓主图 #landingImage）。
4. **调试浏览器已登录 kdocs**（写表）。
5. CDP 端口通（独立调试 profile 已带 `--remote-debugging-port=9222` 启动）。

## 1. 流程总览

| Step | 内容 | 关键工具 |
|---|---|---|
| 1 | 从卖家精灵导出 xlsx 筛出 N 个竞品 | `scripts/xlsx_fix.py` + openpyxl |
| 2 | 建表 + 写基础数据列 | `scripts/kdocs_sheet.py` / kdocs MCP |
| 3 | 主图嵌入（DISPIMG 单元格内嵌） | kdocs MCP picture op / add-row |
| 4 | 广告数据（广告组数/SP广告词/自然词） | 卖家精灵网页版 + CDP |
| 5 | 产品卖点翻译 | 源数据文件 → 翻译 → 写入 |
| 6 | 机会点（市场洞察） | WebSearch 消费者反馈 |
| 7 | 运营手段八点判定 | 卖家精灵评论 API + WebSearch |
| 8 | 写入 + 逐行校验 | `scripts/kdocs_sheet.py` |

## 2. Step 1：筛选竞品

输入：卖家精灵关键词导出 xlsx（`Search(<keyword>)-<N>-US-<日期>.xlsx`）。

筛选链路：
1. 保留有效列，删月销量空值。
2. 计算 top5 月销均值，淘汰「老品 + 低销」。
3. **父体去重**。
4. **标题关键词过滤**，剔除混入其他品类的（例：搜"破窗器"会混进折叠刀、手电）。
5. **品牌去重**：每品牌只留月销最高的 1 个。
6. 按月销降序取前 N（通常 20）。

**坑：openpyxl 读卖家精灵 xlsx 报 `ValueError: Value must be one of {'absolute','twoCell','oneCell'}`**
解法：用 `scripts/xlsx_fix.py` 的 `load_workbook_safe()`——它解压后把 `xl/drawings/*.xml` 里的 `editAs="undefined"` 替换成 `"oneCell"` 再重打包。

**输出**：`picks.json`，每条至少含 `asin / parent / brand / price / sales / days / rev / rating / var / bsr / title / selling_points / img`。

## 3. Step 2：建表 + 基础数据列

列映射（**col 从 0 起**，col0 = A 列）：

| col | 列 | col | 列 |
|---|---|---|---|
| 0 | 竞品链接(ASIN) | 8 | 广告组数 |
| 1 | 竞品主图 | 9 | SP广告词 |
| 2 | 售价 | 10 | 自然搜索词 |
| 3 | 上架天数 | 11 | 广告强度(广告词/自然词) |
| 4 | 月销量 | 12 | 小类排名 |
| 5 | 变体数 | 13 | 产品卖点 |
| 6 | 评分 | 14 | 机会点 |
| 7 | 评论数量 | 15 | 运营手段(八点) |

**⚠ 写入铁律（最重要，务必遵守）**
1. `row_from` 是 **0-based**：表头 → `0`；第 1 条数据 → `1`；第 k 条 → `k`。写错整列错位一行且 API 仍返回成功。
2. **文本列**（ASIN/BSR/卖点/机会点/八点/主图直链）→ formula op，`formula` 直接放字符串，**不带等号**。
3. **数值列**（售价/上架天数/月销/变体/评分/评论数/广告组数/SP词/自然词/广告强度）→ `formula` **必须带等号**：`=8.49`、`=1354`。写纯数字字符串（`"8.49"`）**不会落格，单元格为空**（但 API 仍返回 code=0 成功，极具迷惑性）。
4. **A 列竞品链接写成超链接**（用户要可点击）：`=HYPERLINK("https://www.amazon.com/dp/<ASIN>","<ASIN>")`。

正确 op（kdocs MCP `sheet_range_data_batch_update` / `range-data-batch-update`）：
```json
{"op_type":"cell_operation_type_formula","row_from":1,"row_to":1,"col_from":2,"col_to":2,"formula":"=8.49"}
```

写完后必须校验（见 Step 8）。

## 4. Step 3：主图嵌入（col1）

**⚠ kdocs 图片服务间歇性「服务暂时不可用」(500000)**，内嵌图接口、浮动图接口都可能时好时坏。遇到先隔几秒重试；持续失败则**退化为可点击图片直链文本**（先保证列不空），等服务恢复再补嵌。

取主图 URL：CDP 打开 `https://www.amazon.com/dp/<ASIN>` 抓 `#landingImage` 的 src（也可直接用源 xlsx / picks.json 的 `img` 字段）。正则清洗：把 `._AC_[A-Za-z0-9_]+\.jpg$` 统一替换成 `._AC_SL1500_.jpg`（否则缩略图糊）。

内嵌方式（按可靠性排序）：
1. **首选（DISPIMG 单元格内嵌，用户最认可）**：`add-row` 追加临时行（A=ASIN 标记，B=picture op，`cell_pic_info.width/height` 单位 **twips**，1500≈100px）→ `get-range-data` 读回 `=DISPIMG("ID_xxx",1)` 公式按 ASIN 配对 → 写 `=DISPIMG("ID_xxx",1)` 到目标 B 列 → `delete-range-data shift_up` 删临时行。
2. `batch_update_range_data` 的 picture op：`opType=picture`，图片来源字段（`url`/`image_url`/`pic_content`）实测不稳定。**注意 `upload_attachment` 返回的 `object_id` 不能用于 `=DISPIMG("ID_xxx",1)`（会 `#REF!`）**——DISPIMG 需要 kdocs 生成的 cell-image 资源 ID（形如 `ID_xxxx`），只能靠 picture op / add-row 生成。
3. `create_float_images`（浮动图）：可用远程 URL，但定位脆弱、可能遮挡相邻列，仅作备选。

## 5. Step 4：广告数据（col8/9/10/11）

**广告数据必须登录态**：关键词反查 + 广告洞察页游客态**前 3 个 ASIN 可抓，第 4 个起被卖家精灵风控拦截、跳转登录页**（等待重试无效，独立 profile 新会话同样被拦）。因此必须先在调试浏览器登录卖家精灵，全程用登录态抓；评论 API（§7.2）同样要求登录态。数值**带千分位逗号**（`1,931`），正则要处理逗号。

**col9 SP广告词 / col10 自然搜索词** — 关键词反查页（CDP navigate 自动查询）：
```
https://www.sellersprite.com/v3/keyword-reverse?q=<ASIN>&marketId=1
```
解析 innerText：`自然搜索词 (N)`、`SP广告词 (N)`、`品牌广告词 (N)`、`视频广告词 (N)`、`全部流量词(N)`（无括号 = 0）。数值带千分位，正则 `(\d[\d,]*)` 再 `replace(',','')`。

**col9「SP广告词」列的口径（用户确认，务必执行）**：`col9 = SP广告词 + 品牌广告词 + 视频广告词`（付费广告词总量），不是单独的 SP。

**col8 广告组数** — 广告洞察页：
```
https://www.sellersprite.com/v3/ads-insights?q=<ASIN>&marketId=1&interval=week&desc=false
```
解析 `共计有：N个投放小组`。页面显示"未能找到对应的广告活动及广告组" → **记 0，不是抓取失败**。

**col8 广告组数的口径（用户确认，务必执行）**：= **整个父体 Listing 的投放小组数**（页面标题「该 Listing...」下会混入父体其他变体的广告组），不是单个子体。且该指标**动态变化**（投放调整/时间段/缓存都影响），不同时刻值可能不同。

**col11 广告强度** = (SP+品牌+视频) / 自然搜索词 = col9 ÷ col10，保留 2 位小数。

**流量控制**：每个 ASIN 间隔 5~10s，单次 ≤20 个，防浏览器崩溃/限流。

## 6. Step 5/6：卖点翻译（col13）与机会点（col14）

**卖点翻译坑**：`get-range-data` 的 cellText 截断到 500 字符。长文本一律从源数据文件（`picks.json` 的 `selling_points`）取，不靠 API 读回。翻译时**保留英文**：品牌名、材质型号（440C/420HC）、认证（TUV）、单位（英寸/盎司/°C）、专有名词。

**机会点**（col14，300~380 字）：①产品是什么（形态/材质/价格/变体数）→ ②为什么卖得好（数据+消费者心理）→ ③可借鉴的 3~5 条动作。来源用 WebSearch 查行业研究/第三方测评/真实买家评价，**要带数据的实证，不编**。

## 7. Step 7：运营手段八点判定（核心）

八点固定：`广告 / 合并评论 / Vine / 刷单 / 品牌 / 站外 / 老带新 / 上架时间早`

### 7.1 判定口径表（严格执行，不要自创）

| # | 维度 | 判定标准 | 数据源 | 阈值 |
|---|---|---|---|---|
| 1 | 广告 | 广告词/自然词 | 变体流量对比/关键词反查 (SP+品牌+视频)/自然 | ≥0.5 → ✓ |
| 2 | 合并评论 | 是否存在除美国外其他地区评论 | 卖家精灵 comment API 的 `market` 参数查多站点 | 非美站点评论数 >0 → ✓ |
| 3 | Vine | 是否存在 Vine 评论（要真实条数） | `review-analysis/type/US/{asin}` 的 `vine` 字段 | >0 → ✓ |
| 4 | 刷单 | 近30天留评率 | 近30天评论数 ÷ 近30天销量（**分母优先用「近30天销量(父体)」**，来自插件「变体对比」tab，见 §7.2.2） | >3% → 疑似；否则未见 |
| 5 | 品牌 | 是否有独立站且售同款 | WebSearch | 有→✓；有但品类不符→△ |
| 6 | 站外 | 独立站+社媒+红人测评+Deal站 | WebSearch 逐品牌 | 任一有实证→有 |
| 7 | 老带新 | 该链接是否存在上架更早的 ASIN | **首选**：插件「变体对比」tab（`ss_variants.py`）拿父体全部变体 `days`，本链与之比较；无此数据时退回全量数据按 `parent` 分组取最小 `days` | 存在上架更早 ≥31 天→✓；同期(≤30天)→✗ |
| 8 | 上架时间早 | 上架天数 | 源数据 | ≥1095 天（3年）→ ✓ |

**老带新口径**：**首选插件「变体对比」tab**（`ss_variants.py`，见 §7.2.2）拿父体全部变体的 `days`，本链 `days` 与之逐项比较：存在变体 `days > 本链days + 30` → ✓（有上架更早的兄弟变体）；有更早但差距 ≤30 天 → ✗（同期上架，别写"本链最早"）；本链就是最早 → ✗（是老带新主体）。仅当拿不到变体对比数据时，退回从筛选前全量 `all_rows.json` 按 `parent` 分组算组内最小 `days`；本链 `days > parent_min` → ✓（注意筛选后父体组可能不完整，只能得"无更早证据"非绝对结论）。

### 7.2 卖家精灵评论 API（关键能力）

在**登录态且扩展与网页端账号一致**的 `sellersprite.com/v3/` 页面上下文里用 CDP `Runtime.evaluate` 发 fetch（带 `credentials:'include'`）：

```javascript
// ① 评论类型统计 → vine 真实条数（只有 market=US 返回数据）
fetch('/v3/api/review-analysis/type/US/<ASIN>', {credentials:'include'})
// → {data:{image,verified,video,vine,totalReview}, success:true}
// ② 逐条评论（按日期降序，最新在前）
fetch('/v3/api/review-analysis/comment', {method:'POST',credentials:'include',
  headers:{'Content-Type':'application/json'},
  body: JSON.stringify({asin:'<ASIN>', market:'US', pageNum:1, pageSize:100})})
// → {data:{total, items:[{date,star,vine,verified,free,market,skus,author,...}]}}
```

**⚠ 关键前置：网页端与扩展端登录账号必须一致。** 若网页已登录但评论 API 返回 `ERR_LOGIN_ACCOUNT_INCONSISTENT`（"插件端和网页端登录账号不一致"），说明浏览器里的卖家精灵扩展登录的是另一账号——需用户在扩展里切到与网页端一致的账号后才能批量跑评论分析。未解决前 #2/#3/#4 三点只能标「待补」，不得编造。

`market` 参数可切站点：`US/CA/UK/DE/JP/FR/IT/ES`，各站点返回各自评论总数 → 判定「合并评论」的唯一可靠途径。

已封装成脚本（一次跑完 20 个 ASIN 约 3 分钟）：
```
python scripts/ss_review.py --picks picks.json --out reviews.json
# 输出每个 ASIN: {vine, counts:{US:n,CA:n,...}, non_us:{...}, n30, sales, rate30}
```

### 7.2.1 评论 API 实战坑（旅行药盒项目实测，务必先读）

1. **`type/US` 会报 `ERR_LOGIN_ACCOUNT_INCONSISTENT`（插件端与网页端登录账号不一致），Vine 拿不到。**
   `ss_review.py` 已内置兜底：全量扫描 US 评论条目的 `vine` 布尔字段（pageSize 上限 200，约 4400 条/11 秒），
   `vine_src` 标记为 `scan`。账号不一致未解决前可用兜底近似，但**判定结论须注明来自扫描**（如 `Vine:✓(扫描N条含M条Vine)`）。
2. **comment API 的 `total` ≠ Amazon 页面 ratings 数**：Amazon 的"34,111 ratings"含纯星级评分，
   卖家精灵只索引带文字的评论（可能只有 4,411）。两者口径不同，别当数据错误；用全量扫描算出的 n30
   与 `trend/detail` 月度评论数一致，可直接用。
3. **fetch 的 body 只能 `json.dumps` 一次**：写成 `JSON.stringify(json.dumps(...))` 会让 body 变成
   JSON 字符串而非对象，服务端解析不到参数 → **静默返回 total=0，不报错**。脚本已按此修正。
   另外「页面渲染出菜单」≠「接口登录态就绪」，脚本已加 `wait_ready()`：先用第一个 ASIN 探测 API
   真返回数据再批量抓，否则等 5s 重试（最多 120s）。

**⚠ 抓完必须看一眼数字是否全 0** —— 全 0 = 上面第 3 条或登录态掉了，不是"该 ASIN 真没评论"。

**月度评论趋势 API**（判断近30天评论数是否与全量采样一致，可选）：
```javascript
fetch('/v3/api/review-analysis/trend/detail?asin=<ASIN>&market=US&parent=undefined', {credentials:'include'})
```

### 7.2.2 老带新（#7）与刷单（#4）数据源 —— 插件「变体对比」tab（`ss_variants.py`）

Amazon dp 页插件浮窗 → tab **「变体对比(N)」**（不是「变体流量对比」！两个 tab 名字很像），表格每行含
`变体ASIN / SKU / 价格 / 月销量(父) / 流量词数 / 评分 / 评论数 / FBA / 上架时间(YYYY-MM-DD(N,NNN天))`。

同一面板顶部还有 **`近30天销量(父体)`** —— 这是 **#4 刷单分母的正确口径**（评论是父体共享的，分母也用父体销量）。

老带新判定（阈值 30 天）：
- 存在变体 `days > 本链days + 30` → ✓（`父体N个变体中M个上架更早,最早X天>本链Y天`）
- 有更早但差距 ≤30 天 → ✗（`属同期上架`，别写"本链最早"——那是事实错误）
- 本链就是最早 → ✗（`是老带新主体;其余变体a~b天`）

已封装脚本（含 `Page.bringToFront` + reload 重试，20 个 ASIN 约 8 分钟，断点续采）：
```
python scripts/ss_variants.py --picks picks.json --out variants.json
# → {asin: {days, date, sales30, n_var, variants:[{asin,date,days}, ...]}}
```
走这个 tab 前**必须 `Page.bringToFront`**（见 F5），否则扩展不注入；页面加载慢时 `Page.reload` 重试一次。
实测 360 浏览器失败率约 50%，跑一轮后重跑一次即可补齐（`variants` 为空会自动重试；`--force` 强制重启浏览器）。

### 7.3 站外核查

逐个品牌 WebSearch 四类渠道：A 独立站（品牌名 official website + 是否售同类）、B 社媒（TikTok/IG/YT/FB 官方号）、C 红人测评、D Deal 站（Slickdeals/DealNews/Woot/Groupon）。**只报告实际搜到的证据，给真实 URL；搜不到写"未发现"；同名不同行业标注"同名但不相关"判为未发现。禁止推测、禁止编造 URL。** 品牌多时派子代理并行。

### 7.4 输出格式

每点 `序号.维度:判定(数据依据)`，8 点用 `\n` 连接（kdocs 单元格换行就是写 `\n`）：
```
1.广告:✗(0.13<0.5,广告词96/自然词749,以自然流量为主)
2.合并评论:✓(存在非美地区评论3399条:DE1594/JP633/FR515/UK250/ES203/IT181/CA23)
3.Vine:✓(明显存在37条Vine评论)
4.刷单:未见(近30天3评/14820销=0.02%)
5.品牌:✓(AmazonBasics亚马逊自有品牌,平台流量倾斜)
6.站外:有(第三方测评博客曝光,非品牌主动投放)
7.老带新:✗(本链3158天为组内最老,另有125天新变体挂靠,是老带新的主体)
8.上架时间早:✓(3158天,约8.7年)
```

## 8. Step 8：写入 + 校验（强制）

```
# 文本列用 kdocs_sheet.py write；数值列必须用带等号的 formula（见 §3）
python scripts/kdocs_sheet.py write --file <ID> --ws <ID> --col 15 --data p_col.json --start-row 1
python scripts/kdocs_sheet.py verify --file <ID> --ws <ID> --key-col 0 --col 15 --expect picks_asin.json
```

**校验是强制步骤。写入返回"20/20 成功"不代表内容落在正确的行，也不代表数值真的落格。**

**两种读回方式用途不同：**
1. **文本列**（A/B/M/N/O/P）→ `get-range-data` 的 `cellText` 或 `get_typed_value`。
2. **数值列**（C~L）→ **必须用 `get_typed_value`**（返回 `type=double` + 真实数值）。`get-range-data` 的 `cellText` 对数值单元格**不可靠/常返回 null**，用它校验数值列会误判"没写入"。

**kdocs-cli 输出尾部会追加升级提示**（`⚠ kdocs-cli v2.7.1 available...`），`json.loads` 直接解析会报 "Extra data" → 全部 MISMATCH。解析前剥离：`out = out[: out.rfind('}') + 1]`（`kdocs_sheet.py::read_col` 已内置此剥离）。

**行高**（八点列需 8 行高度）：`set-range-width-height`，range 是对象 `{"row_from":1,"row_to":20,"col_from":15,"col_to":15}`，height=2160 twip≈144px。**不要用 auto-fit**（机会点列 350 字会把行撑到 200px+ 拉变形主图列）。auto-fit 的 range 是 A1 字符串（"2:21"），与 set-range-width-height 的对象格式**别混用**。

## 9. 故障速查

- **F1 CDP 端口不通/浏览器消失**：360 单实例锁 + 进程随命令回收。`taskkill /F /IM 360se.exe` → 重启带 `--remote-debugging-port=9222`；**启动浏览器和抓取必须写在同一个 Python 进程/同一条命令里**。
- **F2 urllib 连 127.0.0.1 返回 502**：系统代理劫持。用 `urllib.request.build_opener(urllib.request.ProxyHandler({}))`；判端口用 **raw socket connect**。
- **F3 WS 握手 403**：手写 WS 客户端**不要发 Origin 头**。
- **F4 `/json/new` 405**：用浏览器级 WS + `Target.createTarget`/`attachToTarget(flatten=True)`。
- **F5 卖家精灵浮窗数据全空**：`createTarget` 用 `about:blank` 不带尺寸 → navigate → **`Page.bringToFront`**（顺序不能反）→ 等扩展容器。
- **F6 Amazon 评论页只返回 8 条且全 US**：Amazon 对自动化浏览器降级。**不要走 Amazon 评论页做地区判定**，走卖家精灵 `market` 参数。
- **F7 卖家精灵 AI 评论报告生成但内容提取不出**：此路不通，直接用 §7.2 内部 API。
- **F8 写入成功但整列错位一行**：`row_from` 是 0-based，误用表格行号。写完必须校验。
- **F9 kdocs opType 报错**：只支持 `cell_operation_type_formula/format/merge/picture`，不支持 value。写文本也用 formula op（文本放 `formula` 字段）。
- **F10 数值列写入后是空的**：formula 写了纯数字字符串（`"8.49"`）。**必须带等号** `=8.49`；用 `get_typed_value` 读回确认。
- **F11 长文本读回截断到 500 字符**：从源数据文件取，不靠 API。
- **F12 Bash 的 PATH 被破坏（`dirname`/`cd`/`tail`/`cat` 全 command not found）**：shell 会话状态不跨命令、环境变量在子进程丢失。改用绝对路径的 python，输出重定向到文件再用 python 读回。
- **F13 批量跑 ASIN 后浏览器崩溃**：每 ASIN 间隔 5~10s，单次 ≤20；备用数据源：关键词反查网页版。
- **F16 kdocs 图片服务"服务暂时不可用"(500000)**：间歇性。隔几秒重试；持续失败退化为主图直链（见 §4）。
- **F17 `upload_attachment` 的 object_id 不能用于 DISPIMG**：会 `#REF!`。DISPIMG 需 kdocs 生成的 cell-image 资源 ID（`ID_xxx`），走 picture op/add-row 方式（见 §4）。

## 10. 禁止事项

1. 禁止凭印象写判定——每个 ✓/✗ 必须跟具体数字或实证来源。
2. 禁止编造 URL——站外核查搜不到就写"未发现"。
3. 禁止跳过校验——写入成功不等于落对行/数值落格。
4. 禁止用 Amazon 评论页做地区/Vine/近30天评论判定（已降级）。
5. 禁止 auto-fit 长文本表（会拉变形主图列）。
6. 禁止数值列不带等号写入（会空但报成功）。
7. 禁止用 `get-range-data` 校验数值列。

## 11. 交付物

- kdocs 表格（全部列填完 + 校验通过）。
- 可视化汇总 HTML（可选，`scripts/gen_html.py`）。
- 中间数据 JSON：`picks.json` / `reviews.json` / `variants.json` / `p_col*.json`。
