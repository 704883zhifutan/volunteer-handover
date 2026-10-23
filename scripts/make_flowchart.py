"""生成 docs/flowchart.svg：本项目的完整流程（含人工判断点与签字节点）。

为什么用脚本画而不是手写 SVG：
- 节点会增删（W2 只开 3 个环节，W4 可能加/减校验），手写坐标一改就全乱；
- 中文文字长度一变就要重排，脚本按块高自动往下推，改流程只改 NODES。

用法：`python3 scripts/make_flowchart.py`
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
GUTTER = 680  # 虚线回退通道，落在主列右侧的空隙里

INK = "#1f2937"
LINE = "#94a3b8"

# 主链路。kind: process / decision / sign。
# decision 的 branch 是"否"的出口；loop 表示"补信息后回到上一步重来"（虚线，不是放行）。
NODES = [
    dict(
        no="01", kind="process",
        title="数据导出（只读脱敏）",
        sub=["三套工具各自导出结构化 CSV：排班、签到、交接", "没有写回通道，没有外发通道（f30 / f32）"],
    ),
    dict(
        no="02", kind="decision",
        title="表头契约是否齐全",
        sub="必需列缺一列即停",
        branch=dict(
            tone="bad", title="阻断：本次不出结论",
            sub=["退出码 2，缺哪一列写清楚", "缺列造出的“缺项”比没有更危险"],
            loop="补齐列后重跑",
        ),
    ),
    dict(
        no="03", kind="process",
        title="只读加载与快照",
        sub=["记 sha256、行数、读取时间、失败原因", "读不到就标 unavailable：不重试、不补值（f35）"],
    ),
    dict(
        no="04", kind="decision",
        title="文件是否都读得到",
        sub="读到 0 行 ≠ 没读到",
        branch=dict(
            tone="warn", title="跳过相关校验并明说",
            sub=["“这不等于没有缺岗”——不许悄悄少一段", "其余校验照跑，C8 记一条读取失败"],
        ),
    ),
    dict(
        no="05", kind="process",
        title="九条确定性校验 C1–C9",
        sub=["C1 缺岗 · C2 占位 · C3 双时间 · C4 版本 · C5 交接", "C6 三值 · C7 编号 · C8 失败标记 · C9 能力边界"],
    ),
    dict(
        no="06", kind="process",
        title="生成两件产物",
        sub=["一页缺项清单 + 交接责任清单", "每条都带 文件#L行号，能一跳回原始行"],
    ),
    dict(
        no="07", kind="sign", who="L1",
        title="当班人核对原始行",
        sub=["现场事实只有现场知道：点位、顶班、临时调人", "工具只提示，不覆盖原值（f14 / f22）"],
    ),
    dict(
        no="08", kind="decision",
        title="这条能不能判定",
        sub="依据够不够",
        branch=dict(
            tone="warn", title="转人工队列，标未复核",
            sub=["不默认通过，也不替人补事实（f44）", "队列无人值守 = 停止条件之一"],
            loop="补到事实后重新核对",
        ),
    ),
    dict(
        no="09", kind="sign", who="复核人",
        title="复核签字并回填",
        sub=["review.csv：结论 + 复核人 + 时间 + 备注", "缺复核人或缺时间 → 这条不生效（f45）"],
    ),
    dict(
        no="10", kind="decision",
        title="是否涉及“交接完成”",
        sub="G3 未定义",
        branch_when="yes",
        branch=dict(
            tone="warn", title="只出信号，不出结论",
            sub=["未签收 / 接收人缺失 / 未结项无责任人", "清单头部留白“完成定义待确认”"],
        ),
    ),
    dict(
        no="11", kind="sign", who="L2",
        title="业务负责人确认生效",
        sub=["顾明岚：范围与试点口径（f04）", "叫停权在傅景：假状态、越界指派、确认被绕过"],
    ),
    dict(
        no="12", kind="process",
        title="指标复算",
        sub=["误报率（分母=已复核）· 确认率 · 复核滞后", "确认率不足 100% 时，比率只覆盖已复核部分"],
    ),
    dict(
        no="13", kind="decision",
        title="确认完整率是否 100%",
        sub="试点硬门",
        branch=dict(
            tone="bad", title="不得进现场结论",
            sub=["未确认的条目在现场等于没人负责", "宁可少发一条，不许没主就发", "回路：回到 09 补齐复核"],
        ),
    ),
    dict(
        no="14", kind="process",
        title="金标回放（W3）",
        sub=["50 次调班，双人各标一遍，分歧由傅景裁", "scripts/score.py 出召回率与 G1 判定"],
    ),
    dict(
        no="15", kind="decision",
        title="召回 100% 且无未覆盖",
        sub="G1 的唯一判据",
        branch=dict(
            tone="bad", title="G1 不能关",
            sub=["召回没有分母 = 无法证伪", "退出码 3，属性是“还关不掉”", "回路：回到 14 补标注再比"],
        ),
    ),
    dict(
        no="16", kind="sign", who="三方",
        title="三门禁签字",
        sub=["G1 傅景+秦芮 · G2 傅景+唐映秋+林亦舟", "G3 顾明岚+唐映秋，叶书确认客户侧"],
    ),
    dict(
        no="17", kind="process",
        title="试点放行（W2）",
        sub=["只开交接、签到、排班三个环节", "其余保持人肉，不加流程"],
    ),
    dict(
        no="18", kind="process",
        title="复盘决策门（W4）",
        sub=["扩范围 / 收窄 / 停止，按工时与误报率定", "对外口径由叶书确认，系统不代发（f52）"],
    ),
]

ROLES = [
    ("顾明岚", "业务负责人", "定范围、确认生效、拍试点口径", "（f02 / f04）"),
    ("林亦舟", "赛事现场协调员", "现场核对与异常证实，顶班调人", "（f10–f14）"),
    ("唐映秋", "项目流程协调员", "回填复核、交接与资料责任", "（f20 / f25）"),
    ("秦芮", "数字化工程师", "只读导出、快照与编号规则", "（f30 / f31）"),
    ("傅景", "审核与质量负责人", "金标标注、门禁签字、叫停权", "（f41 / f44）"),
    ("叶书", "客户协同代表", "对外口径确认，不自动承诺", "（f50 / f52）"),
]

LEGEND = [
    ("实线", "顺序与交接方向；箭头指向下一步。"),
    ("虚线", "补信息后返回——不是放行，是回到上一处再核一遍。"),
    ("菱形", "人工判断点，不是系统自动校验；判定权在人，工具只给依据。"),
    ("蓝色框", "需要签字的节点：复核人 / 业务负责人 / 三方门禁。"),
]

HEAD_NOTE = (
    "范围：导出 → 表头契约 → 校验 → 清单 → 复核签字 → 确认 → 指标 → 金标 → 门禁 → 放行。"
    "写回、外发、自动指派这三类能力在本流程里不存在。"
)


def esc(text: str) -> str:
    return html.escape(text, quote=False)


def build() -> str:
    heights = [104 if n["kind"] == "decision" else 96 for n in NODES]
    top = 150
    total_main = sum(heights) + GAP * (len(NODES) - 1)
    H = top + total_main + GAP + 530

    parts: list[str] = []
    add = parts.append

    add(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
        'role="img" aria-label="志愿者班次交接的完整流程：含人工判断点、复核签字与三门禁签字">')
    add('''<defs>
    <style>
      .t { font-family: ui-sans-serif, -apple-system, "PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC", sans-serif; }
      .h1 { font-size:21px; font-weight:600; fill:#111827; }
      .h2 { font-size:13px; fill:#6b7280; }
      .note { font-size:11.5px; fill:#4b5563; }
      .title { font-size:13.5px; font-weight:600; fill:#1f2937; }
      .sub { font-size:11.5px; fill:#6b7280; }
      .dtitle { font-size:12.5px; font-weight:600; fill:#78350f; }
      .dsub { font-size:11px; fill:#a16207; }
      .dno { font-size:10.5px; font-weight:600; fill:#b45309; }
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

    add('<text class="t h1" x="40" y="52">赛事志愿者排班与交接 · 全流程与人工判断点</text>')
    add('<text class="t h2" x="40" y="78">从只读导出到试点放行：18 步 · 6 个人工判断点 · 4 个签字节点</text>')
    add(f'<rect x="40" y="94" width="{W - 80}" height="34" rx="8" fill="#f8fafc" stroke="#e2e8f0"/>')
    add(f'<text class="t note" x="56" y="116">{esc(HEAD_NOTE)}</text>')

    y = top
    prev_center_bottom = None
    for i, n in enumerate(NODES):
        h = heights[i]
        n["_y"] = y
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
            if n.get("who"):
                add(f'<rect x="{MAIN_X + MAIN_W - 96}" y="{y + 12}" width="84" height="20" rx="10" fill="#eef2ff" stroke="#c7d2fe"/>')
                add(f'<text class="t chip" x="{MAIN_X + MAIN_W - 54}" y="{y + 26}" text-anchor="middle" fill="#4338ca">签字 · {esc(n["who"])}</text>')

        if n.get("branch"):
            b = n["branch"]
            by = y + (h - 96) // 2
            tone = {"bad": ("#fef2f2", "#fecaca", "#b91c1c"), "warn": ("#fffbeb", "#fde68a", "#a16207")}[b["tone"]]
            add(f'<rect x="{BR_X}" y="{by}" width="{BR_W}" height="96" rx="12" fill="{tone[0]}" stroke="{tone[1]}" stroke-width="1.3"/>')
            add(f'<text class="t title" x="{BR_X + 20}" y="{by + 30}" fill="{tone[2]}">{esc(b["title"])}</text>')
            for k, line in enumerate(b["sub"][:3]):
                add(f'<text class="t sub" x="{BR_X + 20}" y="{by + 51 + k * 16.5}">{esc(line)}</text>')
            cy_main = y + h // 2
            add(f'<line x1="{MAIN_X + MAIN_W - 25}" y1="{cy_main}" x2="{BR_X - 8}" y2="{cy_main}" stroke="{LINE}" stroke-width="1.3" marker-end="url(#ar)"/>')
            when = n.get("branch_when", "no")
            add(f'<text class="t edge" x="{(MAIN_X + MAIN_W - 25 + BR_X) / 2}" y="{cy_main - 7}" text-anchor="middle">{"是" if when == "yes" else "否"}</text>')

            if b.get("loop"):
                want = n.get("loop_to")
                idx_t = next((k for k, m in enumerate(NODES) if m["no"] == want), i - 1) if want else i - 1
                target = NODES[idx_t]
                ty = target["_y"] + heights[idx_t] // 2
                add(f'<path d="M {BR_X + 20} {by + 96} L {GUTTER} {by + 96} L {GUTTER} {ty} L {MAIN_X + MAIN_W + 6} {ty}" '
                    'fill="none" stroke="#cbd5e1" stroke-width="1.3" stroke-dasharray="5 5" marker-end="url(#ard)"/>')
                add(f'<text class="t edge" x="{BR_X}" y="{by + 118}" fill="#94a3b8">{esc(b["loop"])}</text>')

        if i + 1 < len(NODES):
            add(f'<line x1="{MAIN_CX}" y1="{y + h}" x2="{MAIN_CX}" y2="{y + h + GAP - 9}" stroke="{LINE}" stroke-width="1.3" marker-end="url(#ar)"/>')
            if n["kind"] == "decision":
                add(f'<text class="t edge" x="{MAIN_CX + 10}" y="{y + h + 22}">{"否" if n.get("branch_when") == "yes" else "是"}</text>')
        y += h + GAP

    # 角色卡
    y_roles = y + 16
    add(f'<text class="t h1" x="40" y="{y_roles + 8}" font-size="15">六位参与者在流程里的位置</text>')
    cy0 = y_roles + 30
    for idx, (name, role, duty, ref) in enumerate(ROLES):
        col, row = idx % 3, idx // 3
        x = 40 + col * 320
        yy = cy0 + row * 96
        add(f'<rect x="{x}" y="{yy}" width="300" height="82" rx="10" fill="#f8fafc" stroke="#e2e8f0"/>')
        add(f'<text class="t card" x="{x + 18}" y="{yy + 26}">{esc(name)}<tspan font-weight="400" fill="#6b7280">　{esc(role)}</tspan></text>')
        add(f'<text class="t card2" x="{x + 18}" y="{yy + 50}">{esc(duty)}</text>')
        add(f'<text class="t card2" x="{x + 18}" y="{yy + 68}" fill="#9ca3af">{esc(ref)}</text>')

    # 读图说明
    y_leg = cy0 + 2 * 96 + 14
    add(f'<text class="t h1" x="40" y="{y_leg + 8}" font-size="15">读图说明</text>')
    for k, (key, val) in enumerate(LEGEND):
        add(f'<text class="t leg" x="56" y="{y_leg + 34 + k * 24}"><tspan font-weight="600" fill="#111827">{esc(key)}</tspan>　{esc(val)}</text>')
    foot = [
        "编号是流程步序，不是系统自动执行顺序：菱形处的判断权始终在人，工具只给依据。",
        "签字节点的含义是“这个人对这一步负责”，不是走形式：缺签名时该条不生效（复核），或缺一签就整批不出包（门禁）。",
        "证据编号对应访谈报告 f00–f55 与 docs/design.md 的 C1–C9、docs/gates.md 的 G1–G3。",
        "本图由 scripts/make_flowchart.py 生成；改流程请改脚本里的 NODES，不要手改 SVG。",
    ]
    for k, line in enumerate(foot):
        add(f'<text class="t foot" x="40" y="{y_leg + 34 + len(LEGEND) * 24 + 16 + k * 19}">{esc(line)}</text>')

    add("</svg>")
    return "\n".join(parts)


def main() -> int:
    svg = build()
    out = ROOT / "docs" / "flowchart.svg"
    out.write_text(svg, encoding="utf-8")
    print(f"wrote {out}（{len(svg)} 字节）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
