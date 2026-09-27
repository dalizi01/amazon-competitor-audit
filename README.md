# amazon-competitor-audit · 亚马逊竞品分析 Skill

把亚马逊竞品分析全套流程封装成一个可复用的 Agent Skill，最终把 N 个竞品 × 16 列的「运营难度分析」结果填入金山文档（kdocs）表格。

## 能力

- **ASIN 筛选**：从卖家精灵关键词导出 xlsx 筛选竞品（父体去重 / 标题过滤 / 品牌去重 / 月销降序取前 N），含 `editAs` 兼容修复。
- **16 列全填**：竞品链接(超链接) / 竞品主图(单元格内嵌 DISPIMG) / 售价 / 上架天数 / 月销量 / 变体数 / 评分 / 评论数量 / 广告组数 / SP广告词 / 自然搜索词 / 广告强度 / 小类排名 / 产品卖点 / 机会点 / 运营手段(八点)。
- **广告数据**：广告组数（父体 Listing 投放小组数）、SP广告词（=SP+品牌+视频广告词之和）、自然搜索词，**需卖家精灵登录态**（游客态前几个可抓，第 4 个起被风控拦截）。
- **运营手段八点判定**（实证，不编造）：广告 / 合并评论 / Vine / 刷单 / 品牌 / 站外 / 老带新 / 上架时间早。
- **强制校验**：逐行比对 + `get_typed_value` 校验数值列，防整列错位 / 数值落空。

## 目录结构

```
amazon-competitor-audit/
├── SKILL.md            # 完整作业流程 + 全部踩坑 + 可移植配置
└── scripts/
    ├── setup_env.py    # 环境自检与准备（缺什么给指引，--install 自动装 openpyxl）
    ├── cdp360.py       # 360/Chrome 内核 CDP 客户端（无第三方依赖）
    ├── xlsx_fix.py     # 修复卖家精灵 xlsx 的 editAs 兼容
    ├── kdocs_sheet.py  # kdocs 表格写入/校验（kdocs-cli 封装，可选）
    ├── ss_review.py    # 卖家精灵评论采集（vine/多站点/近30天）
    └── gen_html.py     # 八点判定可视化汇总
```

## 安装与依赖

把整个 `amazon-competitor-audit` 文件夹放进 Agent 的 `workspace/.user_skills/` 目录即可。

依赖（新机器 / 新 Agent 先跑环境自检）：
```bash
python scripts/setup_env.py            # 只读自检
python scripts/setup_env.py --install  # 自检 + 自动安装 openpyxl
```

- **Python 3.9+**（需 openpyxl，缺了 `python -m pip install openpyxl`）
- **Chrome 内核浏览器**（360 安全浏览器 / Chrome / Edge），必须带调试端口启动：
  `"C:\<浏览器>\360se.exe" --remote-debugging-port=9222`
- **kdocs 访问**：优先用 Agent 环境的 kdocs MCP 工具；`kdocs_sheet.py`（CLI 封装）可选，需要 `kdocs-cli`。
- **登录态**：浏览器里登录卖家精灵 `sellersprite.com/v3/`、Amazon、kdocs。
  - 广告数据也**需卖家精灵登录态**（游客态第 4 个 ASIN 起被风控拦截）；**评论八点（合并评论/Vine/刷单）需卖家精灵【网页端与扩展端账号一致】**。

## 使用方法

给 Agent 两类输入即可启动：
1. **任务输入**：卖家精灵关键词导出 xlsx（`Search(<关键词>)-N-US-<日期>.xlsx`），或一个关键词（Agent 按流程去卖家精灵筛竞品）。
2. **目标表格**：结果要填进哪个 kdocs「运营难度分析」表的链接 / 文件 ID + 工作表 ID。

## 关键口径（已与业务方确认）

- 数值列写入 `formula` **必须带等号**（`=8.49`），否则不落格。
- `row_from` 是 **0-based**（表头 0，第 1 条数据 1）。
- 竞品链接列用 `=HYPERLINK("https://www.amazon.com/dp/<ASIN>","<ASIN>")`。
- col9 广告组数 = 整个父体 Listing 的投放小组数（动态指标）。
- col9 SP广告词 = SP + 品牌 + 视频广告词之和。
- 竞品主图用 DISPIMG 单元格内嵌（add-row 法，最可靠）；图片服务间歇不可用时退化为直链。

## 校验

写入返回 "20/20 成功" **不代表**内容落在正确行 / 数值落格。必须读回逐行比对：文本列用 `get-range-data` / `get_typed_value`；**数值列必须用 `get_typed_value`**（返回 `type=double`）。
