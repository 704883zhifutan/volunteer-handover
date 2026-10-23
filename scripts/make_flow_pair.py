"""生成一对流程图：现状（as-is）与数智化转型后（to-be）。

为什么成对生成：老板看现状图会问"那改了以后呢"，看转型图会问"现在到底多糟"。
两张图共用同一套环节编号与排版，才能一眼对上——哪个环节被工具接管了、哪个环节仍然靠人。

用法：`python3 scripts/make_flow_pair.py` → docs/03-flow-as-is.svg / docs/03-flow-to-be.svg
"""

from __future__ import annotations

import html
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

W = 1000
LEFT_X = 60
LEFT_W = 470
RIGHT_X = 560
RIGHT_W = 380
GAP = 34
TOP = 150

INK = "#1f2937"
LINE = "#94a3b8"

AS_IS = [
    dict(no="01", title="岗位需求与结构", who="业务负责人 · 顾明岚",
         sub=["凭经验估点位与人头，缺口事后才知道", "医疗/安保岗位也要来，但不在试点内"],
         note=("错在：没有需求底稿", ["点位与人头靠口口相传，换人就重来", "代价：中高"]), tone="warn"),
    dict(no="02", title="人员匹配与排班", who="流程协调员 + 现场协调员",
         sub=["群消息里口头调人，排班表事后补", "同一人可能被安排到两个点位"],
         note=("错在：替补没有唯一登记", ["谁替谁、替到哪，只在聊天记录里", "代价：最高"]), tone="bad"),
    dict(no="03", title="班次确认与发布", who="流程协调员 · 唐映秋",
         sub=["版本靠文件名区分，旧版覆盖新版", "确认状态没有地方落"],
         note=("错在：版本没有有效期概念", ["“最新版”靠人记，作废不写原因", "代价：中高"]), tone="warn"),
    dict(no="04", title="现场签到与到岗", who="志愿者 · 当班人",
         sub=["签到靠纸质或群消息接龙", "缺岗本身不产生任何记录"],
         note=("错在：缺岗是“没有数据”", ["没人签到＝没人发现", "代价：高"]), tone="bad"),
    dict(no="05", title="现场交接", who="交班人 → 接班人",
         sub=["口头交接待办事项，截止时间说不清", "未结项随人走，不留痕"],
         note=("错在：责任不落地", ["投诉时才发现“以为交过了”", "代价：最高"]), tone="bad"),
    dict(no="06", title="异常补录", who="全员",
         sub=["先群里说，后补表；回填时间当发生时间", "补录格式各不相同"],
         note=("错在：时间只有一份", ["事后分不清“几点发生”和“几点补”", "代价：中"]), tone="warn"),
    dict(no="07", title="客户协同与对外", who="客户协同代表 · 叶书",
         sub=["对外口径靠个人记忆", "容易承诺现场做不到的事"],
         note=("错在：口径无版本", ["同一件事两种说法，客户先信哪一种", "代价：最高"]), tone="bad"),
]

