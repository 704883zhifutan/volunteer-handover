"""生成 docs/discovery-flow.svg：业务需求发现与验证流程（AI 在哪里、人必须在哪里）。

和 make_flowchart.py 的分工：
- flowchart.svg 画的是"工具上线之后怎么跑"；
- 这张画的是"结论是**怎么得出来的**"——访谈、事实、假设、证伪、签字、试点。
  它回答老板最常问的那句：这些结论，凭什么信？

用法：`python3 scripts/make_discovery_flow.py`
"""

from __future__ import annotations

import html
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

W = 1040
MAIN_X = 190
MAIN_W = 470
MAIN_CX = MAIN_X + MAIN_W // 2
BR_X = 700
BR_W = 320
GAP = 42
GUTTER = 680

INK = "#1f2937"
LINE = "#94a3b8"

AI = ("#f5f3ff", "#c4b5fd", "#6d28d9")
HUMAN = ("#f1f5f9", "#cbd5e1", "#475569")
DATA = ("#ecfdf5", "#a7f3d0", "#047857")

HEAD_NOTE = "范围：从“六个人各说一段”到“敢在真实班次上试一次”。AI 只做草稿和核对，签字一律是人。"


def _chip(kind, label=None):
    base = {"ai": ("AI 起草", AI), "human": ("人判断", HUMAN), "data": ("人记录", DATA)}[kind]
    return (label or base[0], base[1])


NODES = [
    dict(no="01", kind="process", chip="human", chip_label="人定",
         title="业务目标与边界",
         sub=["一句话目标；以及不可越的三条：只读、不外发、不自动指派", "谁定范围、谁有叫停权，一次讲清（f04 / f05）"]),
    dict(no="02", kind="process", chip="human", chip_label="人定",
         title="选访谈对象：六个角色",
         sub=["每人只知道自己那一段；单一角色的说法不成立", "跨角色交叉，才有“事实”而不是“观点”"]),
    dict(no="03", kind="process", chip="data",
         title="逐条记录事实 f00–f55",
         sub=["编号 + 原话 + 出处；先不做归纳，也不急着下结论", "记下“没被提到”的东西，往往比说出来的更关键"]),
    dict(no="04", kind="process", chip="ai",
         title="AI：抽取候选问题",
         sub=["把事实归到问题类别，标出互相矛盾的条目", "只生成候选，不判定真假；候选必须能回到 f 编号"]),
    dict(no="05", kind="decision",
         title="事实够不够撑一条需求",
         sub="一条结论至少三条事实",
         branch=dict(tone="warn", title="回去补证，不硬写",
                     sub=["缺证的需求写出来也验不掉", "补一轮访谈，好过 W3 才发现没基线"],
                     loop="补证后重来")),
    dict(no="06", kind="decision",
         title="同一事实 ≥2 个角色",
         sub="交叉验证",
         branch=dict(tone="warn", title="降级为待验证假设",
                     sub=["不删：可能是真的，只是还没人佐证", "清单上标清“单角色”，复盘时优先验"])),
    dict(no="07", kind="process", chip="ai",
         title="AI：写可证伪的需求假设",
         sub=["格式固定：如果 X，则 Y；判定方法 + 分母 + 判定人", "写不出判定方法的，一律退回重写"]),
    dict(no="08", kind="decision",
         title="有量化基线吗",
         sub="当前值 / 分母 / 来源",
         branch=dict(tone="warn", title="先测基线，不报方案",
                     sub=["没有基线，“效率提升 40%”就是编的", "基线本身也要人认，不是系统算的"])),
    dict(no="09", kind="process", chip="ai",
         title="AI：设计确定性校验",
         sub=["一条校验对应一种失败方式；只判定，不修复", "每条结论必须带 文件#L行号，否则丢弃"]),
    dict(no="10", kind="decision",
         title="这条能被工具判定吗",
         sub="还是人的判断",
         branch=dict(tone="ok", title="写成人判断，工具只给依据",
                     sub=["“交接完成”归业务方（G3），代码不判", "宁可少一个自动结论，不要多一个假结论"])),
    dict(no="11", kind="sign", who="顾明岚",
         title="业务负责人签范围",
         sub=["签的是“做什么、不做什么”，不是签收文档", "范围外的需求一律记入下一批，不进本次试点"]),
    dict(no="12", kind="sign", who="傅景",
         title="质量负责人签验收口径",
         sub=["金标怎么标、召回怎么算、误报率分母是谁", "验收不可证伪，等于没有验收"]),
    dict(no="13", kind="process", chip="human", chip_label="人做",
         title="桌面推演 W0",
         sub=["用小样本把假设走一遍，不碰真实业务数据", "目的是暴露“我们以为对但其实不对”的地方"]),
    dict(no="14", kind="decision",
         title="假设能被证伪吗",
         sub="反例必须存在",
         branch=dict(tone="bad", title="退回 07 改假设",
                     sub=["证不掉的假设，试点也证明不了", "最贵的错误是把“听起来对”当成“已验证”"])),
    dict(no="15", kind="sign", who="叶书",
         title="客户侧确认用途与口径",
         sub=["对外怎么说、什么算“已交接”，由客户侧确认", "系统不自动对外承诺（f52）"]),
    dict(no="16", kind="sign", who="三方",
         title="试点放行签字",
         sub=["G1 能不能说“发现全部重叠” · G2 队列谁值守 · G3 完成定义", "缺一签就不放行：退出码 3，不是警告"]),
    dict(no="17", kind="process", chip="human", chip_label="人做",
         title="现场试点 W2",
         sub=["只开三个环节：交接、签到、排班；其余保持人肉", "清单只读，不写回任何系统"]),
    dict(no="18", kind="decision",
         title="证据够不够扩范围",
         sub="扩 / 收 / 停",
         branch=dict(tone="ok", title="收窄或停，不硬撑",
                     sub=["工时没降就是没降，不许换口径解释", "停也是结论：比扩错了便宜"])),
    dict(no="19", kind="process", chip="human", chip_label="人定",
         title="复盘决策门 W4 + 重新报价",
         sub=["按实测工时、误报率、确认完整率重算价值", "报价随范围走：加范围必须加钱，减范围退钱"]),
]

