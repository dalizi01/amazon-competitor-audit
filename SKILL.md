---
name: amazon-competitor-audit
description: 亚马逊竞品分析并填入金山文档（kdocs）「运营难度分析」表格。覆盖 ASIN 筛选、基础数据列、竞品主图嵌入（DISPIMG 单元格内嵌）、广告数据（广告组数/SP广告词/自然词）、卖点翻译、机会点、运营手段八点判定（广告/合并评论/Vine/刷单/品牌/站外/老带新/上架时间早）。当用户说「竞品分析」「运营难度」「八点分析」「把竞品填进 kdocs/金山表格」「选品调研」「竞品主图嵌入」时使用。依赖：用户本机装有卖家精灵的 Chrome 内核浏览器（360/Chrome/Edge，带 CDP 调试端口）、Python3+openpyxl、kdocs 访问通道（优先 MCP，或用 kdocs-cli）；卖家精灵与 kdocs 需保持登录态。
---

# 亚马逊竞品分析 → kdocs「运营难度分析」表

标准作业流程。目标产物：一张 N 个竞品 × 16 列的分析表，其中「运营手段」列是按固定 8 个维度做的实证判定。

> **⚠ 开工第一步（强制）**：先跑 `python <skill>/scripts/setup_env.py`（只读自检），检查 Python / openpyxl / kdocs 通道 / CDP 端口 / 登录态。**缺什么它会直接给修复指引**。未全绿不要开始抓数或写表——否则同一个根因会以各种奇怪报错在中途冒出来，比事前自检费时得多。

## 0. 环境常量（先确认，各机器路径可能不同）

```
浏览器     : 任意 Chrome 内核（360se / Chrome / Edge），必须带 --remote-debugging-port=9222 启动
CDP 端口   : 127.0.0.1:9222
kdocs-cli  : 用 `kdocs-cli`（见脚本 kdocs_sheet.py 的 KDOCS_CLI 环境变量 / PATH 探测）
Python     : python3（需 openpyxl）
脚本目录   : <skill>/scripts/
```

**scripts/ 清单（8 个脚本）**

| 脚本 | 作用 |
|---|---|
| `cdp360.py` | Chrome 内核浏览器 CDP 客户端（raw socket，握手不发 Origin；`Browser(port=)` 可换端口） |
| `ss_review.py` | 评论采集：Vine / 各站点评论数 / 近30天评论数（含 `wait_ready` 探测 + Vine 扫描兜底） |
| `ss_variants.py` | 插件「变体对比」采集：父体各变体上架时间 + 近30天销量(父体)（判定 #7 老带新、#4 刷单分母） |
| `kdocs_sheet.py` | kdocs 写入 / 逐行校验 / 清行 / 行高（0-based；`_find_kdocs` 自动定位 CLI） |
| `setup_env.py` | 环境自检：Python / openpyxl / kdocs 通道 / CDP / 登录态提示（`--install` 自动装 openpyxl） |
| `xlsx_fix.py` | 修卖家精灵 xlsx 的 `editAs="undefined"`（`load_workbook_safe`） |
| `gen_html.py` | 八点判定可视化汇总 HTML |
| `ss_voc.py` | **评论分析(VOC)采集**：生成/读取评论分析报告，产出「差评点 + 认可点 + 风险 + 根因」→ 供 col14 机会点（见 §6.1） |

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
| **0** | **环境自检 + 前置检查（必须全绿才开工，详见 §0）** | `scripts/setup_env.py` |
| 1 | 从卖家精灵导出 xlsx 筛出 N 个竞品 | `scripts/xlsx_fix.py` + openpyxl |
| 2 | 建表 + 写基础数据列 | `scripts/kdocs_sheet.py` / kdocs MCP |
| 3 | 主图嵌入（DISPIMG 单元格内嵌） | kdocs MCP picture op / add-row |
| 4 | 广告数据（广告组数/SP广告词/自然词） | 卖家精灵网页版 + CDP |
| 5 | 产品卖点翻译 | 源数据文件 → 翻译 → 写入 |
| 6 | 机会点（**listing + 评论差评点/可借鉴点**，见 §6.1） | 评论分析页标签聚类 + comment API + WebSearch |
| 7 | 运营手段八点判定 | 卖家精灵评论 API + WebSearch |
| 8 | 写入 + 逐行校验 | `scripts/kdocs_sheet.py` |