TO_BE = [
    dict(no="01", title="岗位需求与结构", who="业务负责人（人定）",
         sub=["范围先划死：医疗/安保不进试点、不自动指派", "工具只校验范围，不替人做编制"],
         note=("工具：校验范围", ["配置白名单，越界直接阻断", "仍然：人定编制"]), tone="info"),
    dict(no="02", title="人员匹配与排班", who="流程协调员 + 现场协调员",
         sub=["同人同时段多点位 → C2 提示“疑似重复占位”", "顶班关系登记到人，谁替谁可查"],
         note=("工具：C2 占位冲突", ["只提示，不自动改排班", "仍然：人决定怎么调"]), tone="tool"),
    dict(no="03", title="班次确认与发布", who="流程协调员 · 唐映秋",
         sub=["版本有效期 + 确认状态双条件；作废保留原因", "过期版本不得覆盖已确认新版"],
         note=("工具：C4 版本有效性", ["“最新”由字段判定，不看文件名", "仍然：人确认发布"]), tone="tool"),
    dict(no="04", title="现场签到与到岗", who="当班人（L1）",
         sub=["排班与签到交叉比对：缺岗、点位/人员不一致", "签到有、排班无 → 计划外到岗（顶班）"],
         note=("工具：C1 交叉比对", ["每条带 文件#行号", "读到 0 行 ≠ 没读到：跳过要说清"]), tone="tool"),
    dict(no="05", title="现场交接", who="交班人 → 接班人",
         sub=["交接责任清单：版本 / 未结项 / 截止 / 责任人", "未签收、同一人交接、逾期未结 全部标出"],
         note=("工具：C5 交接清单", ["不判定“完成”（G3 未定义）", "只给可核对的信号"]), tone="tool"),
    dict(no="06", title="当班核对与签字", who="L1 核对 → L2 确认",
         sub=["建议只提示，不覆盖原始值", "核对结论回填 review.csv，缺复核人即不生效"],
         note=("人：签字生效", ["工具无审批权，模型无审批权", "仍然：人负责"]), tone="sign"),
    dict(no="07", title="异常补录", who="全员",
         sub=["业务发生时间与系统接收时间分离", "疑似回填只标来源，不预设阈值"],
         note=("工具：C3 双时间", ["倒挂/回填可定位到行", "仍然：人确认是否合规"]), tone="tool"),
    dict(no="08", title="客户协同与对外", who="客户协同代表 · 叶书",
         sub=["系统不出对外消息、不自动承诺", "对外口径由叶书确认后才发"],
         note=("边界：不碰", ["代码里没有发送通道", "仍然：人对外"]), tone="stop"),
    dict(no="09", title="每日复盘", who="流程协调员",
         sub=["批次对比：新增 / 持续 / 消失", "消失不等于已解决，必须人确认"],
         note=("工具：批次对比", ["按「校验+类型+对象」比对", "仍然：人判断扩/收/停"]), tone="tool"),
]

TONE = {
    "bad": ("#fef2f2", "#fecaca", "#b91c1c"),
    "warn": ("#fffbeb", "#fde68a", "#a16207"),
    "info": ("#f8fafc", "#e2e8f0", "#334155"),
    "tool": ("#f5f3ff", "#ddd6fe", "#6d28d9"),
    "sign": ("#eef2ff", "#c7d2fe", "#3730a3"),
    "stop": ("#f0fdf4", "#bbf7d0", "#15803d"),
}


def esc(text: str) -> str:
    return html.escape(str(text), quote=True)


