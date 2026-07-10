# -*- coding: utf-8 -*-
"""
VOC 多框架分析引擎（确定性，无大模型）
====================================
读真实 VOC CSV（已带结构化标签列） -> 聚合标签 -> 跑 7 个分析框架确定性引擎
-> 每个框架产出结构化数据 + HTML section。

7 框架（与前端 FRAMEWORKS 完全对齐）：
  jtbd           JTBD 待完成任务
  needs-analysis 十三种需求分析
  compass        产品创意罗盘（4象限 × 20 打法）
  extreme        极端/领先用户（von Hippel）
  triz           TRIZ 创新方法（40 发明原理）
  researcher     4象限用户需求（重要度-满意度矩阵）
  plutchik       Plutchik 情绪罗盘（8 基本情绪）

纯标准库，无外部依赖。可被 analyze_report.py / run_bot.py 复用。
"""
import csv, re, html, json, datetime
from collections import Counter

# ----------------------------- 工具 -----------------------------
def esc(s):
    return html.escape(str(s))

SPLIT_RE = re.compile(r"[,，、]\s*")

def split_tags(v):
    if not v:
        return []
    return [t.strip() for t in SPLIT_RE.split(v) if t and t.strip()]

def clean_tag(t, module):
    t = re.sub(r"^\d+[.、]\s*", "", t).strip()             # 去 "28." 编号
    if not t or t.isdigit():                                # 丢弃纯数字/空
        return ""
    if module == "需求动机":
        t = t.split("（")[0].split("(")[0].strip().rstrip("）)")
    # 过滤无意义/数据污染
    if any(k in t for k in ("无法判定", "是否提到", "与解放双手相关")):
        return ""
    if any(k in t for k in ("无法为你提供", "我会尽力", "作为一个AI", "提供相应解答",
                            "支持和解答", "抱歉", "作为AI", "帮你")):
        return ""
    if len(t) > 30:                                          # 超长疑似污染
        return ""
    if t in ("", "无法判定"):
        return ""
    return t

def emotion_polarity(t):
    if any(k in t for k in ("非常不满", "愤怒", "气愤", "厌恶", "嫌弃")):
        return -1
    if any(k in t for k in ("不满", "负向", "抱怨", "吐槽")):
        return -1
    if any(k in t for k in ("满意", "喜欢", "开心", "愉悦", "惊喜")):
        return 1
    if any(k in t for k in ("一般", "中性", "无感")):
        return 0
    return 0

# ----------------------------- 列映射 -----------------------------
COLMAP = {
    "使用场景": "使用场景标签",
    "使用阻碍": "产品问题标签",
    "问题类型": "问题类型标签",
    "需求动机": "需求维度标签库",
    "情绪": "情绪标签库",
    "用户画像": "用户属性",
    "解放双手场景问题": "解放双手场景的问题标签（跟解放双手相关）",
}

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

def top(counts, module, n=8):
    return counts[module].most_common(n)

# ============================================================
# 框架 1：JTBD 待完成任务
# ============================================================
SCENE_CLUSTER = {
    "淋浴/浴室环境": ["淋浴", "浴室", "墙面", "瓷砖", "玻璃", "镜面", "潮湿", "隔断", "门"],
    "卧室/居家": ["卧室", "床", "居家", "家用", "房间", "宿舍"],
    "旅行/外出": ["旅行", "出差", "便携", "外出", "户外", "酒店"],
    "光滑平面": ["光滑", "硬质", "平面", "桌面", "地板"],
    "粗糙/特殊面": ["粗糙", "混凝土", "砖墙", "木质", "多孔", "墙面"],
}
OBSTACLE_TO_IMPROVE = {
    "吸附不稳定": "增强吸盘吸附力与材质摩擦系数，覆盖更多墙面类型",
    "吸盘吸附力不足": "升级吸盘结构（真空泵/软胶双层），提升初始吸附与持久性",
    "产品质量差": "提升材质与整体工艺，建立出厂品控标准",
    "产品易断裂": "关键受力部位改用韧性材料，做跌落/弯折测试",
    "材质廉价": "改用亲肤医用级材质，消除塑料廉价感",
    "价格偏高": "优化成本结构或明示价值点，提升性价比感知",
    "与配件不兼容": "标准化接口/螺纹，随附适配环兼容主流配件",
    "配件缺失需另购": "将必要适配器纳入标配，减少二次购买摩擦",
    "螺纹不匹配": "统一螺纹规格并提供转接件",
    "噪音大": "改用静音马达结构 + 阻尼材料，控制声压",
    "清洁困难": "采用可拆洗内胆 / 免洗涂层，减少清洁死角",
    "尺寸不合适": "提供多档尺寸 / 入口渐宽设计，覆盖更多体型",
    "气味重": "改用无味医用硅胶，出厂前通风除味",
}
FORCE_PUSH_KEYS = ["脱落", "损坏", "断裂", "不稳定", "不匹配", "差", "廉价", "缺失", "噪音", "气味"]
FORCE_ANX_KEYS = ["缺失", "另购", "骗局", "透明", "信息", "适配", "价格"]

def cluster_scenes(scene_counter):
    out, unclustered = {}, []
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