## 2. Step 1：筛选竞品

输入：卖家精灵关键词导出 xlsx（`Search(<keyword>)-<N>-US-<日期>.xlsx`）。

筛选链路：
> **销售额口径**：以下「销售额」= 月销量 × 售价，比纯销量更能反映真实市场体量（高价低频 vs 低价高频用销量排会失真）。涉及销量/销售额判断的步骤均按此口径执行。
1. 保留有效列，删月销量空值。
2. 计算 top5 月**销售额**均值，淘汰「老品 + 低销」。
3. **父体去重**。
4. **标题关键词过滤**，剔除混入其他品类的（例：搜"破窗器"会混进折叠刀、手电）。
5. **品牌去重**：每品牌只留月**销售额**最高的 1 个。
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

### 6.1 机会点（col14）：必须「listing + 评论」双源，缺一不可

**结构（三段式，固定，300~400 字）—— 2026-10-08 用户确认口径**：
① **产品**（形态 / 材质 / 价格 / 变体数 + 基本盘：月销 / BSR / 评分 / 评论数）→ ② **差评点**（逐项带条数与占比 + 根因）→ ③ **可借鉴**（3~5 条动作，每条对应一个差评点或一个已被验证的有效设计）。

**三段式模板（照此写，勿自创结构）**：
```
产品：<形态/材质/价格/变体数>。基本盘：月销 N 件、小类 BSR 第 N、N 天累积 N 评分。
差评点：<标签> N 条(NN.N%)、<标签> N 条(NN.N%)、……；根因：<一句话>。
可借鉴：① <动作>；② <动作>；③ <动作>；④ <动作>；⑤ <动作>。
```
三段**均须带真实数字**，数字取自 `voc_insight.json`；差评点按条数降序取 Top 5~9 项。

**⚠ 只从 listing 写机会点是错的**——listing 是**卖家自我主张**（王婆卖瓜），评论才是**买家真实体验**。两个源都要查：

| 源 | 取什么 | 回答什么问题 |
|---|---|---|
| **A. Listing** | 五点描述 / 亮点 / A+ / 变体矩阵 / 价格 / 尺寸 | 卖家**主张**解决了什么 |
| **B. 评论** | ① **差评点**（1~3 星 + 属性标签聚类）② **正面高频词** | 买家**真实**吐槽什么、反复夸什么 |

**评论分析必须产出两类结论：**

- **差评点 —— 找"坑"（要规避）**：竞品被反复吐槽什么（盖子易弹开 / 药片受潮 / 标识磨损 / 尺寸放不进包 / 药片混串）。
  → 用途：**我们做同款时不要重复这些缺陷**；若我们能解决，它就是差异化卖点。
- **可借鉴点 —— 找"对的事"（要继承）**：正面评论反复夸什么（同侧开盖 / 可拆单日盒 / 硅胶密封圈 / 大出药口）。
  → 用途：这些是**已被市场验证的有效设计**，直接抄作业，降低试错成本。

**⚠ 差评点必须带实证数字，且必须是本条 ASIN 自身的评论数据**（不可回溯的行业级聚合数不得冒充本品结论），格式：
```
差评点：体积过大 76 条(15.2%)、填装药物繁琐 39 条(7.8%)、开盖困难 35 条(7.0%)……（样本 n=499）
```
禁止写「有差评」「体验一般」「存在不足」这类**无数据结论**（违反 §10 第 1 条）。

**评论数据通道（按可靠性排序）：**

