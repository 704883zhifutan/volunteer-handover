"""跨工具关联编号。

对应访谈事实 f30（三类工具、无统一关联编号）、f33（重复编号 / 孤儿引用）、H5（编号规则责任方待核实）。

`build_shift_id` 只提供一种**候选**规则，不替业务方拍板：
  批次号:岗位:班次开始(MMDDHHMM):人员代号
真实规则由业务负责人确认后再改这里，并在 docs/design.md 记一条变更。
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, Iterable, List, Optional, Tuple

from .times import parse_ts


def build_shift_id(batch_id: str, position_id: str, window_start: str, person_code: str) -> str:
    start = parse_ts(window_start)
    stamp = start.strftime("%m%d%H%M") if start else "NOTIME"
    return f"{batch_id}:{position_id}:{stamp}:{person_code}"


def find_duplicate_ids(rows: Iterable) -> Dict[str, List[str]]:
    """同一编号出现在多行 → 返回 {编号: [locator, ...]}。"""
    seen: Dict[str, List[str]] = {}
    for row in rows:
        key = row.get("shift_id")
        if key:
            seen.setdefault(key, []).append(row.locator)
    return {k: v for k, v in seen.items() if len(v) > 1}


def find_orphans(rows: Iterable, valid_ids: Iterable[str], id_field: str = "shift_id") -> List[Tuple[str, str]]:
    """引用了一个不存在的班次编号 → 返回 [(locator, 引用值), ...]（断链/孤儿）。"""
    valid = set(valid_ids)
    broken: List[Tuple[str, str]] = []
    for row in rows:
        ref = row.get(id_field)
        if ref and ref not in valid:
            broken.append((row.locator, ref))
    return broken


def number_gaps(ids: Iterable[str], prefix: str = "S") -> List[str]:
    """编号连续性提示（仅对纯数字后缀有效）；不连续不等于错误，只作提示。"""
    numbers = []
    for value in ids:
        tail = value[len(prefix):] if value.startswith(prefix) else ""
        if tail.isdigit():
            numbers.append(int(tail))
    if not numbers:
        return []
    numbers.sort()
    return [f"{prefix}{n:0{len(str(numbers[-1]))}d}" for n in range(1, numbers[-1] + 1) if n not in numbers]
