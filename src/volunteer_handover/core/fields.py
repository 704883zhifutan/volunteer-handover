"""字段字典与三值逻辑。

对应访谈事实 f31：需要对齐的关键字段为人员代号、岗位、技能标签、时间窗、确认状态；
**缺失值与未确认值必须区分**。一旦二者混成一个空值，导出后追溯就失真了。

所以这里不允许"空字符串 = 没有 = 不知道"这种漏斗。
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict


class Tri(Enum):
    """字段三态。任何字段值必须落到这三态之一。"""

    PRESENT = "有值"
    MISSING = "缺失"
    UNCONFIRMED = "未确认"


# 未确认的显式写法。空字符串永远算"缺失"，不算"未确认"。
_UNCONFIRMED_TOKENS = {"未确认", "待确认", "未核实", "unconfirmed", "tbd", "?"}

# 关键字段：跨工具对齐的目标（f31）
KEY_FIELDS = (
    "person_code",    # 人员代号
    "position_id",    # 岗位
    "skill_tags",     # 技能标签
    "window",         # 时间窗（window_start/window_end）
    "confirm_status", # 确认状态
)

FIELD_DICTIONARY: Dict[str, str] = {
    "shift_id": "班次编号（须唯一，跨工具可回填）",
    "batch_id": "批次号（试点只覆盖一个批次）",
    "position_id": "岗位编号",
    "person_code": "人员代号（脱敏，不含真实姓名）",
    "skill_tags": "技能标签，可多个",
    "window_start": "班次开始（业务时间）",
    "window_end": "班次结束（业务时间）",
    "window_minutes": "班次时长，单位：分钟",
    "confirm_status": "确认状态：confirmed / unconfirmed",
    "version_no": "版本号",
    "version_valid_from": "版本生效时间",
    "version_valid_to": "版本失效时间",
    "superseded_by": "被哪个版本替代；非空即视为已作废版本",
    "void_reason": "作废原因（作废必须填）",
    "occurred_at": "业务发生时间（现场真实发生的时刻）",
    "received_at": "系统接收时间（被系统记录的时刻，可能晚于发生）",
}

# 允许出现的异常类型（首批只开 4 类，避免误报泛滥）
SCOPE_ANOMALY_TYPES = (
    "缺岗未登记",
    "疑似重复占位",
    "排班表与现场不一致",
    "计划外到岗",
    "未确认项超时",
)


def tri(value: Any) -> Tri:
    """把任意值判成三态之一。"""
    if value is None:
        return Tri.MISSING
    text = str(value).strip()
    if text == "":
        return Tri.MISSING
    if text.lower() in _UNCONFIRMED_TOKENS:
        return Tri.UNCONFIRMED
    return Tri.PRESENT


def is_confirmed(value: Any) -> bool:
    return str(value or "").strip().lower() in ("confirmed", "已确认", "确认")


def is_unconfirmed(value: Any) -> bool:
    return str(value or "").strip().lower() in ("unconfirmed", "未确认", "待确认")


def missing_key_fields(row: Dict[str, str]) -> list:
    """返回该行三态不是"有值"的关键字段名，附带状态。"""
    checks = [
        ("person_code", row.get("person_code")),
        ("position_id", row.get("position_id")),
        ("skill_tags", row.get("skill_tags")),
        ("window_start", row.get("window_start")),
        ("confirm_status", row.get("confirm_status")),
    ]
    return [(name, tri(value)) for name, value in checks if tri(value) is not Tri.PRESENT]
