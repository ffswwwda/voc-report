# -*- coding: utf-8 -*-
"""
VOC JTBD 分析机器人（C 混合路线样本）
--------------------------------
读真实 VOC CSV（已带结构化标签列） -> 聚合标签 -> 跑 JTBD 确定性引擎 -> 生成自包含 HTML 报告。
纯标准库，无外部依赖、无大模型调用，可定时运行（cron / WorkBuddy automation）。

用法:
  python3 analyze_jtbd.py [csv_path] [output_html]
"""
import csv, re, html, sys, json, datetime
from collections import Counter

CSV_PATH = sys.argv[1] if len(sys.argv) > 1 else "/Users/fsw/Downloads/飞机杯商品评价数据源_美亚欧亚汇总-3星及以下.csv"
OUT_PATH = sys.argv[2] if len(sys.argv) > 2 else "/Users/fsw/WorkBuddy/2026-07-02-11-11-45/gh-pages/data/reports/jtbd_飞机杯_3星及以下.html"

PRODUCT = {
    "purpose": "产品开发",
    "category": "飞机杯（挂载/吸附类）",
    "desc": "一款以吸盘吸附方式固定、用于淋浴等场景的飞机杯挂载支架类产品。",
}

# 列映射：内部模块名 -> CSV 列名
COLMAP = {
    "使用场景": "使用场景标签",
    "使用阻碍": "产品问题标签",
    "需求动机": "需求维度标签库",
    "情绪": "情绪标签库",
    "用户画像": "用户属性",
}

SPLIT_RE = re.compile(r"[,，、]\s*")

def split_tags(v):
    if not v:
        return []
    return [t.strip() for t in SPLIT_RE.split(v) if t and t.strip()]

def clean_tag(t, module):
    t = re.sub(r"^\d+[.、]\s*", "", t).strip()          # 去 "28." 编号
    if not t or t.isdigit():                             # 丢弃纯数字/空
        return ""
    if module == "需求动机":
        t = t.split("（")[0].split("(")[0].strip().rstrip("）)")  # 去括号说明，留主需求名
    if any(k in t for k in ("无法判定", "是否提到", "与解放双手相关")):
        return ""
    # 过滤数据污染（AI 拒答话术等）
    if any(k in t for k in ("无法为你提供", "我会尽力", "作为一个AI", "提供相应解答", "支持和解答", "抱歉")):
        return ""
    if len(t) > 30:                                      # 超长疑似污染
        return ""
    if t in ("", "无法判定"):
        return ""
    return t

def emotion_polarity(t):
    if "非常不满" in t or "愤怒" in t:
        return -1
    if "不满" in t or "负向" in t:
        return -1
    if "满意" in t:
        return 1
    if "一般" in t or "中性" in t:
        return 0
    return 0

