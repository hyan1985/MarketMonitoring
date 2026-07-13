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
| **风险预估** | TuShare 双轨模型：结构拥挤 + 破位风险，含领先信号与硬触发 |
| **可视化看板** | 情绪仪表盘、日线趋势、多空词频、横版风险面板、帖子明细、实时模拟器 |
| **定时任务** | GitHub Actions 每个工作日自动跑昨天数据并更新看板 |

---

## 看板布局

| 区域 | 内容 |
|------|------|
| 左上 | 大盘情绪指数（仪表盘 + 帖子分类占比） |
| 右上 | 情绪日线趋势 + 模型说明（三档横排） |
| 中部 | 活跃多头/空头词频（左右并排） |
| 横版风险卡 | 总分/等级 · 双轨分+炸板率 · 集中度+五维进度条 |
| 风险卡底部 | 变动信号 · 硬触发 · **成交集中度近一年历史分位**（PE 式分位条） |
| 底部 | 情绪模拟器 + 帖子明细表 |

---

## 风险模型

综合风险分 `0–100` = **结构拥挤**（0–50）+ **破位风险**（0–50）。

### 双轨评分

| 轨道 | 维度与信号 | 主升期表现 |
|------|------------|------------|
| **结构拥挤** | 资金集中度、融资余额、行业集中度、论坛情绪亢奋 | 科技拉指数时常偏高 → **观察，不宜追高** |
| **破位风险** | 恐慌扩散、宽度骤降、隐性破位、炸板跌停潮 | 真正减仓信号，**≥22 紧急、≥35 极端** |

**主升趋势熔断：** 均线多头且收盘守 MA10、未大跌；破位分 <20 时总分上限 55。死叉/跌破 MA10/大跌日不再标主升。

### 五维基础分

| 维度 | 数据来源 | 说明 |
|------|----------|------|
| 资金集中度 | 前 5% 个股成交额 / 全市场 | 含近一年**历史极值**与**历史分位** |
| 融资余额占比 | margin + daily_basic | 杠杆参与度 |
| 行业集中度 | 通信+电子成交占比 | 科技主线拥挤度 |
| 恐慌扩散 | 跌幅≥5% 个股占比 | 市场广度恶化 |
| 论坛情绪 | 当日帖子加权情绪分 | 与词频分析联动 |

### 领先与触发信号

| 类型 | 信号 | 作用 |
|------|------|------|
| 量价背离 | 指数高位 + 量能/参与面走弱 | 顶部派发领先特征，持续 2 日确认 |
| 顶部派发形态库 | 缩量背离、巨量滞涨、衰竭缺口、融资流出等 6 类 | 低误报形态可弹窗升级风险等级 |
| 隐性破位 | 指数收红/收平，底下宽度崩塌 | 大幅提升破位分（如 6/26 大绿棒前一日） |
| 炸板率/跌停扩散 | limit_list_d 涨停/炸板/跌停统计 | 赚钱效应转弱时加分 |
| 余震记忆 | 近期刚破位且仍在回撤 | 反弹日维持中性/预警，防死猫跳 |
| 硬触发 | 多维度共振 | 可设总分底线（预警/紧急/极端） |

### 风险等级

| 等级 | 典型条件 | 建议 |
|------|----------|------|
| 🟢 安全 | 双轨均低 | 正常持仓 |
| 🟡 中性 | 结构偏高或余震观察 | 谨慎，不追高 |
| 🟠 预警 | 破位分 ≥15 或硬触发 | 控制仓位 |
| 🔴 紧急 | 破位分 ≥22 | 明显减仓 |
| ⛔ 极端 | 破位分 ≥35 或极端组合 | 大幅减仓/对冲 |

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

### 回测脚本

```bash
python scripts/backtest_risk_peaks.py          # 历史顶部预警提前量
python scripts/backtest_vp_divergence.py       # 量价背离领先信号
python scripts/backtest_distribution_patterns.py  # 顶部派发形态库
python scripts/backtest_big_drops.py           # 历史大跌日模型表现
```

---

## GitHub 部署

### 1. Fork / Clone 后推送

```bash
git remote add origin https://github.com/<用户名>/MarketMonitoring.git
git push -u origin main
```

### 2. 配置 Secrets

仓库 **Settings → Secrets and variables → Actions** 中添加：

- `TUSHARE_TOKEN` — TuShare Pro API Key（建议 5000 积分以上，需 `daily`、`margin`、`limit_list_d` 等接口）

### 3. 启用 Actions 写权限

**Settings → Actions → General → Workflow permissions** → 选择 **Read and write permissions**。

### 4. 启用 GitHub Pages

**Settings → Pages → Source** → Branch 选 `main`，目录选 `/ (root)`。

部署完成后访问：`https://<用户名>.github.io/MarketMonitoring/`

### 5. 手动触发

**Actions → Daily Sentiment Analysis → Run workflow**

可选 `target_day`：`yesterday`（默认，与定时任务一致）或 `today`。

---

## 定时任务

- 工作流：`.github/workflows/daily.yml`
- **每天北京时间 00:30**（0 点后）自动执行
- 抓取**前一自然日**全天论坛帖子；TuShare 风险数据取该日或之前最近已入库的交易日
- 全项目时间与面板展示统一为**北京时间 (Asia/Shanghai)**
- 自动 commit `data.json`、`posts.json` 与 `index.html`

---

## 项目结构

```
├── main.py                 # 主入口：爬取 → 分析 → 风险 → 看板
├── sentiment_analyzer.py   # 词频情绪分析引擎
├── risk_scorer.py          # TuShare 双轨风险评分 + 领先信号
├── dashboard_generator.py  # HTML 看板生成
├── guba_crawler.py         # 东方财富股吧爬虫
├── xueqiu_crawler.py       # 雪球爬虫
├── ths_crawler.py          # 同花顺爬虫
├── config.example.json     # 配置模板（不含敏感信息）
├── data.json               # 分析摘要 + 风险分（轻量，~15KB）
├── posts.json              # 帖子明细（紧凑 JSON，看板异步加载）
├── index.html              # 在线看板模板（~60KB，不再内嵌帖子）
├── data_store.py           # data.json / posts.json 读写
├── scripts/                # 历史回测脚本
│   ├── backtest_risk_peaks.py
│   ├── backtest_vp_divergence.py
│   ├── backtest_distribution_patterns.py
│   └── backtest_big_drops.py
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

---

## 免责声明

本工具仅供情绪因子研究与数据展示，**不构成任何投资建议**。股市有风险，投资需谨慎。

---

## License

[MIT](LICENSE)
