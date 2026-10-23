"""产物 A：一页缺项清单。

设计要求来自访谈事实 f15：
"我需要一页缺项清单和对应志愿者班次的来源位置，不需要一份很长的泛化摘要。"

所以这里有三条硬约束：
1. 每条都必须有 locator，没有定位的条目视为无效输出。
2. 建议永远是文字，不带执行入口。
3. 超过一页上限时，输出警告而不是继续加页——一页装不下说明筛选规则错了。
"""

from __future__ import annotations

import csv
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

REVIEW_STATUSES = ("未复核", "已确认", "已驳回", "转人工队列")

DEFAULT_SUGGESTION = "仅提示，不执行；请当班人员核对原始记录后确认"


@dataclass
class Finding:
    code: str                 # 校验编号 C1–C9
    type: str                 # 异常类型
    subject: str              # 涉及对象（班次号 / 交接口 / 文件）
    detail: str               # 事实描述，不带推测
    source_locator: str       # 例：shifts.csv#L5
    occurred_at: str = ""     # 业务发生时间
    received_at: str = ""     # 系统接收时间
    version: str = ""         # 依据版本
    suggestion: str = DEFAULT_SUGGESTION
    review_status: str = "未复核"
    review_by: str = ""
    review_at: str = ""

    def as_row(self) -> Dict[str, str]:
        return {
            "校验": self.code,
            "类型": self.type,
            "对象": self.subject,
            "事实": self.detail,
            "业务发生时间": self.occurred_at,
            "系统接收时间": self.received_at,
            "依据版本": self.version,
            "来源位置": self.source_locator,
            "建议": self.suggestion,
            "复核状态": self.review_status,
            "复核人": self.review_by,
            "复核时间": self.review_at,
        }


def _width(text: str) -> int:
    """中文按 2 列宽计算，保证终端表格不歪。"""
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in text)


def _pad(text: str, width: int) -> str:
    return text + " " * max(0, width - _width(text))


@dataclass
class ItemSheet:
    batch_id: str
    findings: List[Finding] = field(default_factory=list)
    page_limit: int = 40
    out_of_scope: List[str] = field(default_factory=list)   # 被范围排除的对象（医疗/安保岗位等）
    suppressed_types: List[str] = field(default_factory=list)  # 未开启的异常类型

    def add(self, finding: Finding) -> None:
        self.findings.append(finding)

    def extend(self, findings: List[Finding]) -> None:
        self.findings.extend(findings)

    def filtered(self, allowed_types: Optional[List[str]] = None) -> List[Finding]:
        """按允许的异常类型过滤现场类异常（C1/C2），治理类异常始终保留。"""
        if allowed_types is None:
            return list(self.findings)
        kept = []
        for f in self.findings:
            if f.code in ("C1", "C2") and f.type not in allowed_types:
                self.suppressed_types.append(f.type)
                continue
            kept.append(f)
        self.suppressed_types = sorted(set(self.suppressed_types))
        self.findings = kept
        return kept

    def page_warning(self) -> Optional[str]:
        if len(self.findings) > self.page_limit:
            return (
                f"缺项清单 {len(self.findings)} 条，超过一页上限 {self.page_limit} 条。"
                "按设计，一页装不下说明筛选规则错了，不该加页——请先收窄异常类型或提高触发条件。"
            )
        return None

    def counts_by_type(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for f in self.findings:
            counts[f.type] = counts.get(f.type, 0) + 1
        return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))

    def counts_unreviewed(self) -> int:
        return sum(1 for f in self.findings if f.review_status == "未复核")

    def render_text(self, max_rows: Optional[int] = None) -> str:
        rows = self.findings if max_rows is None else self.findings[:max_rows]
        header = ["序号", "校验", "类型", "对象", "业务发生", "系统接收", "位置", "建议"]
        table = [[str(i + 1), f.code, f.type, f.subject, f.occurred_at or "—", f.received_at or "—",
                  f.source_locator, "仅提示"] for i, f in enumerate(rows)]
        widths = [_width(h) for h in header]
        for line in table:
            for i, cell in enumerate(line):
                widths[i] = max(widths[i], _width(cell))
        out = [" ".join(_pad(h, widths[i]) for i, h in enumerate(header))]
        out.append("-+-".join("-" * w for w in widths))
        for line in table:
            out.append(" ".join(_pad(cell, widths[i]) for i, cell in enumerate(line)))
        if max_rows is not None and len(self.findings) > max_rows:
            out.append(f"... 其余 {len(self.findings) - max_rows} 条见 out/items.csv")
        return "\n".join(out)

    def render_markdown(self) -> str:
        stamp = datetime.now().isoformat(timespec="seconds")
        lines = [
            f"# 一页缺项清单 · 批次 {self.batch_id}",
            "",
            f"- 生成时间：{stamp}",
            "- 性质：**待人工复核的建议**，不是业务结论；本工具不写回任何系统。",
            f"- 条目数：{len(self.findings)}（一页上限 {self.page_limit}）",
            "",
        ]
        warn = self.page_warning()
        if warn:
            lines += [f"> ⚠️ {warn}", ""]
        if self.out_of_scope:
            lines += [f"- 范围外已排除：{'；'.join(self.out_of_scope)}", ""]
        if self.suppressed_types:
            lines += [f"- 本次未开启的异常类型：{'、'.join(self.suppressed_types)}", ""]
        lines += [
            "| 序号 | 校验 | 类型 | 对象 | 事实 | 业务发生时间 | 系统接收时间 | 依据版本 | 来源位置 | 建议 | 复核状态 |",
            "|---|---|---|---|---|---|---|---|---|---|---|",
        ]
        for i, f in enumerate(self.findings, start=1):
            cells = [str(i), f.code, f.type, f.subject, f.detail, f.occurred_at or "—",
                     f.received_at or "—", f.version or "—", f"`{f.source_locator}`", f.suggestion, f.review_status]
            lines.append("| " + " | ".join(c.replace("|", "\\|") for c in cells) + " |")
        lines.append("")
        return "\n".join(lines)

    def to_csv(self, path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(Finding("", "", "", "", "").as_row().keys()))
            writer.writeheader()
            for f in self.findings:
                writer.writerow(f.as_row())
