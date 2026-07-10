# -*- coding: utf-8 -*-
"""
VOC 多框架报告生成器（C 混合路线 · 机器人单文件入口）
读一个真实 VOC CSV -> 聚合 -> 跑 7 框架 -> 写出自包含多框架 HTML 报告。

用法:
  python3 analyze_report.py <csv_path> [out_html] [--purpose 文本] [--category 文本] [--desc 文本]
若不提供 out_html，默认写到同目录 reports/multiframe_<csv名>.html
"""
import sys, os, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from frameworks import aggregate, build_multiframe_report

def infer_product(csv_path, purpose=None, category=None, desc=None):
    stem = os.path.splitext(os.path.basename(csv_path))[0]
    # 从文件名猜测类目
    cat = category
    if not cat:
        if "飞机杯" in stem:
            cat = "飞机杯（挂载/吸附类）"
        elif "倒模" in stem:
            cat = "倒模"
        elif "振动" in stem or "vibe" in stem.lower():
            cat = "振动器"
        else:
            cat = stem
    return {
        "purpose": purpose or "产品开发",
        "category": cat,
        "desc": desc or f"基于 {stem} 真实评价数据生成的多框架分析报告。",
    }

def main():
    if len(sys.argv) < 2:
        print("用法: python3 analyze_report.py <csv_path> [out_html] [--purpose ..] [--category ..] [--desc ..]")
        sys.exit(1)
    csv_path = sys.argv[1]
    out_path = None
    purpose = category = desc = None
    args = sys.argv[2:]
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--purpose":
            purpose = args[i + 1]; i += 2; continue
        elif a == "--category":
            category = args[i + 1]; i += 2; continue
        elif a == "--desc":
            desc = args[i + 1]; i += 2; continue
        elif not out_path:
            out_path = a; i += 1; continue
        else:
            i += 1
    if not out_path:
        out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "reports", "multiframe_" + os.path.splitext(os.path.basename(csv_path))[0] + ".html")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    product = infer_product(csv_path, purpose, category, desc)
    counts, rows = aggregate(csv_path)
    html_out = build_multiframe_report(product, counts, rows)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_out)
    print(f"[OK] 样本 {rows} 条 | 场景 {len(counts['使用场景'])} | 阻碍 {len(counts['使用阻碍'])} | 需求 {len(counts['需求动机'])} | 情绪 {len(counts['情绪'])} | 画像 {len(counts['用户画像'])}")
    print(f"[OUT] {out_path}")

if __name__ == "__main__":
    main()