1. **评论分析页 · 属性标签聚类（首选，硬数据）** —— 2026-10-08 实测路径
   - **新版（推荐，无需插件）**：`https://www.sellersprite.com/v3/ai-review-analysis`
     可直接**输入单个 ASIN 生成报告**。操作三步：① 站点选「美国站」→ ② 输入框（`el-input__inner`，`placeholder="请输入单个ASIN 如: B00FLYWNYQ"`）填 ASIN → ③ 点「生成报告」按钮（`button` 内含文本 `生成报告 (消耗10次)`）。
   - **旧版**：`https://www.sellersprite.com/v3/review-analysis?q=<ASIN>` —— 需先经**插件端**（dp 页扩展面板「AI 评论分析」）收集评论建报告，否则页面显示"您暂未创建评论分析报告"、`label` API 返回空数组。
   - **⚠ 消耗配额**：生成 1 个报告 = **10 次**。查余额 `GET /v3/api/ai-analysis/daily-remaining-quota`（实测 **100/天** → **每天最多 10 个 ASIN**）。20 个竞品要分 2 天，**先算配额再动手**。
   - **⚠ 异步**：提交后状态 `PREPARING`（页面提示"预计 3–5 分钟"），任务在**服务端**跑，**浏览器关了也继续**；读数据前必须轮询等 `status` 完成。
   - **报告列表**：`GET /v3/api/review-analysis/list?market=US&pageSize=500`（**`asin`/`q` 参数被忽略**，这是"我的报告列表"不是查询接口）。每条含 `rating / ratings / reviews / firstReviewDate / lastReviewDate / analysisTime / status`。
   - **VOC / 标签数据**：`POST /v3/api/review-voc/list`（**必须 POST**，GET 返回 405）；报告未完成时返回 `total:0`。相关：`/v3/api/review-analysis/label`（返回 `marketList` 12 站点 + `labelList`）、`/v3/api/review-analysis/label/list`。
   - ⚠ 该功能需**登录**（实测账号 XY556688 可用）；游客态被拦到落地页。
2. **comment API · 星级与时间分布（辅助，无需额外权限）**
   `POST /v3/api/review-analysis/comment`，items 每条含 `star`(1~5) / `date` / `vine` / `verified` / `market` / `skus` / `author`。
   → 可算**低星占比**、**差评时间趋势**（判断某缺陷是否已在新批次修复——若近期仍集中出现，说明**尚未修复，是可打的空档**）。
   ⚠ 该接口返回**结构化元数据，不含评论正文**——要原文得从评论分析页或 dp 页取。
3. **WebSearch**：行业研究 / 第三方测评 / 论坛，做市场规模与趋势背书（可量化最好，如 CAGR）。

**写作要点**：① 段用基本盘数据说明"这款为什么值得研究"；② 段**逐项列差评点，每项必须带条数**——差评点就是我们要抢的空档；③ 段每条可借鉴动作都要**挂钩②段的某一个差评点**（如"铰链加加强筋并承诺开合次数——对应 33 条断裂风险"），让结论可执行，而不是泛泛而谈。

### 6.2 评论分析(VOC)脚本与数据结构 —— 2026-10-08 全链路实测打通

**✅ 已封装脚本 `scripts/ss_voc.py`（推荐直接用，勿手写一遍）**
```bash
# 只读已有报告（不消耗配额，秒级）
python scripts/ss_voc.py --asins B0BQJ2XZWF --out voc_insight.json
# 报告不存在时提交生成（⚠ 消耗 10 次配额/个）
python scripts/ss_voc.py --picks picks.json --create --out voc_insight.json
```
实测输出：
```
配额: 90
[B0BQJ2XZWF] 已有报告 id=31781 状态=COMPLETED
[B0BQJ2XZWF] 差评点 9 项 [('体积过大',76), ('填装药物繁琐',39), ('开盖困难',35)]
[B0BQJ2XZWF] 认可点 4 项 [('容量充足',95), ('单日盒可拆卸',84), ('双重锁定稳固',53)]
```
脚本内置 raw-socket 版 `get_browser_ws_url`（规避 F24 的 stdin 阻塞），产出 `voc_insight.json`。

**数据结构**：`POST /v3/api/review-voc/task-detail` body `{"id":"<报告id>"}` → `data.data` 含 **6 个子 JSON**，值都是**转义 JSON 字符串，需二次 `json.loads`**：