def build(nodes, title, subtitle, head_note, footer):
    h_node = 96
    total = len(nodes) * h_node + GAP * (len(nodes) - 1)
    H = TOP + total + 190

    parts = []
    add = parts.append
    add(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
        'font-family="-apple-system,BlinkMacSystemFont,\'PingFang SC\',\'Helvetica Neue\',Arial,sans-serif">')
    add('<defs><style>'
        '.h1{font-size:20px;font-weight:700;fill:#0f172a}'
        '.h2{font-size:12.5px;fill:#64748b}'
        '.note{font-size:11.5px;fill:#475569}'
        '.title{font-size:13.5px;font-weight:600;fill:#1f2937}'
        '.who{font-size:11px;fill:#6b7280}'
        '.sub{font-size:11.5px;fill:#4b5563}'
        '.nt{font-size:11.5px;font-weight:600}'
        '.ns{font-size:11px;fill:#4b5563}'
        '.foot{font-size:11px;fill:#6b7280}'
        '</style>'
        '<marker id="ar" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
        'orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 z" fill="#94a3b8"/></marker></defs>'
        '<rect x="0" y="0" width="100%" height="100%" fill="#ffffff"/>')

    add(f'<text class="h1" x="40" y="52">{esc(title)}</text>')
    add(f'<text class="h2" x="40" y="78">{esc(subtitle)}</text>')
    add(f'<rect x="40" y="94" width="{W - 80}" height="34" rx="8" fill="#f8fafc" stroke="#e2e8f0"/>')
    add(f'<text class="note" x="56" y="116">{esc(head_note)}</text>')

    y = TOP
    for i, n in enumerate(nodes):
        add(f'<rect x="{LEFT_X}" y="{y}" width="{LEFT_W}" height="{h_node}" rx="12" fill="#ffffff" stroke="#cbd5e1" stroke-width="1.3"/>')
        add(f'<text class="title" x="{LEFT_X + 22}" y="{y + 30}">{esc(n["no"])}　{esc(n["title"])}</text>')
        add(f'<text class="who" x="{LEFT_X + LEFT_W - 18}" y="{y + 30}" text-anchor="end">{esc(n["who"])}</text>')
        for k, line in enumerate(n["sub"][:2]):
            add(f'<text class="sub" x="{LEFT_X + 22}" y="{y + 54 + k * 19}">{esc(line)}</text>')

        fill, stroke, ink = TONE[n["tone"]]
        nt, nsub = n["note"]
        add(f'<rect x="{RIGHT_X}" y="{y}" width="{RIGHT_W}" height="{h_node}" rx="12" fill="{fill}" stroke="{stroke}" stroke-width="1.3"/>')
        add(f'<text class="nt" x="{RIGHT_X + 18}" y="{y + 30}" fill="{ink}">{esc(nt)}</text>')
        for k, line in enumerate(nsub[:2]):
            add(f'<text class="ns" x="{RIGHT_X + 18}" y="{y + 53 + k * 19}">{esc(line)}</text>')

        add(f'<line x1="{LEFT_X + LEFT_W + 6}" y1="{y + h_node // 2}" x2="{RIGHT_X - 8}" y2="{y + h_node // 2}" '
            'stroke="#cbd5e1" stroke-width="1.2" stroke-dasharray="4 4"/>')

        if i + 1 < len(nodes):
            add(f'<line x1="{LEFT_X + 40}" y1="{y + h_node}" x2="{LEFT_X + 40}" y2="{y + h_node + GAP - 9}" '
                'stroke="#94a3b8" stroke-width="1.3" marker-end="url(#ar)"/>')
        y += h_node + GAP

    fy = y + 14
    add(f'<rect x="40" y="{fy}" width="{W - 80}" height="{28 + 20 * len(footer)}" rx="10" fill="#f8fafc" stroke="#e2e8f0"/>')
    for k, line in enumerate(footer):
        add(f'<text class="foot" x="58" y="{fy + 24 + k * 20}">{esc(line)}</text>')

    add("</svg>")
    return "\n".join(parts)


def main() -> int:
    as_is = build(
        AS_IS,
        "现状：志愿者班次是怎么跑的，错在哪一步最贵",
        "7 个环节 · 全部靠人 · 信息散在群消息、排班表、文件库里",
        "范围：岗位需求 → 现场交接 → 客户协同。代价 = 后果 × 发现难度 × 频次。",
        [
            "信息载体：内部服务台 / 业务台账 / 文件库，三套工具之间没有统一编号（f30）。",
            "最贵的三步是「人员匹配」「现场交接」「客户协同」：错了当场看不出来，往往在投诉时才暴露。",
            "本图由 scripts/make_flow_pair.py 生成；改流程请改脚本里的 AS_IS / TO_BE。",
        ],
    )
    to_be = build(
        TO_BE,
        "转型后：同一套流程，工具只做核对，签字仍在人手里",
        "9 个环节 · 7 处只读信号 · 1 处签字生效 · 1 处明确不碰",
        "范围：同一批班次、同一个批次。工具只在“核对”这一步出手，不写回、不发消息、不指派。",
        [
            "工具做的：C1 交叉比对 · C2 占位冲突 · C3 双时间 · C4 版本 · C5 交接清单 · 批次对比——全部只读。",
            "人做的：定编制、定怎么调班、确认发布、现场核对（L1）、业务确认（L2）、对外口径。",
            "不碰的：写回任何系统、发外部消息、自动指派医疗/安保、判定“交接完成”（G3 未定义）。",
            "对照看：现状图里最贵的三步（02 匹配、05 交接、07 协同），转型图在这三处各有一个只读信号。",
        ],
    )
    out1 = ROOT / "docs" / "03-flow-as-is.svg"
    out2 = ROOT / "docs" / "03-flow-to-be.svg"
    out1.write_text(as_is, encoding="utf-8")
    out2.write_text(to_be, encoding="utf-8")
    print(f"wrote {out1.name} ({len(as_is.encode('utf-8'))} B), {out2.name} ({len(to_be.encode('utf-8'))} B)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
