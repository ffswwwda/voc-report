# VOC 分析机器人（C 混合路线）

把真实 VOC CSV 丢进 `inbox/`，机器人自动聚合标签并跑 7 个框架确定性引擎，
产出自包含多框架 HTML 报告到 `reports/`，处理完的原始 CSV 移入 `done/`。

## 目录
- `frameworks.py` —— 共享引擎（聚合 + 7 框架：jtbd / needs-analysis / compass / extreme / triz / researcher / plutchik）+ 报告 CSS
- `analyze_report.py` —— 单文件入口：一个 CSV → 一份多框架报告
- `run_bot.py` —— 扫描入口：遍历 `inbox/*.csv` 批量出报告
- `inbox/` —— 把新 CSV 放这里即触发（空目录会被忽略）
- `reports/` —— 生成的多框架报告 `multiframe_<csv名>.html`
- `done/` —— 处理完的原始 CSV

## 本地手动运行
```bash
# 批量（推荐）：扫描 inbox 下所有 CSV
python3 data/run_bot.py

# 单文件：指定 CSV 与输出
python3 data/analyze_report.py <csv路径> [输出html] [--purpose 文本] [--category 文本] [--desc 文本]
```

## 定时自动化（WorkBuddy）
已配置每日 08:00 自动运行 `run_bot.py`；若有新报告生成，自动
`git add data/reports data/done && git commit && git push origin main`。
无新 CSV 时仅提示 inbox 为空。

## 框架与前端对齐
7 个框架与 `experience.html` 的 `FRAMEWORKS` 完全对应，结论均由真实标签频次
聚合得出，可溯源到 `reports` 报告末尾的「数据附录」。