| 子 JSON | 关键内容 | 用途 |
|---|---|---|
| **`aggregationsJson`** | **`negative_tag_distribution`（差评点+条数）**、`positive_tag_distribution`、`risk_tag_distribution`、`topic/rating/sentiment/scenario/journey_stage/category_specific_distribution` | **差评点 & 可借鉴点的直接来源（带数字）** |
| **`reportJson`** | `negative_root_causes`（差评根因：type/title/summary/cause分析）、`insights`、`usage_context_insights`（who/environment/task/goal/正负信号）、`opinion_divergences`（评价分歧）、`low_sample_clues`、`summary`（one_sentence/top_positive/top_negative/biggest_risks/main_scenarios） | 定性归因 + 场景洞察 |
| **`taggedReviewsJson`** | 逐条打标评论：`{review_id, rating, sentiment, topic_tags, journey_stage_tags, positive_tags, negative_tags, scenario_tags, risk_tags}` | 可自行统计低星占比、按标签筛评论 |
| **`evidenceSlicesJson`** | 每标签 `{tag, polarity, total_count, review_ids, selected_review_ids, slices}` | **可追溯到原文评论（写"查看证据"用）** |
| `tagLibraryJson` | `dynamic_tag_library` | 标签体系 |
| `resultJson` | `product_info`（asin/title/brand/price/rating/ratings/features/overviews）、`data_quality`（total_raw/total_valid_reviews/verified/image/video_count）、`degraded` / `degraded_reason`、`analysis_scope` | 元信息与数据质量 |

相关端点（全部在 `sellersprite.com` 域、`credentials:'include'`）：
| 端点 | 方法 | body / 说明 |
|---|---|---|
| `/v3/api/review-voc/list` | POST | `{asin, market}` 或 `{"ids":["<id>"]}` — 报告列表（含 `status`） |
| `/v3/api/review-voc/batch-get-report` | POST | **`{"ids":[<int>]}`** — 仅返回 `{id, ready}`，用于轮询 |
| `/v3/api/review-voc/task-detail` | POST | **`{"id":"<字符串>"}`** — 报告全量数据（上表 6 个子 JSON） |
| `/v3/api/review-voc/reviews` | POST | `{asin:"<父ASIN>", market, reviewIds:[...]}` — 评论原文 |
| `/v3/api/ai-analysis/daily-remaining-quota` | GET | 当日剩余配额 |
| `/v3/api/review-analysis/label` | GET | `marketList`（12 站点）+ `labelList` |

⚠ **`degraded: true` 的含义**：本次为**降级分析**（如 `degraded_reason: tagback_review_id_integrity_failed`）。数据仍完整可用，但**写进 col14 时必须注明**样本口径（如"本次分析样本 499 条"）。

⚠ **报告详情页**（人工核对用）：`/v3/ai-review-analysis/details?list=<id>&asin=<ASIN>`。

## 7. Step 7：运营手段八点判定（核心）

八点固定：`广告 / 合并评论 / Vine / 刷单 / 品牌 / 站外 / 老带新 / 上架时间早`

### 7.1 判定口径表（严格执行，不要自创）

| # | 维度 | 判定标准 | 数据源 | 阈值 |
|---|---|---|---|---|
| 1 | 广告 | 广告词/自然词 | 变体流量对比/关键词反查 (SP+品牌+视频)/自然 | ≥0.5 → ✓ |
| 2 | 合并评论 | 是否存在除美国外其他地区评论 | 卖家精灵 comment API 的 `market` 参数查多站点 | 非美站点评论数 >0 → ✓ |
| 3 | Vine | 是否存在 Vine 评论（要真实条数） | `review-analysis/type/US/{asin}` 的 `vine` 字段 | >0 → ✓ |
| 4 | 刷单 | 近30天留评率 | 近30天评论数 ÷ 近30天销量（**分母优先用「近30天销量(父体)」**，来自插件「变体对比」tab，见 §7.2.2） | >3% → 疑似；否则未见 |
| 5 | 品牌 | 五维判定，命中 ≥2 项即存在品牌效应（见 §7.2.3） | 见 §7.2.3（品牌搜索词 / A+品牌故事 / 站外自然推荐 / 同规格价格溢价 / 品牌独立站） | 5 项命中 ≥2 → ✓；<2 → ✗ |
| 6 | 站外 | 四维判定，命中 ≥2 项即存在站外推广（见 §7.3） | 卖家精灵站外推广数据为主 + WebSearch 兜底（折扣站/达人/付费广告/覆盖渠道） | 4 项命中 ≥2 → 有；<2 → 无 |
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

