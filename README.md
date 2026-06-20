# 大A情绪分参考模型

爬取东方财富上证指数股吧帖子，做词频情绪分析，生成 `data.json` 与 `index.html` 看板。

## 本地运行

```bash
pip install -r requirements.txt
python main.py              # 分析今天
python main.py --yesterday  # 分析昨天（定时任务用）
python main.py --date 2026-06-15 --no-browser  # 补跑指定日
```

## GitHub 定时任务

- 工作流：`.github/workflows/daily.yml`
- **每天北京时间 08:00** 自动跑 `--yesterday`，分析前一交易日帖子
- 结果自动 commit `data.json` 与 `index.html`

### 首次部署

1. 在 GitHub 新建仓库（如 `a-share-sentiment`）
2. 本地推送：

```bash
cd 词频情绪
git init
git add .
git commit -m "Initial commit: sentiment crawler + daily workflow"
git branch -M main
git remote add origin https://github.com/<你的用户名>/<仓库名>.git
git push -u origin main
```

3. 仓库 **Settings → Actions → General** 中允许 workflow 写入仓库
4. （可选）**Settings → Pages** 选 `main` 分支 `/root`，用 `index.html` 在线看板

### 手动触发

Actions → Daily Sentiment Analysis → Run workflow
