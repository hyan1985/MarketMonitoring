# MarketMonitoring · 大A情绪分参考

[![Daily Analysis](https://github.com/hyan1985/MarketMonitoring/actions/workflows/daily.yml/badge.svg)](https://github.com/hyan1985/MarketMonitoring/actions/workflows/daily.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](requirements.txt)

> 多源爬取 A 股论坛帖子，基于词频词典做情绪量化，并结合 TuShare 市场数据估算大盘综合风险值，自动生成可视化看板。

**在线看板：** https://hyan1985.github.io/MarketMonitoring/

---

## 功能概览

| 模块 | 说明 |
|------|------|
| **多源爬虫** | 东方财富股吧、雪球、同花顺（上证指数相关讨论） |
| **情绪分析** | 基于多头/空头/否定词词典的分词加权打分，范围 `[-1, 1]` |
| **风险预估** | TuShare 五维模型：资金集中度、融资余额、行业集中度、市场广度、论坛情绪 |
| **可视化看板** | 情绪仪表盘、日线趋势、词频图、词云、帖子明细、实时模拟器 |
| **定时任务** | GitHub Actions 每个工作日自动跑昨天数据并更新看板 |

---

## 快速开始

### 本地运行

```bash
git clone https://github.com/hyan1985/MarketMonitoring.git
cd MarketMonitoring
pip install -r requirements.txt
cp config.example.json config.json   # 按需填写 TuShare Token 等
python main.py                       # 默认分析昨天（北京时间）
python main.py --yesterday           # 显式指定前一自然日（定时任务用）
python main.py --today               # 分析当天（北京时间）
python main.py --date YYYY-MM-DD --no-browser  # 补跑指定日期
```

运行完成后会生成/更新 `data.json` 与 `index.html`，并在浏览器中打开看板（可用 `--no-browser` 跳过）。

### 环境变量

| 变量 | 说明 |
|------|------|
| `TUSHARE_TOKEN` | TuShare Pro API Token，用于大盘风险值计算 |

本地可在 `config.json` 中配置，GitHub Actions 请设为仓库 Secret。

---

## GitHub 部署

### 1. Fork / Clone 后推送

```bash
git remote add origin https://github.com/<用户名>/MarketMonitoring.git
git push -u origin main
```

### 2. 配置 Secrets

仓库 **Settings → Secrets and variables → Actions** 中添加：

- `TUSHARE_TOKEN` — TuShare Pro API Key（5000 积分以上推荐）

### 3. 启用 Actions 写权限

**Settings → Actions → General → Workflow permissions** → 选择 **Read and write permissions**。

### 4. 启用 GitHub Pages

**Settings → Pages → Source** → Branch 选 `main`，目录选 `/ (root)`。

部署完成后访问：`https://<用户名>.github.io/MarketMonitoring/`

### 5. 手动触发

**Actions → Daily Sentiment Analysis → Run workflow**

---

## 定时任务

- 工作流：`.github/workflows/daily.yml`
- **每天北京时间 00:30**（0 点后）自动执行
- 抓取**前一自然日**全天论坛帖子；TuShare 风险数据取该日或之前最近已入库的交易日
- 全项目时间与面板展示统一为**北京时间 (Asia/Shanghai)**
- 自动 commit `data.json` 与 `index.html`

---

## 项目结构

```
├── main.py                 # 主入口：爬取 → 分析 → 风险 → 看板
├── sentiment_analyzer.py   # 词频情绪分析引擎
├── risk_scorer.py          # TuShare 多维风险评分
├── dashboard_generator.py  # HTML 看板生成
├── guba_crawler.py         # 东方财富股吧爬虫
├── xueqiu_crawler.py       # 雪球爬虫
├── ths_crawler.py          # 同花顺爬虫
├── config.example.json     # 配置模板（不含敏感信息）
├── data.json               # 分析结果（由 workflow 更新）
├── index.html              # 在线看板（由 workflow 更新）
└── .github/workflows/
    └── daily.yml           # 每日定时任务
```

---

## 情绪分解读

| 区间 | 含义 | 参考操作 |
|------|------|----------|
| `< -0.3` | 极度恐慌 / 黄金买点 | 逆向建仓 +10%~+20% |
| `-0.3 ~ 0.5` | 情绪中性 / 卧倒装死 | 维持底仓，持股不动 |
| `> +0.5` | 极度亢奋 / 防御警报 | 防守减仓 -10%~-20% |

## 风险值解读

综合风险分 `0–100`：五维基础分 + 变动信号（≤15）+ 累积风险（≤18）+ 硬触发底线。**≥45 预警、≥60 紧急减仓、≥75 极端风险**。

---

## 免责声明

本工具仅供情绪因子研究与数据展示，**不构成任何投资建议**。股市有风险，投资需谨慎。

---

## License

[MIT](LICENSE)