**⚠ `--picks` 要求每条含小写 `asin` 键**。源表 dump 出来通常是大写 `ASIN`，直接喂会报 `KeyError: 'asin'`（脚本内按 `d['asin']` 取）。先归一化：
```python
std = [{'asin': d['ASIN'], 'brand': d.get('品牌',''), 'price': d.get('price_n'),
        'sales': int(float(d.get('sales_n') or 0))} for d in picks]
json.dump(std, open('picks_std.json','w',encoding='utf-8'), ensure_ascii=False)
```
`gen_html.py` 的 `--picks` 同样要求 `asin/brand/price/sales` 小写键，可复用这份 `picks_std.json`。

走这个 tab 前**必须 `Page.bringToFront`**（见 F5），否则扩展不注入；页面加载慢时 `Page.reload` 重试一次。
实测 360 浏览器失败率约 50%，跑一轮后重跑一次即可补齐（`variants` 为空会自动重试；`--force` 强制重启浏览器）。

### 7.2.3 品牌效应五维判定（#5）

按以下 **5 个维度** 逐项实证核查，**命中 ≥2 项即判定存在品牌效应（✓），否则 ✗**。每个维度必须有证据来源，禁止凭印象。

| # | 维度 | 判定标准 | 数据源 |
|---|---|---|---|
| 5-1 | 亚马逊品牌搜索词 | 搜索词中存在品牌搜索词：品牌名**单独作为一个搜索词**（如「Stanley」），或品牌名**作为关键词串的一部分**（如「Stanley 40oz 保温杯」），二者任一即命中 | 关键词反查页 `keyword-reverse?q=<ASIN>` 的自然搜索词 / 全部流量词，逐条筛查是否含品牌名（§5） |
| 5-2 | A+ 页面品牌故事 | Amazon 详情页 A+ Content 中存在品牌故事模块（Brand Story / 品牌介绍） | CDP 打开 `amazon.com/dp/<ASIN>` 抓 A+ 区块 |
| 5-3 | 站外自然推荐 | 站外有媒体 / 博客 / 红人的自发自然推荐（非付费投放），有实证来源 | WebSearch 品牌名 + 测评 / 报道 |
| 5-4 | 同规格价格溢价 | 同规格（同材质 / 同容量 / 同功能）产品价格显著高于主流竞品，溢价率可量化 | 本链 price 对比同类竞品价格（源数据 / picks.json） |
| 5-5 | 品牌独立站 | 存在品牌独立站且售同类产品 | WebSearch 品牌名 official website（独立站核查，§5 独立维度） |

判定规则：
- 5 项中**命中 ≥2 →** `品牌:✓(命中N项:5-1/5-2/...)`；
- **命中 <2 →** `品牌:✗(仅命中N项...)`。

**⚠ 5-1 解析关键词反查页的锚点选择**：parse 时**不要拿页面标题做锚点**——标题里本身就含品牌名，会导致"每页都命中"的假阳性。应以 **「高频词」区域**为起点向下切出流量词列表，再逐条判断是否含品牌名。

注意：**#5 品牌五维 与 #6 站外 是两个独立判定**。5-3 站外自然推荐、5-5 品牌独立站虽然也走 WebSearch，但只作为「品牌效应」的证据之一；#6 站外的四维判定（§7.3）口径独立，互不影响。

### 7.3 站外推广四维判定（#6）

按以下 **4 个维度** 逐项实证核查，**命中 ≥2 项即判定存在站外推广（有），否则 无**。数据**以卖家精灵站外推广页为主，缺失维度用 WebSearch 兜底**。每个维度必须有证据来源，禁止凭印象、禁止编造。