# ----------------------------- 聚合 -----------------------------
def aggregate(path):
    counts = {m: Counter() for m in COLMAP}
    rows = 0
    with open(path, encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            rows += 1
            for m, col in COLMAP.items():
                for t in split_tags(row.get(col, "")):
                    ct = clean_tag(t, m)
                    if ct:
                        counts[m][ct] += 1
    return counts, rows

# ----------------------------- JTBD 引擎 -----------------------------
SCENE_CLUSTER = {
    "淋浴/浴室环境": ["淋浴", "浴室", "墙面", "瓷砖", "玻璃", "镜面", "潮湿", "隔断", "门"],
    "卧室/居家": ["卧室", "床", "居家", "家用", "房间"],
    "旅行/外出": ["旅行", "出差", "便携", "外出", "户外"],
    "光滑平面": ["光滑", "硬质", "平面", "桌面", "地板"],
    "粗糙/特殊面": ["粗糙", "混凝土", "砖墙", "木质", "多孔"],
}

OBSTACLE_TO_IMPROVE = {
    "吸附不稳定": "增强吸盘吸附力与材质摩擦系数，覆盖更多墙面类型",
    "吸盘吸附力不足": "升级吸盘结构（如真空泵/软胶双层），提升初始吸附与持久性",
    "产品质量差": "提升材质与整体工艺，建立出厂品控标准",
    "产品易断裂": "关键受力部位改用韧性材料，做跌落/弯折测试",
    "材质廉价": "改用亲肤医用级材质，消除塑料廉价感",
    "价格偏高": "优化成本结构或明示价值点，提升性价比感知",
    "与配件不兼容": "标准化接口/螺纹，随附适配环兼容主流配件",
    "配件缺失需另购": "将必要适配器纳入标配，减少二次购买摩擦",
    "螺纹不匹配": "统一螺纹规格并提供转接件",
}

FORCE_PUSH_KEYS = ["脱落", "损坏", "断裂", "不稳定", "不匹配", "差", "廉价", "缺失"]
FORCE_ANX_KEYS = ["缺失", "另购", "骗局", "透明", "信息", "适配"]

def cluster_scenes(scene_counter):
    out = {}
    unclustered = []
    for tag, n in scene_counter.most_common():
        hit = None
        for name, keys in SCENE_CLUSTER.items():
            if any(k in tag for k in keys):
                hit = name
                break
        if hit:
            out.setdefault(hit, []).append((tag, n))
        else:
            unclustered.append((tag, n))
    return out, unclustered

def build_main_job(scene_top, need_top, obs_top):
    scene = scene_top[0] if scene_top else "核心使用场景"
    need = need_top[0] if need_top else "核心诉求"
    obs = obs_top[0] if obs_top else "产品缺陷"
    return (f"当用户处于【{scene}】等场景中需要使用产品时，ta 的核心诉求是【{need}】，"
            f"以便避免「{obs}」这类问题带来的糟糕体验，真正把产品用得安心、用得值。")

def engine(counts, rows):
    scene_c = counts["使用场景"]
    obs_c = counts["使用阻碍"]
    need_c = counts["需求动机"]
    emo_c = counts["情绪"]
    pers_c = counts["用户画像"]

    scene_top = [t for t, _ in scene_c.most_common(6)]
    need_top = [t for t, _ in need_c.most_common(6)]
    obs_top = [t for t, _ in obs_c.most_common(6)]
    obs_items = obs_c.most_common(8)

    main_job = build_main_job(scene_top, need_top, obs_top)

    # 三层任务
    functional = scene_top[:5] or ["（无场景标签）"]
    # 情感任务：从需求 + 负向情绪推导
    emo_pos = [t for t, _ in emo_c.most_common() if emotion_polarity(t) >= 0]
    emo_neg = [t for t, _ in emo_c.most_common() if emotion_polarity(t) < 0]
    emotional = []
    for t in need_top[:3]:
        emotional.append(f"因「{t}」未被满足而渴望被妥帖对待")
    if emo_neg:
        emotional.append(f"摆脱「{emo_neg[0]}」等负面感受")
    if not emotional:
        emotional = ["（情感信号弱）"]
    # 社会任务：私密品类默认弱
    social = []
    if any("送礼" in t or "体面" in t or "社交" in t for t in need_top + list(pers_c)):
        social.append("在送礼/社交场景中维持得体的形象")
    else:
        social.append("以自用与隐私为主，社会任务弱；仅当「送礼体面」诉求出现时可激活")

    # 情境地图
    clusters, unclustered = cluster_scenes(scene_c)

    # 阻碍力量分级
    if obs_items:
        maxn = obs_items[0][1]
        obstacles_graded = []
        for t, n in obs_items:
            if n >= max(3, maxn * 0.6):
                lvl = "高强度"
            elif n >= max(2, maxn * 0.3):
                lvl = "中强度"
            else:
                lvl = "低强度"
            obstacles_graded.append((t, n, lvl))
    else:
        obstacles_graded = []

    # 期望进程（改进方向）
    progress = []
    for t, n in obs_items[:5]:
        mapped = None
        for key, val in OBSTACLE_TO_IMPROVE.items():
            if key in t:
                mapped = val
                break
        if not mapped:
            mapped = f"针对「{t}」做专项产品迭代"
        progress.append((t, n, mapped))

    # 四力
    push = obs_top[0] if obs_top else "（无）"
    pull = need_top[0] if need_top else "（无）"
    anxiety = []
    for t, n in obs_items:
        if any(k in t for k in FORCE_ANX_KEYS):
            anxiety.append(t)
    if emo_neg:
        anxiety.append(emo_neg[0])
    anxiety = anxiety[:3] or ["（无明显焦虑信号）"]
    habit = []
    for t, n in pers_c.most_common(3):
        habit.append(t)
    if not habit:
        habit = ["（无明显习惯信号）"]

    # 行动建议
    rec_product = [m for _, _, m in progress[:3]]
    rec_marketing = []
    if need_top:
        rec_marketing.append(f"围绕「{need_top[0]}」做核心卖点沟通")
    if emo_neg:
        rec_marketing.append(f"用真实实测消除「{emo_neg[0]}」顾虑")
    if not rec_marketing:
        rec_marketing = ["（缺营销信号）"]
    rec_innov = []
    if any("吸附" in t or "脱落" in t for t, _, _ in progress):
        rec_innov.append("吸附结构专利化，做成品类差异化锚点")
    rec_innov.append("去敏感化外观/包装，降低购买心理门槛")

    return {
        "main_job": main_job,
        "functional": functional,
        "emotional": emotional,
        "social": social,
        "clusters": clusters,
        "unclustered": unclustered,
        "obstacles": obstacles_graded,
        "progress": progress,
        "push": push, "pull": pull, "anxiety": anxiety, "habit": habit,
        "rec_product": rec_product, "rec_marketing": rec_marketing, "rec_innov": rec_innov,
        "scene_top": scene_top, "need_top": need_top, "obs_top": obs_top,
    }

# ----------------------------- HTML 渲染 -----------------------------
CSS = """
:root{--bg:#f7f8fb;--card:#fff;--ink:#1f2430;--mut:#6b7280;--line:#e6e8ef;
--brand:#4f46e5;--brand2:#0ea5e9;--rose:#e11d48;--amber:#d97706;--teal:#0f766e;}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
background:var(--bg);color:var(--ink);line-height:1.65;padding:32px 18px 64px}
.wrap{max-width:880px;margin:0 auto}
.hero{background:linear-gradient(135deg,#4f46e5,#0ea5e9);color:#fff;border-radius:18px;
padding:28px 30px;box-shadow:0 10px 30px rgba(79,70,229,.18)}
.hero h1{font-size:22px;font-weight:600;margin-bottom:6px}
.hero .meta{font-size:13px;opacity:.92;margin-top:10px;display:flex;flex-wrap:wrap;gap:8px}
.hero .pill{background:rgba(255,255,255,.18);padding:3px 10px;border-radius:999px;font-size:12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:22px 24px;margin-top:18px;
box-shadow:0 2px 10px rgba(31,36,48,.04)}
.card h2{font-size:16px;font-weight:600;margin-bottom:14px;display:flex;align-items:center;gap:8px}
.card h2 .n{width:24px;height:24px;border-radius:7px;background:var(--brand);color:#fff;
font-size:13px;display:inline-flex;align-items:center;justify-content:center}
.job{font-size:15px;background:#eef2ff;border-left:4px solid var(--brand);padding:16px 18px;border-radius:10px;color:#312e81}
.layers{display:grid;grid-template-columns:1fr 1fr 1fr;gap:14px}
.layer{border:1px solid var(--line);border-radius:10px;padding:14px}
.layer h3{font-size:13px;font-weight:600;margin-bottom:8px;color:var(--brand)}
.layer.em h3{color:var(--rose)} .layer.so h3{color:var(--teal)}
.layer ul{list-style:none;font-size:13px;color:var(--mut)} .layer li{padding:3px 0}
.chip{display:inline-block;background:#f1f5f9;border:1px solid var(--line);border-radius:999px;
padding:3px 10px;font-size:12px;margin:3px 4px 0 0;color:#334155}
.circ-row{display:flex;gap:10px;padding:8px 0;border-bottom:1px dashed var(--line);font-size:13px}
.circ-row:last-child{border-bottom:none}
.circ-name{width:140px;color:var(--brand);font-weight:600;flex:none}
.obs{display:flex;align-items:center;gap:12px;padding:9px 0;border-bottom:1px solid var(--line)}
.obs:last-child{border-bottom:none}
.obs .t{width:200px;font-size:13px}
.obs .bar{flex:1;height:8px;background:#eef2f7;border-radius:99px;overflow:hidden}
.obs .bar i{display:block;height:100%;background:var(--brand)}
.lvl{font-size:11px;padding:2px 8px;border-radius:99px}
.lvl.high{background:#fee2e2;color:var(--rose)} .lvl.mid{background:#fef3c7;color:var(--amber)}
.lvl.low{background:#e0f2fe;color:var(--brand2)}
.forces{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.force{border:1px solid var(--line);border-radius:10px;padding:14px}
.force h3{font-size:13px;font-weight:600;margin-bottom:8px}
.force.push h3{color:var(--rose)} .force.pull h3{color:var(--brand)}
.force.anx h3{color:var(--amber)} .force.hab h3{color:var(--teal)}
.recs{display:grid;grid-template-columns:1fr 1fr 1fr;gap:14px}
.rec{border-top:3px solid var(--brand);border-radius:10px;padding:14px;background:#fafbff}
.rec.mkt{border-color:var(--brand2)} .rec.inn{border-color:var(--teal)}
.rec h3{font-size:13px;font-weight:600;margin-bottom:8px}
.rec ul{list-style:none;font-size:13px;color:var(--mut)} .rec li{padding:3px 0;padding-left:14px;position:relative}
.rec li:before{content:"·";position:absolute;left:2px;color:var(--brand)}
.appx{font-size:12px;color:var(--mut)}
.appx table{width:100%;border-collapse:collapse;margin-top:8px}
.appx th,.appx td{border:1px solid var(--line);padding:6px 8px;text-align:left;font-size:12px}
.appx th{background:#f8fafc}
.foot{text-align:center;color:var(--mut);font-size:12px;margin-top:24px}
@media(max-width:680px){.layers,.recs{grid-template-columns:1fr}.forces{grid-template-columns:1fr}
.circ-name{width:110px}}
"""

def chip(s):
    return f'<span class="chip">{html.escape(s)}</span>'

def render(profile, eng, rows):
    gen = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    # 情境地图
    circ_html = ""
    all_clustered = []
    for name, items in eng["clusters"].items():
        tags = " ".join(chip(t) for t, _ in items)
        all_clustered.append(f"{name}（{sum(n for _,n in items)}）")
        circ_html += f'<div class="circ-row"><div class="circ-name">{html.escape(name)}</div><div>{tags}</div></div>'
    for t, n in eng["unclustered"][:6]:
        circ_html += f'<div class="circ-row"><div class="circ-name">其他</div><div>{chip(t)}</div></div>'

    # 阻碍
    maxn = eng["obstacles"][0][1] if eng["obstacles"] else 1
    obs_html = ""
    for t, n, lvl in eng["obstacles"]:
        cls = "high" if lvl == "高强度" else ("mid" if lvl == "中强度" else "low")
        pct = max(8, int(n / maxn * 100))
        obs_html += (f'<div class="obs"><div class="t">{html.escape(t)} <span class="appx">×{n}</span></div>'
                     f'<div class="bar"><i style="width:{pct}%"></i></div>'
                     f'<span class="lvl {cls}">{lvl}</span></div>')

    # 期望进程
    prog_html = "".join(
        f'<div class="obs"><div class="t">{html.escape(t)} <span class="appx">×{n}</span></div>'
        f'<div style="flex:1;font-size:13px;color:#334155">{html.escape(m)}</div></div>'
        for t, n, m in eng["progress"])

    forces_html = f"""
    <div class="force push"><h3>推力 · 现状痛点</h3><div>{chip(eng['push'])}</div></div>
    <div class="force pull"><h3>拉力 · 理想吸引</h3><div>{chip(eng['pull'])}</div></div>
    <div class="force anx"><h3>焦虑 · 决策顾虑</h3><div>{"".join(chip(a) for a in eng['anxiety'])}</div></div>
    <div class="force hab"><h3>习惯 · 现状惯性</h3><div>{"".join(chip(h) for h in eng['habit'])}</div></div>"""

    recs_html = f"""
    <div class="rec"><h3>产品侧</h3><ul>{"".join(f"<li>{html.escape(x)}</li>" for x in eng['rec_product'])}</ul></div>
    <div class="rec mkt"><h3>营销侧</h3><ul>{"".join(f"<li>{html.escape(x)}</li>" for x in eng['rec_marketing'])}</ul></div>
    <div class="rec inn"><h3>创新侧</h3><ul>{"".join(f"<li>{html.escape(x)}</li>" for x in eng['rec_innov'])}</ul></div>"""

    # 附录
    appx_rows = ""
    for m in COLMAP:
        c = profile[m]
        top = c.most_common(8)
        cells = "".join(f"<td>{html.escape(t)} ×{n}</td>" for t, n in top) or "<td>（无）</td>"
        appx_rows += f"<tr><th>{m}</th>{cells}</tr>"

    return f"""<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>JTBD 分析报告 · {html.escape(PRODUCT['category'])}</title>
<style>{CSS}</style></head><body><div class="wrap">
<div class="hero">
  <h1>JTBD 待完成任务 · 深度分析报告</h1>
  <div style="font-size:14px;opacity:.95">基于真实 VOC 导入数据 · 确定性引擎（无大模型）</div>
  <div class="meta">
    <span class="pill">分析目的：{html.escape(PRODUCT['purpose'])}</span>
    <span class="pill">产品类目：{html.escape(PRODUCT['category'])}</span>
    <span class="pill">样本量：{rows} 条评价</span>
    <span class="pill">生成：{gen}</span>
  </div>
</div>

<div class="card"><h2><span class="n">★</span>CORE JOB · 核心任务陈述</h2>
  <div class="job">{html.escape(eng['main_job'])}</div></div>

<div class="card"><h2><span class="n">1</span>三层任务结构</h2>
  <div class="layers">
    <div class="layer fn"><h3>功能任务</h3><ul>{"".join(f"<li>{html.escape(x)}</li>" for x in eng['functional'])}</ul></div>
    <div class="layer em"><h3>情感任务</h3><ul>{"".join(f"<li>{html.escape(x)}</li>" for x in eng['emotional'])}</ul></div>
    <div class="layer so"><h3>社会任务</h3><ul>{"".join(f"<li>{html.escape(x)}</li>" for x in eng['social'])}</ul></div>
  </div></div>

<div class="card"><h2><span class="n">2</span>任务情境地图</h2>{circ_html}</div>

<div class="card"><h2><span class="n">3</span>阻碍力量（按出现频次分级）</h2>{obs_html}</div>

<div class="card"><h2><span class="n">4</span>期望进程（阻碍 → 改进方向）</h2>{prog_html}</div>

<div class="card"><h2><span class="n">5</span>JTBD 四力模型</h2><div class="forces">{forces_html}</div></div>

<div class="card"><h2><span class="n">6</span>行动建议</h2><div class="recs">{recs_html}</div></div>

<div class="card appx"><h2><span class="n">7</span>数据附录 · 标签来源</h2>
  <div>下列结论均由下方真实标签频次聚合得出，可溯源。</div>
  <table><tr><th>模块</th><th colspan="8">Top 标签（频次）</th></tr>{appx_rows}</table></div>

<div class="foot">本报告由 VOC JTBD 分析机器人（确定性引擎）自动生成 · C 混合路线样本</div>
</div></body></html>"""

def main():
    counts, rows = aggregate(CSV_PATH)
    eng = engine(counts, rows)
    profile = counts
    html_out = render(profile, eng, rows)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(html_out)
    # 控制台摘要
    print(f"[OK] 样本 {rows} 条 | 场景标签 {len(counts['使用场景'])} | 阻碍标签 {len(counts['使用阻碍'])} | 需求 {len(counts['需求动机'])} | 情绪 {len(counts['情绪'])}")
    print(f"[CORE] {eng['main_job']}")
    print(f"[OUT] {OUT_PATH}")

if __name__ == "__main__":
    main()
