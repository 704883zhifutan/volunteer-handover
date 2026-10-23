"""批次对比：今天的清单和上一次比，多了什么、少了什么。

为什么要有这个：一次运行只能回答"现在有什么"。现场真正要问的是
"昨天那条未结项今天还在不在"——而这句话只有在**编号稳定**的前提下才算得出来。
所以这里的比对键不是 `编号`（内容指纹，事实字段一变就换号），而是
`(校验, 类型, 对象)` 这组"业务身份"；编号变化单独标成"内容有变"。

一条纪律：**"消失"不等于"解决了"。** 可能是数据没读到、可能是换了一批数据、
可能是有人改了判定口径。所以对比结果里消失项永远单独列，并附一句提醒，
不合并进"已解决"。
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

from .items import Finding, finding_from_row

NEW = "新增"
PERSIST = "持续"
GONE = "消失"


@dataclass(frozen=True)
class DiffEntry:
    kind: str
    finding: Finding
    note: str = ""

    @property
    def key(self) -> Tuple[str, str, str]:
        return (self.finding.code, self.finding.type, self.finding.subject)


def load_items(path) -> List[Finding]:
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        return [finding_from_row(row) for row in reader]


def _group(findings: List[Finding]) -> Dict[Tuple[str, str, str], List[Finding]]:
    groups: Dict[Tuple[str, str, str], List[Finding]] = {}
    for finding in findings:
        groups.setdefault((finding.code, finding.type, finding.subject), []).append(finding)
    return groups


def compute(previous: List[Finding], current: List[Finding]) -> List[DiffEntry]:
    """按业务身份分组后逐条配对。

    同一组里可能有多条（同一个交接有 OI-1、OI-2 两条逾期），所以不能简单地"一键对一条"：
    先按编号精确配对，再按来源位置配，剩下的按顺序配。配对不上的才是新增/消失。
    """
    prev_groups = _group(previous)
    curr_groups = _group(current)
    entries: List[DiffEntry] = []

    for key in sorted(set(prev_groups) | set(curr_groups)):
        olds = list(prev_groups.get(key, []))
        news = list(curr_groups.get(key, []))

        # 1) 编号完全相同：同一件事没变
        for cur in list(news):
            match = next((o for o in olds if o.fid == cur.fid), None)
            if match is not None:
                entries.append(DiffEntry(PERSIST, cur))
                news.remove(cur)
                olds.remove(match)

        # 2) 同一来源位置、编号变了：事情还在，内容有变
        for cur in list(news):
            match = next((o for o in olds if o.source_locator == cur.source_locator), None)
            if match is not None:
                entries.append(DiffEntry(PERSIST, cur, note=f"内容有变（{match.fid} → {cur.fid}）"))
                news.remove(cur)
                olds.remove(match)

        # 3) 同组内剩余按顺序配对：位置也变了（比如前面插了一行），但事还是那件事
        for cur, old in zip(list(news), list(olds)):
            entries.append(DiffEntry(PERSIST, cur, note="内容有变（位置或细节变化）"))
            news.remove(cur)
            olds.remove(old)

        entries.extend(DiffEntry(NEW, cur) for cur in news)
        entries.extend(DiffEntry(GONE, old, note="不代表已解决，需人确认") for old in olds)

    order = {NEW: 0, PERSIST: 1, GONE: 2}
    entries.sort(key=lambda e: (order[e.kind], e.finding.type, e.finding.subject, e.finding.source_locator))
    return entries


def counts(entries: List[DiffEntry]) -> Dict[str, int]:
    return {
        NEW: sum(1 for e in entries if e.kind == NEW),
        PERSIST: sum(1 for e in entries if e.kind == PERSIST),
        GONE: sum(1 for e in entries if e.kind == GONE),
    }


def render_markdown(entries: List[DiffEntry], prev_label: str, curr_label: str) -> str:
    stat = counts(entries)
    lines = [
        f"# 批次对比 · {prev_label} → {curr_label}",
        "",
        f"新增 {stat[NEW]} · 持续 {stat[PERSIST]} · 消失 {stat[GONE]}",
        "",
        "比对键是「校验 + 类型 + 对象」，不是编号：编号是内容指纹，字段一改就换号。",
        "",
        "> **消失不等于已解决。** 可能是文件没读到、批次换了、或口径变了；"
        "消失项必须由人确认，系统不会把它算成“已整改”。",
        "",
    ]
    if not entries:
        lines.append("两次运行没有差异（条目、编号都一致）。")
        return "\n".join(lines) + "\n"

    for title, kind in ((f"新增（{stat[NEW]}）", NEW), (f"持续（{stat[PERSIST]}）", PERSIST), (f"消失（{stat[GONE]}）", GONE)):
        group = [e for e in entries if e.kind == kind]
        if not group:
            continue
        lines += [f"## {title}", "", "| 类型 | 对象 | 详情 | 位置 | 备注 |", "|---|---|---|---|---|"]
        for entry in group:
            f = entry.finding
            detail = f.detail.replace("|", "／")
            lines.append(
                f"| {f.type} | {f.subject} | {detail} | {f.source_locator} | {entry.note or '—'} |"
            )
        lines.append("")
    return "\n".join(lines)


def to_csv(entries: List[DiffEntry], path) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["变化", "编号", "校验", "类型", "对象", "详情", "来源位置", "复核状态", "备注"])
        for entry in entries:
            f = entry.finding
            writer.writerow(
                [entry.kind, f.fid, f.code, f.type, f.subject, f.detail, f.source_locator, f.review_status, entry.note]
            )
    return out


def render_text(entries: List[DiffEntry]) -> str:
    stat = counts(entries)
    head = f"批次对比：新增 {stat[NEW]} · 持续 {stat[PERSIST]} · 消失 {stat[GONE]}"
    if not entries:
        return head + "（两次一致）"
    lines = [head]
    for kind in (NEW, GONE):
        group = [e for e in entries if e.kind == kind]
        for entry in group[:5]:
            lines.append(f"  {kind}  {entry.finding.type}  {entry.finding.subject}")
        if len(group) > 5:
            lines.append(f"  {kind}  …另有 {len(group) - 5} 条，见 diff.md")
    if stat[GONE]:
        lines.append("  注意：消失不等于已解决，需人确认")
    return "\n".join(lines)