| # | 维度 | 判定口径（近90天） | 数据源 |
|---|---|---|---|
| 6-1 | 折扣站推广记录 | 出现该 ASIN 或明确对应产品的独立促销活动数（同一活动转载去重） | 卖家精灵站外推广 / WebSearch Deal 站（Slickdeals/DealNews/Woot/Groupon） |
| 6-2 | 达人推广内容 | 带产品购买链接 / 专属折扣码 / 联盟链接 / 商业合作标识的独立创作者数 | 卖家精灵站外推广 / WebSearch 红人测评 |
| 6-3 | 站外付费广告 | 可核实且对应该产品的独立广告素材数（同素材多版本去重） | 卖家精灵站外推广 / WebSearch 品牌广告素材 |
| 6-4 | 推广覆盖渠道 | 已发现有效推广证据的平台数（折扣站、YouTube、TikTok、Instagram、Facebook 等） | 卖家精灵站外推广 / WebSearch 逐平台 |

判定规则：
- 4 项中**命中 ≥2 →** `站外:有(命中N项:6-1/6-2/...)`；
- **命中 <2 →** `站外:无(仅命中N项...)`。

**证据原则**：只报告实际搜到的证据，给真实 URL；搜不到写"未发现"；同名不同行业标注"同名但不相关"判为未发现。卖家精灵站外推广页需登录态抓取；缺失维度用 WebSearch 补，WebSearch 也搜不到则该维度按未命中处理。品牌多时派子代理并行。

### 7.4 输出格式

**只输出命中的维度**：八点中判定为「存在 / 命中 / ✓ / 有 / 疑似」的**才写入表格**；判定为「无 / ✗ / 未见 / 不命中 / 待补」的**不展示**。命中项按 `序号.维度:判定(数据依据)` 用 `\n` 连接（kdocs 单元格换行就是写 `\n`）；若八点全部未命中，该格留空。

**判定归属约定**：判为「疑似」（如 #4 刷单 rate30>3%）是有实证的正面信号，**算存在、写入**；「未见 / 无 / ✗ / 待补」不写。