def engine_jtbd(counts, rows, product):
    scene_c, obs_c, need_c, emo_c, pers_c = (counts["使用场景"], counts["使用阻碍"],
                                            counts["需求动机"], counts["情绪"], counts["用户画像"])
    scene_top = [t for t, _ in scene_c.most_common(6)]
    need_top = [t for t, _ in need_c.most_common(6)]
    obs_top = [t for t, _ in obs_c.most_common(6)]
    obs_items = obs_c.most_common(8)

    main_job = (f"当用户处于【{scene_top[0] if scene_top else '核心使用场景'}】等场景中需要使用产品时，"
                f"ta 的核心诉求是【{need_top[0] if need_top else '核心诉求'}】，"
                f"以便避免「{obs_top[0] if obs_top else '产品缺陷'}」这类问题带来的糟糕体验，"
                f"真正把产品用得安心、用得值。")

    functional = scene_top[:5] or ["（无场景标签）"]
    emo_pos = [t for t, _ in emo_c.most_common() if emotion_polarity(t) >= 0]
    emo_neg = [t for t, _ in emo_c.most_common() if emotion_polarity(t) < 0]
    emotional = [f"因「{t}」未被满足而渴望被妥帖对待" for t in need_top[:3]]
    if emo_neg:
        emotional.append(f"摆脱「{emo_neg[0]}」等负面感受")
    if not emotional:
        emotional = ["（情感信号弱）"]
    if any("送礼" in t or "体面" in t or "社交" in t for t in need_top + list(pers_c)):
        social = ["在送礼/社交场景中维持得体的形象"]
    else:
        social = ["以自用与隐私为主，社会任务弱；仅当「送礼体面」诉求出现时可激活"]

    clusters, unclustered = cluster_scenes(scene_c)
    obstacles_graded = []
    if obs_items:
        maxn = obs_items[0][1]
        for t, n in obs_items:
            lvl = "高强度" if n >= max(3, maxn * 0.6) else ("中强度" if n >= max(2, maxn * 0.3) else "低强度")
            obstacles_graded.append((t, n, lvl))
    progress = []
    for t, n in obs_items[:5]:
        mapped = next((v for k, v in OBSTACLE_TO_IMPROVE.items() if k in t), f"针对「{t}」做专项产品迭代")
        progress.append((t, n, mapped))
    push = obs_top[0] if obs_top else "（无）"
    pull = need_top[0] if need_top else "（无）"
    anxiety = [t for t, _ in obs_items if any(k in t for k in FORCE_ANX_KEYS)][:3]
    if emo_neg:
        anxiety.append(emo_neg[0])
    anxiety = anxiety[:3] or ["（无明显焦虑信号）"]
    habit = [t for t, _ in pers_c.most_common(3)] or ["（无明显习惯信号）"]
    rec_product = [m for _, _, m in progress[:3]]
    rec_marketing = []
    if need_top:
        rec_marketing.append(f"围绕「{need_top[0]}」做核心卖点沟通")
    if emo_neg:
        rec_marketing.append(f"用真实实测消除「{emo_neg[0]}」顾虑")
    rec_marketing = rec_marketing or ["（缺营销信号）"]
    rec_innov = []
    if any("吸附" in t or "脱落" in t for t, _, _ in progress):
        rec_innov.append("吸附结构专利化，做成品类差异化锚点")
    rec_innov.append("去敏感化外观/包装，降低购买心理门槛")

    return dict(main_job=main_job, functional=functional, emotional=emotional, social=social,
                clusters=clusters, unclustered=unclustered, obstacles=obstacles_graded,
                progress=progress, push=push, pull=pull, anxiety=anxiety, habit=habit,
                rec_product=rec_product, rec_marketing=rec_marketing, rec_innov=rec_innov,
                scene_top=scene_top, need_top=need_top, obs_top=obs_top)

def render_jtbd(eng, counts):
    circ_html = ""
    for name, items in eng["clusters"].items():
        tags = "".join(f'<span class="chip">{esc(t)}</span>' for t, _ in items)
        circ_html += f'<div class="row"><div class="row-k" style="color:var(--c-blue)">{esc(name)}</div><div>{tags}</div></div>'
    for t, n in eng["unclustered"][:6]:
        circ_html += f'<div class="row"><div class="row-k" style="color:var(--c-slate)">其他</div><div><span class="chip">{esc(t)}</span></div></div>'
    maxn = eng["obstacles"][0][1] if eng["obstacles"] else 1
    obs_html = ""
    for t, n, lvl in eng["obstacles"]:
        cls = "high" if lvl == "高强度" else ("mid" if lvl == "中强度" else "low")
        pct = max(8, int(n / maxn * 100))
        obs_html += (f'<div class="row"><div class="row-k" style="width:200px">{esc(t)} <span class="mut">×{n}</span></div>'
                     f'<div class="bar"><i style="width:{pct}%"></i></div>'
                     f'<span class="lvl {cls}">{lvl}</span></div>')
    prog_html = "".join(
        f'<div class="row"><div class="row-k" style="width:200px">{esc(t)} <span class="mut">×{n}</span></div>'
        f'<div style="flex:1;font-size:13px">{esc(m)}</div></div>' for t, n, m in eng["progress"])
    forces = (f'<div class="qcard push"><h4>推力 · 现状痛点</h4><div>{esc(eng["push"])}</div></div>'
              f'<div class="qcard pull"><h4>拉力 · 理想吸引</h4><div>{esc(eng["pull"])}</div></div>'
              f'<div class="qcard anx"><h4>焦虑 · 决策顾虑</h4><div>{"".join(f"<span class=chip>{esc(a)}</span>" for a in eng["anxiety"])}</div></div>'
              f'<div class="qcard hab"><h4>习惯 · 现状惯性</h4><div>{"".join(f"<span class=chip>{esc(h)}</span>" for h in eng["habit"])}</div></div>')
    recs = (f'<div class="qcard"><h4 style="color:var(--c-blue)">产品侧</h4><ul>{"".join(f"<li>{esc(x)}</li>" for x in eng["rec_product"])}</ul></div>'
            f'<div class="qcard"><h4 style="color:var(--c-teal)">营销侧</h4><ul>{"".join(f"<li>{esc(x)}</li>" for x in eng["rec_marketing"])}</ul></div>'
            f'<div class="qcard"><h4 style="color:var(--c-violet)">创新侧</h4><ul>{"".join(f"<li>{esc(x)}</li>" for x in eng["rec_innov"])}</ul></div>')
    return f'''
<div class="job">{esc(eng["main_job"])}</div>
<div class="grid3">
  <div class="box"><h4 style="color:var(--c-blue)">功能任务</h4><ul>{"".join(f"<li>{esc(x)}</li>" for x in eng["functional"])}</ul></div>
  <div class="box"><h4 style="color:var(--c-rose)">情感任务</h4><ul>{"".join(f"<li>{esc(x)}</li>" for x in eng["emotional"])}</ul></div>
  <div class="box"><h4 style="color:var(--c-teal)">社会任务</h4><ul>{"".join(f"<li>{esc(x)}</li>" for x in eng["social"])}</ul></div>
</div>
<h3 class="sub">任务情境地图</h3>{circ_html}
<h3 class="sub">阻碍力量（按频次分级）</h3>{obs_html}
<h3 class="sub">期望进程（阻碍 → 改进方向）</h3>{prog_html}
<h3 class="sub">JTBD 四力模型</h3><div class="grid2">{forces}</div>
<h3 class="sub">行动建议</h3><div class="grid3">{recs}</div>'''

