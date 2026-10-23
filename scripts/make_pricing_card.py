"""生成 docs/pricing.svg：一页看清"报价怎么定"。

为什么单独画一张：报价单是长文，谈判时没人翻长文。
这张图只回答三个问题——六种计价里为什么选这一种、三档各卖什么、哪些钱不赚。

用法：`python3 scripts/make_pricing_card.py`
"""

from __future__ import annotations

import html
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

W = 1040
M = 40
CONTENT = W - M * 2

INK = "#0f172a"
MUTED = "#64748b"

# 列宽（合计 = CONTENT）
COLS = [196, 246, 306, 212]

ROWS = [
    ("人天 / T&M", "你的时间", "变更失控吃掉毛利；AI 时代最容易被比价", ("不推荐", "no")),
    ("功能点 / 规模", "可枚举的功能范围", "功能点认定有争议，需要权威标准", ("不适用", "off")),
    ("固定总价 / 整包", "一个确定的结果", "范围蔓延直接吃掉毛利", ("只用于闭口包", "mid")),
    ("订阅 / 年费", "持续可用的能力", "客户不续费 = 收入归零", ("二期再说", "off")),
    ("用量计费", "用得越多付越多", "客户成本不可控，范围风险归我们", ("备选 2,400/批", "mid")),
    ("效果付费 / 分成", "可验证的业务结果", "基线不稳、归因扯皮、客户控制变量", ("只对工时分成", "mid")),
    ("基础费 + 效果浮动", "交付能力 + 结果红利", "公式必须事先写死，否则事后全靠谈", ("推荐", "yes")),
]

BADGE = {
    "no": ("#fef2f2", "#fecaca", "#b91c1c"),
    "off": ("#f1f5f9", "#e2e8f0", "#64748b"),
    "mid": ("#fffbeb", "#fde68a", "#a16207"),
    "yes": ("#eef2ff", "#c7d2fe", "#3730a3"),
}

PLANS = [
    ("诊断包", "¥68,000", ["W0 一项：访谈复盘、事实台账", "需求假设 + 门禁草案", "结论：值不值得做"]),
    ("试点包 ★", "¥198,000", ["W0–W4 全部，33 人天", "含金标回放与复盘", "浮动另计 ≤ ¥60,000"]),
    ("扩展包", "¥120,000 起", ["换业务域复用框架", "门禁与模板直接沿用", "18 人天起"]),
]


def esc(text: str) -> str:
    return html.escape(str(text), quote=True)