示例（该品命中 2/3/5/6/8 五项；#1、#4、#7 判定为 ✗/未见，已过滤不展示）：
```
2.合并评论:✓(存在非美地区评论3399条:DE1594/JP633/FR515/UK250/ES203/IT181/CA23)
3.Vine:✓(明显存在37条Vine评论)
5.品牌:✓(命中3项:品牌搜索词+A+品牌故事+品牌独立站,AmazonBasics自有品牌)
6.站外:有(命中3项:6-1折扣站+6-2达人+6-4覆盖渠道,近90天证据)
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

**⚠ `get-typed-value` 的 range 是 A1 字符串（`"C2:M21"`），不是 `{row_from,...}` 对象** —— 传对象会报 `range 为必填`。注意这与 `set-range-width-height`（对象）**格式相反**，别混用。
```json
{"file_id":"<ID>","worksheet_id":2,"range":"C2:M21"}
```
返回的 `typedValues` 是**行主序一维数组**，按 C→M 每行 11 个顺排，需自行切分：
```python
tv = json.loads(out[:out.rfind('}')+1])['data']['typedValues']
grid = [tv[i*11:(i+1)*11] for i in range(20)]   # 20 行 × 11 列
```
比对口径：`abs(got - expect) < 1e-6` **且** `type == "double"`。旅行药盒项目实测应达 **220/220（20 行 × 11 列）全一致**才判通过。

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
- **F18 `get-typed-value` 报「range 为必填」**：range 必须传 **A1 字符串**（`"C2:M21"`），不是 `{row_from,...}` 对象。注意这与 `set-range-width-height`（对象）、`auto-fit`（A1 字符串 `"2:21"`）各不相同，**三处格式勿混用**（见 §8）。
- **F19 picture op 返回 `code:0` 但读回"像没落格"**：用 `get-range-data` 的 `cellText` 去匹配 `=DISPIMG("ID_xxx",1)` **会假阴性**（拼接/转义差异）。**以 `isCellPic == true` 为准**；仍存疑就单行重写该 picture op 再复读一次。
- **F20 `set-range-width-height` 只想调行高**：`width` / `height` **至少传一个**即可；**只传 `height` 不会改列宽**（安全）。反之若同时传 `width`，会连带改列宽——主图列 width=2160 是刻意设的，别在改行高时误传。
- **F21 源表 dump 漏列 → 整列全 None**：`dump_full.py` 的 `NEED` 列表必须与目标表 16 列一一对齐（尤其易漏 **产品卖点（五点描述）**）。dump 完先断言每列非空率，别等写库才发现整列空。
- **F22 拿不到目标文档的分享链接**：若目标表在**团队/他人空间**，OAuth 账号的 `drive list-my-files` 树里检索不到它（遍历返回空 items），只有 `file_id` 能直连读写。**这不影响填表**（sheet 系列 API 只认 `file_id`），别为此卡住；交付时不硬编 URL，改为告知用户文件名 + `file_id`。
- **F23 评论分析页被拦到落地页**：游客态或账号无套餐时会被重定向到落地页。**优先走新版** `v3/ai-review-analysis`（可直接输 ASIN 生成，见 §6.1 通道 1）；旧版 `v3/review-analysis` 的入口是 dp 页扩展面板的「AI 评论分析」按钮（**注意不是 `v3/rs`，那个路径是错的**）。**若确实拿不到**：差评点退化为「comment API 星级分布 + 低星时间趋势」+ WebSearch 第三方测评，**并在结论里注明数据源等级**，不得因此编数字。
- **F24 ★★ `get_browser_ws_url` 在非交互 stdin 下永久阻塞（最难查的坑）★★**：`cdp360.get_browser_ws_url()` 会先尝试 `sys.stdin.read()`（为适配 sandbox 下"curl 管道喂 JSON"的姿势）。若在 Bash 工具里写成 `python script.py 2>&1 | tee log`，**stdin 是管道且无数据也无 EOF** → `read()` **永久挂起**：脚本无任何输出、最终被 SIGTERM 杀掉，看起来像"卡在启动浏览器"，极易误判。
  **两种解法**：
  ① 命令加 `< /dev/null`（stdin 立即 EOF，转走 urllib 分支）；
  ② 脚本内 monkeypatch 成 **raw socket 版**（sandbox 下最稳，不依赖 stdin/urllib）：
  ```python
  cdp360.get_browser_ws_url = _ws_url      # 用 socket 发 GET /json/version 取 webSocketDebuggerUrl
  ```
  ⚠ raw socket 版**不能等 EOF**——CDP 常 keep-alive，`recv()` 会超时；必须解析 `Content-Length` 后定量读取 body。
- **F25 sandbox 下能启动 GUI 浏览器，但有前提**：Python `subprocess.Popen(360se.exe, '--remote-debugging-port=9222')` 在 sandbox 里**可用**（实测 1 秒端口就绪）。但**启动与抓取必须在同一条 Bash 命令/同一进程内**（命令一结束，浏览器进程即被回收）——这也是 `ensure_browser()` 存在的理由。
- **F26 ★★ `POST /v3/api/review-voc/list` 忽略一切过滤参数 —— 会把同一份报告写到多个 ASIN 上 ★★**（2026-10-08 实测）：该端点**不看** `asin` / `asinList` / `asins` / `market` 任何一个，**永远返回账号下的全部报告**（`data.items`），默认 `size:20`。实测用 9 个**不同** ASIN 去查，全部返回同一份 `id=31781`（B0BQJ2XZWF 的报告）。若按 `items[0]` 取"该 ASIN 的报告"，**9 行会写出完全相同的 col14 文案**，而且 `status=COMPLETED` 会让脚本以为"已有报告、无需创建"，**静默跳过配额消耗，全程不报错**——是最危险的一类错误。
  - **正确做法**：拉全量再**客户端按 asin 精确匹配**
    ```python
    def find_report(s, asin):
        d = api(s, '/v3/api/review-voc/list', {'page': 1, 'size': 200}, n=2000000)
        for it in ((d.get('data') or {}).get('items') or []):
            if (it.get('asin') or '').strip().upper() == asin.strip().upper():
                return it
        return None
    ```
  - `ss_voc.py` 已按此修复（新增 `list_reports()` + 精确匹配版 `find_report()`）。
  - **通用教训**：凡"查询类"端点拿到结果，**必须核对返回对象里的业务键（asin/sku/id）是否与入参一致**，不能假设服务端做了过滤。这与 §10 第 3 条同源——写入前的每一环都要能自证。
- **F27 ★ 用 UI 点击创建 VOC 报告成功率只有 ~50%，必须改直调 API ★**（2026-10-08 实测）：原 `create_report()` 走页面 UI（选站点 → 填 ASIN → 点「生成报告」），连续批量创建时 **9 次尝试只建成 5 个**。失败形态极隐蔽：`el-select` 下拉与输入框回填在连续操作中丢事件，按钮点了但请求根本没发出去 → **配额不扣、报告不建、脚本不报错**（因为 `find_report` 拿不到 id 只打印空字符串）。逐次失败是无规律的（成功/失败交替），不是"第一次之后全失败"。
  - **真实接口**（用 `window.fetch` / `XMLHttpRequest.prototype` 钩子抓取所得）：
    ```
    POST /v3/api/review-voc/new-task    body: {"asin":"B0XXXXXXXX","market":"US"}
    → {"code":"OK","message":"成功","data":31857,"success":true}   # data 即 report_id
    ```
  - **同时修正的两个参数细节**：
    - `list` 的真实 body 是 `{"keyword":"","market":"","pageSize":200,"pageNum":1,"labelIdList":[]}`
    - `batch-get-report` 站点实际传**字符串** id：`{"ids":["31855","31854"]}`
  - **新建报告进列表有数秒延迟**：`new-task` 返回 id 后立刻查 `list` 可能查不到，需重试 3~6 次（每次间隔 3s）。
  - **抓接口的通用姿势**（任何"页面点击才有、又找不到文档"的操作都适用）：注入钩子 → 手动点一次 → 读 `window.__cap`
    ```javascript
    window.__cap=[]; const of=window.fetch;
    window.fetch=function(){var a=arguments[0],b=arguments[1]||{};
      window.__cap.push({u:(typeof a==='string')?a:(a&&a.url),m:b.method,b:String(b.body||'')});
      return of.apply(this,arguments);};
    var oo=XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open=function(m,u){this.__m=m;this.__u=u;return oo.apply(this,arguments);};
    var os=XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.send=function(b){window.__cap.push({u:this.__u,m:this.__m,b:String(b||'')});
      return os.apply(this,arguments);};
    ```
    ⚠ 探测本身也消耗一次配额——所以要挑**本来就缺报告**的 ASIN 来探，探测即产出，不浪费。

## 10. 禁止事项

1. 禁止凭印象写判定——每个 ✓/✗ 必须跟具体数字或实证来源。
2. 禁止编造 URL——站外推广判定搜不到就写"未发现"。
3. 禁止跳过校验——写入成功不等于落对行/数值落格。
4. 禁止用 Amazon 评论页做地区/Vine/近30天评论判定（已降级）。
5. 禁止 auto-fit 长文本表（会拉变形主图列）。
6. 禁止数值列不带等号写入（会空但报成功）。
7. 禁止用 `get-range-data` 校验数值列。
8. 禁止**只凭 listing** 写机会点——必须叠加评论分析，产出「**差评点（带实证数字）+ 可借鉴点**」（见 §6.1）。listing 是卖家自夸，评论才是买家实感。
9. 禁止**假设查询接口按入参过滤**——拿到列表结果必须核对返回对象里的业务键（`asin`/`sku`/`id`）与入参一致，再往下用（见 F26 的血案）。
10. 禁止用行业级/同类头部**聚合数**冒充本品结论——差评点条数必须来自该 ASIN 自己的评论样本（`voc_insight.json`），保证可回溯。

## 11. 交付物

- kdocs 表格（全部列填完 + 校验通过）。
- 可视化汇总 HTML（可选，`scripts/gen_html.py`）。
- 中间数据 JSON：`picks.json` / `reviews.json` / `variants.json` / **`voc_insight.json`**（评论洞察：各 ASIN 的**差评点 / 认可点 / 风险 / 根因**，由 `scripts/ss_voc.py` 产出，供 col14 使用）/ `p_col*.json`。