# ============================================================
# 框架 2：十三种需求分析
# ============================================================
NEEDS13 = [
    ("生理满足", ["生理", "身体", "性", "释放", "快感", "高潮", "解压"]),
    ("安全", ["安全", "隐私", "卫生", "材质", "无毒", "可靠", "稳固", "放心", "安心"]),
    ("归属与爱", ["亲密", "伴侣", "关系", "爱", "互动", "陪伴", "感情"]),
    ("尊重", ["体面", "认可", "尊严", "高端", "档次", "面子", "格调"]),
    ("自我实现", ["探索", "成长", "提升", "自我", "进阶", "突破"]),
    ("认知", ["理解", "了解", "知识", "懂", "明白", "清晰"]),
    ("审美", ["美观", "设计", "颜值", "逼真", "视觉", "好看", "颜值"]),
    ("掌控", ["控制", "自主", "可调", "掌握", "自定义", "调节"]),
    ("刺激", ["刺激", "新鲜", "兴奋", "多样", "玩法", "趣味"]),
    ("舒适", ["舒适", "柔软", "手感", "贴合", "轻松", "顺滑", "亲肤"]),
    ("自由", ["自由", "无拘", "便携", "解放", "不受限", "灵活", "轻巧"]),
    ("影响", ["影响", "吸引", "魅力", "社交", "展示", "晒", "回头率"]),
    ("超越", ["极致", "巅峰", "忘我", "沉浸", "酣畅", "巅峰体验"]),
]
NEED_HIERARCHY = {"生理满足": "生存层", "安全": "生存层", "舒适": "生存层",
                  "归属与爱": "关系层", "尊重": "关系层", "影响": "关系层",
                  "认知": "成长层", "自我实现": "成长层", "掌控": "成长层",
                  "审美": "成长层", "刺激": "成长层", "自由": "成长层", "超越": "成长层"}

def engine_needs(counts, rows, product):
    scores = {name: 0 for name, _ in NEEDS13}
    evidence = {name: Counter() for name, _ in NEEDS13}
    src = []
    src += [(t, n, "需求动机") for t, n in counts["需求动机"].most_common(40)]
    src += [(t, n, "使用阻碍") for t, n in counts["使用阻碍"].most_common(40)]
    src += [(t, n, "情绪") for t, n in counts["情绪"].most_common(40)]
    for tag, n, mod in src:
        for name, keys in NEEDS13:
            if any(k in tag for k in keys):
                scores[name] += n
                evidence[name][tag] += n
    ranked = sorted(scores.items(), key=lambda x: -x[1])
    ranked = [(n, s) for n, s in ranked if s > 0] or [(n, 0) for n, _ in NEEDS13]
    top5 = ranked[:5]
    # 层次分布
    hier = Counter()
    for name, s in ranked:
        if s > 0:
            hier[NEED_HIERARCHY[name]] += s
    return dict(ranked=ranked, top5=top5, evidence=evidence,
                hierarchy=hier.most_common(), total=sum(scores.values()))

def render_needs(eng, counts):
    rows = ""
    for name, s in eng["ranked"][:8]:
        pct = max(6, int(s / (eng["ranked"][0][1] or 1) * 100))
        ev = "".join(f'<span class="chip">{esc(t)}×{n}</span>' for t, n in eng["evidence"][name].most_common(4))
        rows += (f'<div class="row"><div class="row-k" style="width:120px">{esc(name)}'
                 f'<span class="mut"> · {eng["hierarchy"] and NEED_HIERARCHY[name]}</span></div>'
                 f'<div class="bar"><i style="width:{pct}%;background:var(--c-violet)"></i></div>'
                 f'<div style="width:48px;text-align:right" class="mut">{s}</div></div>')
    hier = "".join(f'<span class="chip">{esc(k)} {v}</span>' for k, v in eng["hierarchy"])
    return f'''
<div class="grid2">
  <div><h3 class="sub">需求优先级（13 种人类需求映射）</h3>{rows}</div>
  <div>
    <h3 class="sub">需求层次分布</h3><div style="margin:8px 0">{hier}</div>
    <h3 class="sub">核心洞察</h3>
    <ul class="insight">
      <li>最凸显需求：<b>{esc(eng["top5"][0][0])}</b>（{eng["top5"][0][1]} 次信号），处于 <b>{NEED_HIERARCHY[eng["top5"][0][0]]}</b>。</li>
      <li>前 3 需求：{ "、".join(esc(n) for n,_ in eng["top5"][:3]) }，应作为产品定义的核心锚点。</li>
      <li>需求层次偏向 <b>{eng["hierarchy"][0][0] if eng["hierarchy"] else "—"}</b>，说明用户当前诉求集中在{ "生存/关系/成长" }的不同阶段。</li>
    </ul>
  </div>
</div>'''

