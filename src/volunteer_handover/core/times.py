"""时间处理：双时间戳、时间窗、重叠判定。

对应访谈事实 f13（回填时间不能当发生时间）、f34（同时记录业务发生时间与系统接收时间）、
f35（读取失败保留快照并标记时间，不编造最新状态）、f21/f24（版本有效期）。

一条硬规则：**延迟阈值尚未核实（H1），所以默认不判定"超阈值"，只标记"疑似回填"。**
不要在代码里偷偷塞一个 15 分钟之类的魔法数字。
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, Tuple

TIME_FORMATS = (
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
)

# 批量补录类来源：阈值未定时，仅对这类来源标记"疑似回填"
BATCH_SOURCE_HINTS = ("文件库", "批量", "补录", "群消息")


def parse_ts(value: Optional[str]) -> Optional[datetime]:
    text = (value or "").strip()
    if not text:
        return None
    for fmt in TIME_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def gap_minutes(occurred: Optional[datetime], received: Optional[datetime]) -> Optional[float]:
    if occurred is None or received is None:
        return None
    return (received - occurred).total_seconds() / 60.0


def is_batch_source(source_tool: str) -> bool:
    text = (source_tool or "").strip()
    return any(hint in text for hint in BATCH_SOURCE_HINTS)


def dual_time_state(
    occurred: Optional[str],
    received: Optional[str],
    threshold_minutes: Optional[float] = None,
    source_tool: str = "",
) -> str:
    """判断双时间关系。

    返回：正常 / 时间倒挂 / 疑似回填 / 缺失(业务发生时间) / 缺失(系统接收时间)

    threshold_minutes 为 None 时（默认，因为事实未核实）：
    - 只要接收早于发生，判"时间倒挂"（这是矛盾，与阈值无关）；
    - 仅当来源是批量补录类且接收晚于发生，判"疑似回填"；
    - 其余情况判"正常"，**不因为"晚了 3 分钟"就报警**。
    """
    occ = parse_ts(occurred)
    rec = parse_ts(received)
    if occ is None:
        return "缺失(业务发生时间)"
    if rec is None:
        return "缺失(系统接收时间)"
    delta = gap_minutes(occ, rec)
    if delta is None:
        return "正常"
    if delta < 0:
        return "时间倒挂"
    if delta == 0:
        return "正常"
    if threshold_minutes is not None:
        return "疑似回填" if delta >= float(threshold_minutes) else "正常"
    return "疑似回填" if is_batch_source(source_tool) else "正常"


def window(row: dict) -> Tuple[Optional[datetime], Optional[datetime]]:
    return parse_ts(row.get("window_start")), parse_ts(row.get("window_end"))


def overlaps(a_start, a_end, b_start, b_end) -> bool:
    if None in (a_start, a_end, b_start, b_end):
        return False
    return a_start < b_end and b_start < a_end


def duration_minutes(start: Optional[datetime], end: Optional[datetime]) -> Optional[int]:
    if start is None or end is None:
        return None
    return int((end - start).total_seconds() // 60)


def version_active(row: dict, as_of: Optional[datetime]) -> bool:
    """版本是否在有效期内。有效期缺失即视为无法判定，返回 False 并由调用方标记。"""
    start = parse_ts(row.get("version_valid_from"))
    end = parse_ts(row.get("version_valid_to"))
    if start is None or end is None:
        return False
    if as_of is None:
        return True
    return start <= as_of <= end