ROLES = [
    ("顾明岚", "业务负责人", "定范围、签生效、拍试点口径", "f00 / f04"),
    ("林亦舟", "赛事现场协调员", "现场核对与异常证实、顶班调人", "f10–f14"),
    ("唐映秋", "项目流程协调员", "回填复核、交接与资料责任", "f20 / f25"),
    ("秦芮", "数字化工程师", "只读导出、快照与编号规则", "f30 / f31"),
    ("傅景", "审核与质量负责人", "金标标注、门禁签字、叫停权", "f41 / f44"),
    ("叶书", "客户协同代表", "对外口径确认，不自动承诺", "f50 / f52"),
]

LEGEND = [
    ("实线", "流程方向；箭头指向下一步。"),
    ("虚线", "补信息后回到上一步——不是放行，是重做一遍。"),
    ("菱形", "人的判断点：AI 给依据，判断权在人。"),
    ("紫色标记", "AI 起草 / 设计：产出是草稿，必须有人签字才生效。"),
    ("蓝框", "签字节点：这一步没有这个人，结论作废。"),
]


def esc(text: str) -> str:
    return html.escape(str(text), quote=True)


def heights_for(nodes):
    return [104 if n["kind"] == "decision" else 96 for n in nodes]


def build() -> str:
    parts = []
    add = parts.append
    heights = heights_for(NODES)
    top = 150
    total_main = sum(heights) + GAP * (len(NODES) - 1)
    H = top + total_main + GAP + 560

    add(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="-apple-system,BlinkMacSystemFont,\'PingFang SC\',\'Helvetica Neue\',Arial,sans-serif">')
    add('<defs><style>')
    add('''
      .t { fill:#1f2937; }
      .h1 { font-size:20px; font-weight:700; fill:#0f172a; }
      .h2 { font-size:12.5px; fill:#64748b; }
      .note { font-size:11.5px; fill:#475569; }
      .title { font-size:13.5px; font-weight:600; }
      .sub { font-size:11.5px; fill:#4b5563; }
      .dno { font-size:10.5px; fill:#a16207; font-weight:600; }
      .dtitle { font-size:13px; font-weight:600; fill:#713f12; }
      .dsub { font-size:11px; fill:#92400e; }
      .edge { font-size:11px; fill:#6b7280; }
      .chip { font-size:10px; font-weight:600; }
      .leg { font-size:11.5px; fill:#4b5563; }
      .card { font-size:12.5px; font-weight:600; fill:#111827; }
      .card2 { font-size:11px; fill:#6b7280; }
      .foot { font-size:11px; fill:#6b7280; }
    </style>
    <marker id="ar" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M0 0 L10 5 L0 10 z" fill="#94a3b8"/>
    </marker>
    <marker id="ard" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M0 0 L10 5 L0 10 z" fill="#cbd5e1"/>
    </marker>
  </defs>
  <rect x="0" y="0" width="100%" height="100%" fill="#ffffff"/>''')

    add('<text class="t h1" x="40" y="52">业务需求发现与验证 · 谁在判断，AI 在哪一步出手</text>')
    add('<text class="t h2" x="40" y="78">从六个人各说一段，到敢在真实班次上试一次：19 步 · 6 个人判断点 · 4 个签字节点</text>')
    add(f'<rect x="40" y="94" width="{W - 80}" height="34" rx="8" fill="#f8fafc" stroke="#e2e8f0"/>')
    add(f'<text class="t note" x="56" y="116">{esc(HEAD_NOTE)}</text>')

    y = top
    for i, n in enumerate(NODES):
        h = heights[i]
        if n["kind"] == "decision":
            cy = y + h // 2
            pts = f"{MAIN_CX},{y} {MAIN_X + MAIN_W - 25},{cy} {MAIN_CX},{y + h} {MAIN_X + 25},{cy}"
            add(f'<polygon points="{pts}" fill="#fefce8" stroke="#f0d9a8" stroke-width="1.4"/>')
            add(f'<text class="t dno" x="{MAIN_CX}" y="{cy - 30}" text-anchor="middle">{n["no"]}</text>')
            add(f'<text class="t dtitle" x="{MAIN_CX}" y="{cy - 2}" text-anchor="middle">{esc(n["title"])}</text>')
            if n.get("sub"):
                add(f'<text class="t dsub" x="{MAIN_CX}" y="{cy + 17}" text-anchor="middle">{esc(n["sub"])}</text>')
        else:
            fill, stroke = ("#f5f7ff", "#a5b4fc") if n["kind"] == "sign" else ("#f1f5f9", "#cbd5e1")
            add(f'<rect x="{MAIN_X}" y="{y}" width="{MAIN_W}" height="{h}" rx="12" fill="{fill}" stroke="{stroke}" stroke-width="1.3"/>')
            add(f'<text class="t title" x="{MAIN_X + 26}" y="{y + 32}">{esc(n["no"])}　{esc(n["title"])}</text>')
            for k, line in enumerate(n.get("sub", [])[:2]):
                add(f'<text class="t sub" x="{MAIN_X + 26}" y="{y + 54 + k * 19}">{esc(line)}</text>')

            if n["kind"] == "sign":
                add(f'<rect x="{MAIN_X + MAIN_W - 116}" y="{y + 12}" width="104" height="20" rx="10" fill="#eef2ff" stroke="#c7d2fe"/>')
                add(f'<text class="t chip" x="{MAIN_X + MAIN_W - 64}" y="{y + 26}" text-anchor="middle" fill="#4338ca">签字 · {esc(n["who"])}</text>')
            elif n.get("chip"):
                label, (cf, cs, ct) = _chip(n["chip"], n.get("chip_label"))
                add(f'<rect x="{MAIN_X + MAIN_W - 96}" y="{y + 12}" width="84" height="20" rx="10" fill="{cf}" stroke="{cs}"/>')
                add(f'<text class="t chip" x="{MAIN_X + MAIN_W - 54}" y="{y + 26}" text-anchor="middle" fill="{ct}">{esc(label)}</text>')

        if n.get("branch"):
            b = n["branch"]
            by = y + (h - 96) // 2
            tone = {"bad": ("#fef2f2", "#fecaca", "#b91c1c"),
                    "warn": ("#fffbeb", "#fde68a", "#a16207"),
                    "ok": ("#f0fdf4", "#bbf7d0", "#15803d")}[b["tone"]]
            add(f'<rect x="{BR_X}" y="{by}" width="{BR_W}" height="96" rx="12" fill="{tone[0]}" stroke="{tone[1]}" stroke-width="1.3"/>')
            add(f'<text class="t title" x="{BR_X + 20}" y="{by + 30}" fill="{tone[2]}">{esc(b["title"])}</text>')
            for k, line in enumerate(b["sub"][:3]):
                add(f'<text class="t sub" x="{BR_X + 20}" y="{by + 51 + k * 16.5}">{esc(line)}</text>')
            cy_main = y + h // 2
            add(f'<line x1="{MAIN_X + MAIN_W - 25}" y1="{cy_main}" x2="{BR_X - 8}" y2="{cy_main}" stroke="{LINE}" stroke-width="1.3" marker-end="url(#ar)"/>')
            add(f'<text class="t edge" x="{(MAIN_X + MAIN_W - 25 + BR_X) / 2}" y="{cy_main - 7}" text-anchor="middle">否</text>')

            if b.get("loop"):
                target = NODES[i - 1]
                ty = target["_y"] + heights[i - 1] // 2
                add(f'<path d="M {BR_X + 20} {by + 96} L {GUTTER} {by + 96} L {GUTTER} {ty} L {MAIN_X + MAIN_W + 6} {ty}" '
                    'fill="none" stroke="#cbd5e1" stroke-width="1.3" stroke-dasharray="5 5" marker-end="url(#ard)"/>')
                add(f'<text class="t edge" x="{BR_X}" y="{by + 118}" fill="#94a3b8">{esc(b["loop"])}</text>')

        n["_y"] = y
        if i + 1 < len(NODES):
            add(f'<line x1="{MAIN_CX}" y1="{y + h}" x2="{MAIN_CX}" y2="{y + h + GAP - 9}" stroke="{LINE}" stroke-width="1.3" marker-end="url(#ar)"/>')
            if n["kind"] == "decision":
                add(f'<text class="t edge" x="{MAIN_CX + 10}" y="{y + h + 22}">是</text>')
        y += h + GAP

    y_roles = y + 16
    add(f'<text class="t h1" x="40" y="{y_roles + 8}" font-size="15">六位受访者在发现流程里的位置</text>')
    cy0 = y_roles + 30
    for idx, (name, role, duty, ref) in enumerate(ROLES):
        col, row = idx % 3, idx // 3
        x = 40 + col * 320
        yy = cy0 + row * 96
        add(f'<rect x="{x}" y="{yy}" width="300" height="82" rx="10" fill="#f8fafc" stroke="#e2e8f0"/>')
        add(f'<text class="t card" x="{x + 18}" y="{yy + 26}">{esc(name)}<tspan font-weight="400" fill="#6b7280">　{esc(role)}</tspan></text>')
        add(f'<text class="t card2" x="{x + 18}" y="{yy + 50}">{esc(duty)}</text>')
        add(f'<text class="t card2" x="{x + 18}" y="{yy + 68}" fill="#9ca3af">{esc(ref)}</text>')

    y_leg = cy0 + 2 * 96 + 14
    add(f'<text class="t h1" x="40" y="{y_leg + 8}" font-size="15">读图说明</text>')
    for k, (key, val) in enumerate(LEGEND):
        add(f'<text class="t leg" x="56" y="{y_leg + 34 + k * 24}"><tspan font-weight="600" fill="#111827">{esc(key)}</tspan>　{esc(val)}</text>')

    foot = [
        "AI 的产出全是草稿：候选问题、假设、校验设计；判定与签字不在它的权限里。",
        "每个菱形都允许“否”，且“否”有明确去处——回补证、降级、退假设、收窄范围，没有一条是硬着头皮往下走。",
        "签字节点的含义是责任：字不在，结论不生效（复核）或整批不放行（门禁）。",
        "证据编号对应访谈报告 f00–f55 与 docs/design.md、docs/gates.md；本图由 scripts/make_discovery_flow.py 生成。",
        "报价与范围：发现阶段的结论决定试点范围，试点结果决定下一轮报价（见 QUOTATION.md）。",
    ]
    for k, line in enumerate(foot):
        add(f'<text class="t foot" x="40" y="{y_leg + 34 + len(LEGEND) * 24 + 16 + k * 19}">{esc(line)}</text>')

    add("</svg>")
    return "\n".join(parts)


def main() -> int:
    svg = build()
    out = ROOT / "docs" / "discovery-flow.svg"
    out.write_text(svg, encoding="utf-8")
    print(f"wrote {out}（{len(svg.encode('utf-8'))} 字节）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