# ============================================================
# 框架 3：产品创意罗盘（4 象限 × 20 打法）
# ============================================================
COMPASS_QUADS = [
    ("加 · 强化现有", "enhance", [
        "升级{mat}材质至医用级，消除廉价感与气味",
        "强化{obs}相关的{part}结构，提升耐用度",
        "提升{need}相关性能参数，拉开与竞品差距",
        "增加{scene}场景下的握持/固定稳定性",
        "把{need}做成可量化的体验指标对外沟通",
    ]),
    ("减 · 做减法", "reduce", [
        "针对{obs}做静音/轻量化处理，降低使用门槛",
        "简化{scene}场景下的安装/收纳步骤",
        "去掉冗余配件，核心功能做减法聚焦",
        "用免洗/可拆洗设计消除{obs}清洁负担",
        "弱化敏感外观，降低购买心理阻力",
    ]),
    ("乘 · 组合扩展", "combine", [
        "将{need}与{scene}场景打包成套装方案",
        "跨品类组合（如与润滑/清洁配套）提升客单",
        "把{obs}的解决方式做成可扩展模块生态",
        "结合{need}做内容/社群运营放大口碑",
        "用{scene}场景延展至旅行/礼品新人群",
    ]),
    ("除 · 重构替代", "rebuild", [
        "用结构重构解决{obs}，而非修补表面",
        "以服务/订阅模式替代一次性硬件投入",
        "用新材料/新工艺替代传统{mat}方案",
        "用 APP/智能控制替代机械旋钮交互",
        "重构价值主张，从卖产品转为卖{need}结果",
    ]),
]

def _pick(counts, mod, keys, n=1):
    out = []
    for t, _ in counts[mod].most_common(60):
        if any(k in t for k in keys):
            out.append(t)
        if len(out) >= n:
            break
    return out

def engine_compass(counts, rows, product):
    needs = [t for t, _ in counts["需求动机"].most_common(8)]
    obs = [t for t, _ in counts["使用阻碍"].most_common(8)]
    scenes = [t for t, _ in counts["使用场景"].most_common(6)]
    mats = _pick(counts, "使用阻碍", ["材质", "硅胶", "塑料"])
    parts = _pick(counts, "使用阻碍", ["结构", "接口", "螺纹", "吸盘", "电机"])
    ideas = []
    for qname, qkey, tactics in COMPASS_QUADS:
        filled = []
        for tpl in tactics:
            s = tpl
            s = s.replace("{need}", needs[0] if needs else "核心诉求")
            s = s.replace("{obs}", obs[0] if obs else "主要痛点")
            s = s.replace("{scene}", scenes[0] if scenes else "核心场景")
            s = s.replace("{mat}", mats[0] if mats else "主体")
            s = s.replace("{part}", parts[0] if parts else "关键部位")
            filled.append(s)
        ideas.append((qname, qkey, filled))
    return dict(ideas=ideas)

def render_compass(eng, counts):
    html_parts = ""
    for qname, qkey, filled in eng["ideas"]:
        items = "".join(f'<li>{esc(x)}</li>' for x in filled)
        html_parts += f'<div class="qcard"><h4 style="color:var(--c-cyan)">{esc(qname)}</h4><ul>{items}</ul></div>'
    return f'<div class="grid2">{html_parts}</div>'

# ============================================================
# 框架 4：极端/领先用户（von Hippel）
# ============================================================
def engine_extreme(counts, rows, product):
    obs_items = counts["使用阻碍"].most_common(8)
    need_items = counts["需求动机"].most_common(8)
    pers_items = counts["用户画像"].most_common(8)
    # 极端痛点用户：高频阻碍
    extreme_pain = [(t, n) for t, n in obs_items if n >= max(2, obs_items[0][1] * 0.4)] if obs_items else []
    # 领先需求：高频需求但尚未被满足（对应阻碍存在）
    lead_needs = []
    for t, n in need_items:
        related_obs = [o for o, _ in obs_items if any(k in o for k in t) or any(k in t for k in o)]
        lead_needs.append((t, n, bool(related_obs)))
    lead_needs = [x for x in lead_needs if x[2]][:4] or [(t, n, False) for t, n in need_items[:3]]
    # 行为线索：用户画像 + 解放双手场景问题（代表 workarounds/advanced use）
    behaviors = [t for t, _ in pers_items[:5]]
    workarounds = [t for t, _ in counts["解放双手场景问题"].most_common(6)]
    # 创新机会：极端用户的未满足需求 -> 未来主流
    opp = []
    for t, n, _ in lead_needs[:3]:
        opp.append(f"为「{t}」提供超出当前主流的解决方案，领先用户今天的痛点就是大众明天的需求")
    if obs_items:
        opp.append(f"针对极端痛点「{obs_items[0][0]}」做结构性突破，而非渐进修补")
    return dict(extreme_pain=extreme_pain, lead_needs=lead_needs, behaviors=behaviors,
                workarounds=workarounds, opp=opp, top_obs=obs_items[0][0] if obs_items else "（无）")