def build() -> str:
    top = 150
    row_h = 58
    head_h = 44
    table_h = head_h + row_h * len(ROWS)
    y_plans = top + table_h + 46
    plan_h = 118
    y_formula = y_plans + plan_h + 30
    y_bad = y_formula + 60 + 46
    H = y_bad + 96

    parts = []
    add = parts.append
    add(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
        'font-family="-apple-system,BlinkMacSystemFont,\'PingFang SC\',\'Helvetica Neue\',Arial,sans-serif">')
    add('<defs><style>'
        f'.ink{{fill:{INK}}}.muted{{fill:{MUTED}}}'
        '.eyebrow{font-size:12px;font-weight:700;letter-spacing:.5px;fill:#2563eb}'
        '.h1{font-size:30px;font-weight:700;fill:#0f172a}'
        '.h2{font-size:13.5px;fill:#475569}'
        '.th{font-size:11.5px;font-weight:700;fill:#1e293b}'
        '.cell{font-size:11.5px;fill:#334155}'
        '.cellb{font-size:11.5px;font-weight:600;fill:#0f172a}'
        '.badge{font-size:11px;font-weight:700}'
        '.plan{font-size:12px;font-weight:700;fill:#0f172a}'
        '.price{font-size:22px;font-weight:700;fill:#1d4ed8}'
        '.small{font-size:11px;fill:#475569}'
        '.foot{font-size:11px;fill:#94a3b8}'
        '</style></defs>'
        '<rect x="0" y="0" width="100%" height="100%" fill="#ffffff"/>')

    # 外框卡片
    add(f'<rect x="20" y="20" width="{W - 40}" height="{H - 40}" rx="16" fill="#ffffff" stroke="#e2e8f0" stroke-width="1.5"/>')

    add(f'<text class="eyebrow" x="{M}" y="62">报价 · 计价模式</text>')
    add(f'<text class="h1" x="{M}" y="102">六种计价方式，我们只用一种</text>')
    add(f'<text class="h2" x="{M}" y="128">判断标准只有一条：客户能不能用这个价，算出自己省了多少。算不出来的，在 AI 时代一定被压价。</text>')

    # 表头
    x = M
    add(f'<rect x="{M}" y="{top}" width="{CONTENT}" height="{head_h}" rx="8" fill="#f1f5f9"/>')
    for i, (label, w) in enumerate(zip(["计价方式", "客户买的是什么", "最大的坑", "本项目判断"], COLS)):
        add(f'<text class="th" x="{x + 14}" y="{top + 28}">{label}</text>')
        x += w

    # 行
    y = top + head_h
    for ri, (name, buys, pit, (judge, tone)) in enumerate(ROWS):
        if ri % 2 == 1:
            add(f'<rect x="{M}" y="{y}" width="{CONTENT}" height="{row_h}" fill="#fafbfc"/>')
        if tone == "yes":
            add(f'<rect x="{M}" y="{y}" width="{CONTENT}" height="{row_h}" fill="#f5f7ff"/>')
            add(f'<rect x="{M}" y="{y}" width="4" height="{row_h}" fill="#6366f1"/>')
        add(f'<line x1="{M}" y1="{y + row_h}" x2="{M + CONTENT}" y2="{y + row_h}" stroke="#e8edf3"/>')
        add(f'<text class="cellb" x="{M + 14}" y="{y + 35}">{esc(name)}</text>')
        add(f'<text class="cell" x="{M + COLS[0] + 14}" y="{y + 35}">{esc(buys)}</text>')
        add(f'<text class="cell" x="{M + COLS[0] + COLS[1] + 14}" y="{y + 35}">{esc(pit)}</text>')
        fill, stroke, ink = BADGE[tone]
        bx = M + COLS[0] + COLS[1] + COLS[2] + 14
        add(f'<rect x="{bx}" y="{y + 17}" width="150" height="24" rx="12" fill="{fill}" stroke="{stroke}"/>')
        add(f'<text class="badge" x="{bx + 75}" y="{y + 33}" text-anchor="middle" fill="{ink}">{esc(judge)}</text>')
        y += row_h

    # 三档
    add(f'<text class="th" x="{M}" y="{y_plans - 12}">三档怎么买</text>')
    gap = 16
    card_w = (CONTENT - gap * 2) // 3
    for i, (title, price, lines) in enumerate(PLANS):
        px = M + i * (card_w + gap)
        stroke = "#c7d2fe" if i == 1 else "#e2e8f0"
        fill = "#f8faff" if i == 1 else "#ffffff"
        add(f'<rect x="{px}" y="{y_plans}" width="{card_w}" height="{plan_h}" rx="12" fill="{fill}" stroke="{stroke}" stroke-width="1.3"/>')
        add(f'<text class="plan" x="{px + 18}" y="{y_plans + 26}">{esc(title)}</text>')
        add(f'<text class="price" x="{px + 18}" y="{y_plans + 58}">{esc(price)}</text>')
        for k, line in enumerate(lines[:3]):
            add(f'<text class="small" x="{px + 18}" y="{y_plans + 82 + k * 17}">{esc(line)}</text>')

    # 浮动公式
    add(f'<rect x="{M}" y="{y_formula}" width="{CONTENT}" height="60" rx="10" fill="#f0fdf4" stroke="#bbf7d0"/>')
    add(f'<text class="th" x="{M + 18}" y="{y_formula + 25}" fill="#15803d">效果浮动（只对核对工时）</text>')
    add(f'<text class="small" x="{M + 18}" y="{y_formula + 45}">'
        '浮动 = (H0 − H1) × 年批次 × ¥180 × 20%，上限 ¥60,000；H1 ≥ H0 时为 0，不倒扣</text>')
    add(f'<text class="small" x="{M + CONTENT - 18}" y="{y_formula + 45}" text-anchor="end" fill="#15803d">'
        '算例：(18−9)×40×180×20% = ¥12,960</text>')

    # 不赚的钱
    chips = ["不写回任何系统", "不发外部消息", "不自动指派医疗/安保", "不判定“交接完成”"]
    cx = M
    add(f'<text class="th" x="{M}" y="{y_bad - 14}">这些钱不赚（写进合同）</text>')
    for chip in chips:
        w = 26 + len(chip) * 12
        add(f'<rect x="{cx}" y="{y_bad}" width="{w}" height="28" rx="14" fill="#fff7ed" stroke="#fed7aa"/>')
        add(f'<text class="small" x="{cx + w / 2}" y="{y_bad + 18}" text-anchor="middle" fill="#c2410c">{esc(chip)}</text>')
        cx += w + 12

    add(f'<text class="foot" x="{M}" y="{H - 44}">'
        '单位：人民币。数字为演练示例，不代表真实商务承诺；完整条款见 docs/04-quotation.md。'
        '</text>')
    add(f'<text class="foot" x="{M}" y="{H - 26}">'
        '本图由 scripts/make_pricing_card.py 生成，改价格请改脚本，不要手改 SVG。'
        '</text>')

    add("</svg>")
    return "\n".join(parts)


def main() -> int:
    svg = build()
    out = ROOT / "docs" / "pricing.svg"
    out.write_text(svg, encoding="utf-8")
    print(f"wrote {out}（{len(svg.encode('utf-8'))} 字节）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
