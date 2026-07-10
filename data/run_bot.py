# -*- coding: utf-8 -*-
"""
VOC 分析机器人（定时自动化入口）
================================
扫描 data/inbox/*.csv -> 逐个生成多框架 HTML 报告到 data/reports/ -> 处理完移入 data/done/。

设计：机器人只负责「产出报告」，不自动推送。推送由调用方（WorkBuddy 定时自动化）
在跑完本脚本后执行 `git add data/reports data/done && git commit && git push`。
这样即使网络异常，报告也已落盘，下次可补推。

用法:
  python3 run_bot.py
"""
import sys, os, shutil, glob, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from frameworks import aggregate, build_multiframe_report

BASE = os.path.dirname(os.path.abspath(__file__))
INBOX = os.path.join(BASE, "inbox")
DONE = os.path.join(BASE, "done")
REPORTS = os.path.join(BASE, "reports")

def infer_product(stem):
    if "飞机杯" in stem:
        cat = "飞机杯（挂载/吸附类）"
    elif "倒模" in stem:
        cat = "倒模"
    elif "振动" in stem or stem.lower().endswith("vibe"):
        cat = "振动器"
    else:
        cat = stem
    return {"purpose": "产品开发", "category": cat, "desc": f"基于 {stem} 真实评价数据自动生成。"}

def main():
    os.makedirs(INBOX, exist_ok=True)
    os.makedirs(DONE, exist_ok=True)
    os.makedirs(REPORTS, exist_ok=True)
    files = sorted(glob.glob(os.path.join(INBOX, "*.csv")))
    if not files:
        print(f"[BOT] inbox 为空（{INBOX}），无需处理。把新 CSV 丢进 inbox/ 即可触发。")
        return
    print(f"[BOT] 发现 {len(files)} 个待处理 CSV @ {datetime.datetime.now():%Y-%m-%d %H:%M}")
    for csv_path in files:
        stem = os.path.splitext(os.path.basename(csv_path))[0]
        try:
            product = infer_product(stem)
            counts, rows = aggregate(csv_path)
            html_out = build_multiframe_report(product, counts, rows)
            out_path = os.path.join(REPORTS, "multiframe_" + stem + ".html")
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(html_out)
            # 移动已处理文件
            shutil.move(csv_path, os.path.join(DONE, os.path.basename(csv_path)))
            print(f"[OK] {stem} | {rows} 条 -> {out_path} | 已移入 done/")
        except Exception as e:
            print(f"[ERR] {stem} 处理失败: {e}")
    print("[BOT] 完成。报告在 data/reports/，原始 CSV 在 data/done/。")

if __name__ == "__main__":
    main()