def render_extreme(eng, counts):
    pain = "".join(f'<li><span class="chip">{esc(t)}</span> ×{n}（高频极端痛点）</li>' for t, n in eng["extreme_pain"]) or "<li>（无明显极端痛点）</li>"
    lead = "".join(f'<li><b>{esc(t)}</b> ×{n} {"✓ 已有对应阻碍→真实未满足" if r else "→ 潜在领先需求"}</li>' for t, n, r in eng["lead_needs"])
    beh = "".join(f'<span class="chip">{esc(t)}</span>' for t in eng["behaviors"]) or "（无）"
    wrk = "".join(f'<span class="chip">{esc(t)}</span>' for t in eng["workarounds"]) or "（无明确 workaround 信号）"
    opp = "".join(f'<li>{esc(x)}</li>' for x in eng["opp"]) or "<li>（无）</li>"
    return f'''
<div class="grid2">
  <div>
    <h3 class="sub">极端痛点用户画像</h3><ul>{pain}</ul>
    <h3 class="sub">领先用户行为线索</h3><div style="margin:6px 0">{beh}</div>
    <h3 class="sub">进阶使用 / Workaround 信号</h3><div style="margin:6px 0">{wrk}</div>
  </div>
  <div>
    <h3 class="sub">领先用户未被满足的需求</h3><ul>{lead}</ul>
    <h3 class="sub">创新机会（von Hippel：领先用户需求预测未来主流）</h3><ul class="insight">{opp}</ul>
  </div>
</div>'''

# ============================================================
# 框架 5：TRIZ 创新方法（40 发明原理）
# ============================================================
TRIZ_PRINCIPLES = {
    1: "分割", 2: "抽取", 3: "局部质量", 4: "非对称", 5: "合并", 7: "嵌套",
    8: "重量补偿", 9: "预先反作用", 10: "预先作用", 13: "反向", 14: "曲面替代",
    15: "动态性", 16: "不足/过度作用", 17: "另一维度", 19: "周期性作用",
    20: "有效持续作用", 24: "中介物", 25: "自服务", 26: "复制", 27: "低价/一次性",
    28: "机械系统替代", 30: "柔性外壳", 31: "多孔材料", 32: "颜色改变",
    34: "抛弃/修复", 35: "参数变化", 36: "同源", 37: "热膨胀", 39: "惰性环境", 40: "复合材料",
}
TRIZ_MAP = {
    "吸附/固定": ([1, 7, 15, 17, 31], "吸附力提升与便携性之间存在矛盾：在『固定更牢』与『更轻更便携』之间"),
    "便携/重量": ([8, 30, 27], "功能完整与轻量便携存在矛盾：『更强性能』与『更轻巧』之间"),
    "噪音": ([2, 19, 28, 35], "强动力与低噪音存在矛盾：『动力更足』与『更安静』之间"),
    "清洁": ([28, 3, 34, 25], "结构复杂与易清洁存在矛盾：『功能更多』与『更好打理』之间"),
    "材质/气味": ([40, 39, 14], "成本与体验存在矛盾：『更安全的材质』与『可控成本』之间"),
    "价格/价值": ([27, 16, 35], "高价值与低价格存在矛盾：『体验升级』与『价格敏感』之间"),
    "体验/逼真": ([26, 32, 36], "真实感与隐私存在矛盾：『更逼真』与『更低调隐私』之间"),
}
TRIZ_TRIGGER = {
    "吸附/固定": ["吸附", "固定", "吸盘", "脱落", "不稳", "墙面"],
    "便携/重量": ["便携", "重量", "轻", "出差", "旅行", "收纳"],
    "噪音": ["噪音", "声音", "静音", "响"],
    "清洁": ["清洁", "清洗", "拆洗", "卫生", "死角"],
    "材质/气味": ["材质", "硅胶", "塑料", "气味", "廉价", "亲肤"],
    "价格/价值": ["价格", "性价比", "贵", "偏贵", "价值"],
    "体验/逼真": ["逼真", "视觉", "手感", "体验", "触感"],
}

def engine_triz(counts, rows, product):
    text_blob = " ".join(
        [t for t, _ in counts["使用阻碍"].most_common(40)] +
        [t for t, _ in counts["需求动机"].most_common(30)] +
        [t for t, _ in counts["使用场景"].most_common(20)]
    )
    results = []
    for theme, triggers in TRIZ_TRIGGER.items():
        if any(k in text_blob for k in triggers):
            nums, contradiction = TRIZ_MAP[theme]
            princ = [(n, TRIZ_PRINCIPLES[n]) for n in nums]
            results.append((theme, contradiction, princ))
    if not results:
        results = [("吸附/固定", TRIZ_MAP["吸附/固定"][1], [(n, TRIZ_PRINCIPLES[n]) for n in TRIZ_MAP["吸附/固定"][0]])]
    return dict(results=results)

def render_triz(eng, counts):
    parts = ""
    for theme, contradiction, princ in eng["results"]:
        plist = "".join(f'<span class="chip">#{n} {esc(p)}</span>' for n, p in princ)
        parts += f'''<div class="qcard">
          <h4 style="color:var(--c-amber)">技术矛盾：{esc(theme)}</h4>
          <div class="mut" style="font-size:13px;margin:4px 0 8px">{esc(contradiction)}</div>
          <div><b>适用发明原理：</b>{plist}</div>
        </div>'''
    return f'<div class="grid2">{parts}</div>'

# ============================================================
# 框架 6：4 象限用户需求（重要度-满意度矩阵）
# ============================================================
def _norm(val, mx):
    return round(val / mx * 100) if mx else 0

