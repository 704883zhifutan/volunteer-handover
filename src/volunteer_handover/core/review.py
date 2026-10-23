"""复核回填：把人的判断读回来。

为什么必须有这一层
------------------
没有它，"误报率""确认完整率"就没法算，W4 复盘只能凭印象说"好像还行"。
更糟的是：清单发出去、人核过了，结论却停在纸上，第二天重新跑一遍又从零开始。

三条规则
--------
1. **结论必须有人**：没有复核人的行不生效。没人负责的"已确认"等于没确认（f22/f45）。
2. **结论必须有时间**：没有复核时间的行不生效，否则无法回答"压了多久还没核"。
3. **对不上的编号不静默丢弃**：数据一变编号就变（见 items.make_finding_id），
   旧结论会挂不上。这时要显式报出来让人重新核，而不是当成"没有异常"。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

from ..utils.csvio import read_rows
from .items import REVIEW_CONCLUSIONS, Finding

REVIEW_COLUMNS = ("编号", "复核状态", "复核人", "复核时间", "备注")


@dataclass(frozen=True)
class ReviewEntry:
    fid: str
    status: str
    by: str
    at: str
    note: str = ""
    locator: str = ""


@dataclass(frozen=True)
class ReviewProblem:
    locator: str
    reason: str


@dataclass
class ReviewApply:
    total: int = 0
    reviewed: int = 0
    applied: int = 0
    unmatched: List[ReviewEntry] = field(default_factory=list)
    problems: List[ReviewProblem] = field(default_factory=list)

    def note(self) -> str:
        if self.applied == 0 and not self.problems:
            return ""
        return f"已回填 {self.applied}/{self.total} 条，对不上 {len(self.unmatched)} 条，格式问题 {len(self.problems)} 条"


def load_reviews(path) -> Tuple[List[ReviewEntry], List[ReviewProblem]]:
    """读取人工回填表。文件不存在不算错误——只是这次没做回填。"""
    entries: List[ReviewEntry] = []
    problems: List[ReviewProblem] = []
    p = Path(path)
    if not p.exists():
        return entries, problems

    for row in read_rows(p):
        fid = row.get("编号")
        status = row.get("复核状态")
        by = row.get("复核人")
        at = row.get("复核时间")
        if not fid:
            problems.append(ReviewProblem(row.locator, "缺编号：无法关联到清单条目"))
            continue
        if status not in REVIEW_CONCLUSIONS:
            problems.append(
                ReviewProblem(
                    row.locator,
                    f"复核状态「{status or '空'}」无效，只能是 {'/'.join(REVIEW_CONCLUSIONS)}"
                    "（工具不替人做结论，也不默认通过）",
                )
            )
            continue
        if not by:
            problems.append(ReviewProblem(row.locator, "缺复核人：没人负责的结论不生效"))
            continue
        if not at:
            problems.append(ReviewProblem(row.locator, "缺复核时间：无法计算复核滞后"))
            continue
        entries.append(ReviewEntry(fid=fid, status=status, by=by, at=at, note=row.get("备注"), locator=row.locator))
    return entries, problems


def apply_reviews(findings: Iterable[Finding], entries: Iterable[ReviewEntry]) -> ReviewApply:
    index: Dict[str, Finding] = {f.fid: f for f in findings}
    result = ReviewApply(total=len(index), reviewed=sum(1 for f in index.values() if f.review_status != "未复核"))
    seen = set()
    for entry in entries:
        if entry.fid in seen:
            result.problems.append(ReviewProblem(entry.locator, "编号重复：同一编号只认第一条，后一条忽略"))
            continue
        seen.add(entry.fid)
        target = index.get(entry.fid)
        if target is None:
            result.unmatched.append(entry)
            continue
        target.review_status = entry.status
        target.review_by = entry.by
        target.review_at = entry.at
        result.applied += 1
    result.reviewed = sum(1 for f in index.values() if f.review_status != "未复核")
    return result