def engine_researcher(counts, rows, product):
    themes = []
    for t, n in counts["需求动机"].most_common(12):
        themes.append((t, n, "need"))
    for t, n in counts["使用阻碍"].most_common(12):
        themes.append((t, n, "obs"))
    if not themes:
        return dict(points=[], quad={})
    maxn = max(n for _, n, _ in themes) or 1
    points = []
    for t, n, kind in themes:
        imp = _norm(n, maxn)
        if kind == "obs":
            sat = max(8, 45 - int(n / maxn * 40))          # 阻碍越多→满意度越低
        else:
            # 需求满意度：看是否有对应阻碍拉低
            rel_obs = sum(on for ot, on in counts["使用阻碍"].most_common(20) if any(k in ot for k in t) or any(k in t for k in ot))
            sat = max(25, 88 - int(rel_obs / max(1, maxn) * 50))
        points.append((t, imp, sat, kind))
    # 象限
    imp_med = sorted(p[1] for p in points)[len(points)//2]
    quad = {"重点改进区": [], "保持优势区": [], "过度投入区": [], "低优先级区": []}
    for t, imp, sat, kind in points:
        hi = imp >= imp_med
        hs = sat >= 55
        if hi and not hs:
            quad["重点改进区"].append((t, imp, sat))
        elif hi and hs:
            quad["保持优势区"].append((t, imp, sat))
        elif not hi and hs:
            quad["过度投入区"].append((t, imp, sat))
        else:
            quad["低优先级区"].append((t, imp, sat))
    return dict(points=points, quad=quad, imp_med=imp_med)

def render_researcher(eng, counts):
    # 散点（用定位 div 模拟象限图）
    dots = ""
    for t, imp, sat, kind in eng["points"]:
        x = max(4, min(96, imp))
        y = max(4, min(96, 100 - sat))
        color = "var(--c-rose)" if kind == "obs" else "var(--c-blue)"
        dots += f'<span class="dot" title="{esc(t)} (重要{imp}/满意{sat})" style="left:{x}%;top:{y}%;background:{color}"></span>'
    quad_html = ""
    qcolor = {"重点改进区": "var(--c-rose)", "保持优势区": "var(--c-teal)", "过度投入区": "var(--c-amber)", "低优先级区": "var(--c-slate)"}
    for q, items in eng["quad"].items():
        its = "".join(f'<span class="chip">{esc(t)} <span class="mut">{imp}/{sat}</span></span>' for t, imp, sat in items) or '<span class="mut">（空）</span>'
        quad_html += f'<div class="qcard"><h4 style="color:{qcolor[q]}">{esc(q)}</h4><div style="margin-top:6px">{its}</div></div>'
    return f'''
<div class="quadmap">
  <div class="qm-axis-y">满意度 →</div>
  <div class="qm-axis-x">重要度 →</div>
  <div class="qm-cross-h"></div><div class="qm-cross-v"></div>
  {dots}
  <div class="qm-label tl">高重要·高满意（保持优势）</div>
  <div class="qm-label tr">高重要·低满意（重点改进）</div>
  <div class="qm-label bl">低重要·高满意（过度投入）</div>
  <div class="qm-label br">低重要·低满意（低优先级）</div>
</div>
<h3 class="sub">象限归类（蓝=需求 / 红=阻碍）</h3>
<div class="grid2">{quad_html}</div>'''

# ============================================================
# 框架 7：Plutchik 情绪罗盘（8 基本情绪）
# ============================================================
EMOTIONS8 = {
    "喜悦": ["满意", "喜欢", "开心", "愉悦", "高兴", "惊喜", "享受", "爽"],
    "信任": ["信任", "可靠", "安心", "放心", "稳", "踏实"],
    "恐惧": ["担忧", "害怕", "顾虑", "焦虑", "担心", "怕"],
    "惊讶": ["惊讶", "意外", "惊艳", "出乎意料", "震撼"],
    "悲伤": ["失望", "失落", "遗憾", "难过", "伤心"],
    "厌恶": ["厌恶", "嫌弃", "气味", "廉价感", "反感", "恶心"],
    "愤怒": ["愤怒", "气愤", "不满", "吐槽", "差评", "无语"],
    "期待": ["期待", "希望", "想要", "渴望", "种草", "期待值"],
}
EMO_COLOR = {"喜悦": "#22c55e", "信任": "#3b82f6", "恐惧": "#8b5cf6", "惊讶": "#f59e0b",
             "悲伤": "#64748b", "厌恶": "#a16207", "愤怒": "#ef4444", "期待": "#ec4899"}

def engine_plutchik(counts, rows, product):
    scores = {e: 0 for e in EMOTIONS8}
    evidence = {e: Counter() for e in EMOTIONS8}
    for tag, n in counts["情绪"].most_common(80):
        for e, keys in EMOTIONS8.items():
            if any(k in tag for k in keys):
                scores[e] += n
                evidence[e][tag] += n
    # 也用阻碍/需求补充极性
    neg = sum(n for t, n in counts["使用阻碍"].most_common(40) if any(k in t for k in ["差", "劣质", "失败", "断", "坏"]))
    if neg:
        scores["愤怒"] += neg // 3
    ranked = sorted(scores.items(), key=lambda x: -x[1])
    ranked = [(e, s) for e, s in ranked if s > 0] or list(scores.items())
    total = sum(scores.values()) or 1
    dominant_polarity = "正向" if sum(scores[e] for e in ["喜悦", "信任", "期待"]) > sum(scores[e] for e in ["愤怒", "厌恶", "悲伤", "恐惧"]) else "负向"
    return dict(ranked=ranked, evidence=evidence, total=total,
                dominant_polarity=dominant_polarity, top3=ranked[:3])

def render_plutchik(eng, counts):
    wheel = ""
    for e, s in eng["ranked"]:
        pct = max(5, int(s / (eng["ranked"][0][1] or 1) * 100))
        ev = "".join(f'<span class="chip">{esc(t)}×{n}</span>' for t, n in eng["evidence"][e].most_common(3))
        wheel += (f'<div class="row"><div class="row-k" style="width:64px;color:{EMO_COLOR[e]}">{esc(e)}</div>'
                  f'<div class="bar"><i style="width:{pct}%;background:{EMO_COLOR[e]}"></i></div>'
                  f'<div style="width:44px;text-align:right" class="mut">{s}</div></div>'
                  f'<div style="margin:2px 0 8px 76px;font-size:12px">{ev}</div>')
    top3 = "、".join(f"{e}({s})" for e, s in eng["top3"])
    return f'''
<div class="grid2">
  <div>
    <h3 class="sub">8 种基本情绪分布</h3>{wheel}
  </div>
  <div>
    <h3 class="sub">情绪主导</h3>
    <div class="pill-big" style="background:{EMO_COLOR.get(eng['top3'][0][0],'#888')}">主导情绪极性：{esc(eng['dominant_polarity'])}</div>
    <ul class="insight">
      <li>Top3 情绪：<b>{esc(top3)}</b></li>
      <li>情绪主要由 {'阻碍/痛点（负向）' if eng['dominant_polarity']=='负向' else '需求满足（正向）'} 驱动。</li>
      <li>情感设计建议：用「{esc(eng['top3'][0][0])}」做品牌情绪锚点，针对性消解「{esc(eng['ranked'][-1][0] if eng['ranked'] else '负面')}」。</li>
    </ul>
  </div>
</div>'''

# ----------------------------- 注册表 -----------------------------
FRAMES = [
    ("jtbd", "🎯", "#2563EB", "JTBD 待完成任务", "理解用户真正想要完成的任务（功能/情感/社会三层）", engine_jtbd, render_jtbd),
    ("needs-analysis", "🧭", "#7C3AED", "十三种需求分析", "从 13 种人类需求出发，定位需求层次与优先级", engine_needs, render_needs),
    ("compass", "🧩", "#0891B2", "产品创意罗盘", "4 象限 × 20 种打法，系统化发散产品创意", engine_compass, render_compass),
    ("extreme", "🔬", "#059669", "极端/领先用户", "基于 von Hippel 理论，从领先用户挖未来需求", engine_extreme, render_extreme),
    ("triz", "⚙️", "#D97706", "TRIZ 创新方法", "40 个发明原理，系统化解决技术矛盾", engine_triz, render_triz),
    ("researcher", "📊", "#DB2777", "4象限用户需求", "重要度-满意度矩阵，区分表达需求与真实需求", engine_researcher, render_researcher),
    ("plutchik", "🎭", "#BE185D", "Plutchik 情绪罗盘", "8 种基本情绪 + 强度，洞察情感驱动因素", engine_plutchik, render_plutchik),
]

def run_all(counts, rows, product):
    out = []
    for key, icon, color, name, desc, eng_fn, ren_fn in FRAMES:
        try:
            eng = eng_fn(counts, rows, product)
            body = ren_fn(eng, counts)
        except Exception as e:
            body = f'<div class="mut">引擎执行出错：{esc(e)}</div>'
        out.append(dict(key=key, icon=icon, color=color, name=name, desc=desc, body=body))
    return out

# ----------------------------- 共享 CSS -----------------------------
REPORT_CSS = """
:root{--bg:#f7f8fb;--card:#fff;--ink:#1f2430;--mut:#6b7280;--line:#e6e8ef;
--c-blue:#2563EB;--c-violet:#7C3AED;--c-cyan:#0891B2;--c-teal:#059669;
--c-amber:#D97706;--c-rose:#E11D48;--c-pink:#DB2777;--c-slate:#64748B;}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
background:var(--bg);color:var(--ink);line-height:1.65;padding:0 0 64px}
.wrap{max-width:980px;margin:0 auto;padding:0 18px}
.hero{background:linear-gradient(135deg,#4f46e5,#0ea5e9);color:#fff;padding:30px 18px;margin-bottom:22px}
.hero .inner{max-width:980px;margin:0 auto;padding:0 18px}
.hero h1{font-size:23px;font-weight:600;margin-bottom:6px}
.hero .sub{font-size:14px;opacity:.95}
.hero .meta{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}
.hero .pill{background:rgba(255,255,255,.18);padding:4px 11px;border-radius:999px;font-size:12px}
.toc{position:sticky;top:0;background:rgba(255,255,255,.92);backdrop-filter:blur(8px);
border-bottom:1px solid var(--line);padding:10px 0;z-index:5;margin-bottom:8px}
.toc .inner{max-width:980px;margin:0 auto;padding:0 18px;display:flex;flex-wrap:wrap;gap:8px}
.toc a{font-size:12.5px;color:var(--mut);text-decoration:none;padding:4px 10px;border:1px solid var(--line);border-radius:999px}
.toc a:hover{color:var(--c-blue);border-color:var(--c-blue)}
.fw{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:22px 24px;margin-top:16px;
box-shadow:0 2px 10px rgba(31,36,48,.04);scroll-margin-top:56px}
.fw-head{display:flex;align-items:center;gap:10px;margin-bottom:14px;padding-bottom:12px;border-bottom:2px solid var(--line)}
.fw-head .ico{font-size:20px}
.fw-head .nm{font-size:17px;font-weight:600}
.fw-head .ds{font-size:12.5px;color:var(--mut);margin-left:auto;text-align:right;max-width:50%}
.job{font-size:15px;background:#eef2ff;border-left:4px solid var(--c-blue);padding:16px 18px;border-radius:10px;color:#312e81;margin-bottom:6px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.grid3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:14px}
.box,.qcard{border:1px solid var(--line);border-radius:10px;padding:14px}
.box h4,.qcard h4{font-size:13.5px;font-weight:600;margin-bottom:8px}
.box ul,.qcard ul{list-style:none;font-size:13px;color:var(--mut)}
.box li,.qcard li{padding:3px 0}
.sub{font-size:14px;font-weight:600;margin:16px 0 8px;color:var(--ink)}
.row{display:flex;gap:10px;align-items:center;padding:7px 0;border-bottom:1px dashed var(--line);font-size:13px}
.row:last-child{border-bottom:none}
.row-k{color:var(--c-blue);font-weight:600;flex:none}
.bar{flex:1;height:8px;background:#eef2f7;border-radius:99px;overflow:hidden;min-width:60px}
.bar i{display:block;height:100%;background:var(--c-blue)}
.lvl{font-size:11px;padding:2px 8px;border-radius:99px;flex:none}
.lvl.high{background:#fee2e2;color:var(--c-rose)} .lvl.mid{background:#fef3c7;color:var(--c-amber)}
.lvl.low{background:#e0f2fe;color:var(--c-blue)}
.chip{display:inline-block;background:#f1f5f9;border:1px solid var(--line);border-radius:999px;
padding:3px 9px;font-size:12px;margin:3px 4px 0 0;color:#334155}
.insight{list-style:none;font-size:13px;color:#334155}
.insight li{padding:4px 0 4px 16px;position:relative}
.insight li:before{content:"▸";position:absolute;left:0;color:var(--c-blue)}
.pill-big{display:inline-block;color:#fff;padding:8px 14px;border-radius:10px;font-weight:600;font-size:14px;margin:6px 0}
.quadmap{position:relative;height:300px;background:#fafbff;border:1px solid var(--line);border-radius:12px;margin:10px 0}
.quadmap .dot{position:absolute;width:14px;height:14px;border-radius:50%;transform:translate(-50%,-50%);
border:2px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.3)}
.qm-cross-h{position:absolute;left:0;right:0;top:50%;height:1px;background:var(--line)}
.qm-cross-v{position:absolute;top:0;bottom:0;left:50%;width:1px;background:var(--line)}
.qm-axis-y{position:absolute;left:6px;top:50%;transform:rotate(-90deg);font-size:11px;color:var(--mut)}
.qm-axis-x{position:absolute;bottom:4px;right:10px;font-size:11px;color:var(--mut)}
.qm-label{position:absolute;font-size:10.5px;color:var(--mut)}
.qm-label.tl{left:8px;top:6px}.qm-label.tr{right:8px;top:6px;text-align:right}
.qm-label.bl{left:8px;bottom:6px}.qm-label.br{right:8px;bottom:6px;text-align:right}
.appx{font-size:12px;color:var(--mut)}
.appx table{width:100%;border-collapse:collapse;margin-top:8px}
.appx th,.appx td{border:1px solid var(--line);padding:6px 8px;text-align:left;font-size:12px}
.appx th{background:#f8fafc}
.foot{text-align:center;color:var(--mut);font-size:12px;margin-top:26px}
@media(max-width:720px){.grid2,.grid3{grid-template-columns:1fr}.fw-head .ds{display:none}}
"""

def build_multiframe_report(product, counts, rows, extra=None):
    sections = run_all(counts, rows, product)
    gen = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    toc = "".join(f'<a href="#fw-{s["key"]}">{s["icon"]} {esc(s["name"])}</a>' for s in sections)
    body = ""
    for s in sections:
        body += (f'<section class="fw" id="fw-{s["key"]}">'
                 f'<div class="fw-head"><span class="ico">{s["icon"]}</span>'
                 f'<span class="nm" style="color:{s["color"]}">{esc(s["name"])}</span>'
                 f'<span class="ds">{esc(s["desc"])}</span></div>{s["body"]}</section>')
    # 附录
    appx_rows = ""
    for m in COLMAP:
        c = counts[m]
        top = c.most_common(10)
        cells = "".join(f"<td>{esc(t)} ×{n}</td>" for t, n in top) or "<td>（无）</td>"
        appx_rows += f"<tr><th>{esc(m)}</th>{cells}</tr>"
    appendix = (f'<section class="fw" id="fw-appendix"><div class="fw-head">'
                f'<span class="ico">📎</span><span class="nm">数据附录 · 标签来源</span>'
                f'<span class="ds">所有结论均可溯源到下列真实标签频次</span></div>'
                f'<div class="appx"><table><tr><th>模块</th><th colspan="10">Top 标签（频次）</th></tr>{appx_rows}</table></div></section>')
    return f"""<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>VOC 多框架分析报告 · {esc(product.get('category',''))}</title>
<style>{REPORT_CSS}</style></head><body>
<div class="hero"><div class="inner">
  <h1>VOC 多框架深度分析报告</h1>
  <div class="sub">基于真实 VOC 导入数据 · 7 框架确定性引擎（无大模型）· 与前端 FRAMEWORKS 对齐</div>
  <div class="meta">
    <span class="pill">分析目的：{esc(product.get('purpose',''))}</span>
    <span class="pill">产品类目：{esc(product.get('category',''))}</span>
    <span class="pill">样本量：{rows} 条评价</span>
    <span class="pill">覆盖框架：{len(sections)} 个</span>
    <span class="pill">生成：{gen}</span>
  </div>
</div></div>
<div class="toc"><div class="inner">{toc}<a href="#fw-appendix">📎 附录</a></div></div>
<div class="wrap">{body}{appendix}
<div class="foot">本报告由 VOC 分析机器人（确定性多框架引擎）自动生成 · C 混合路线</div>
</div></body></html>"""
