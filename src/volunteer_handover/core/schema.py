"""表头契约：缺列必须让这一趟停下来，而不是变出一页假缺项。

为什么需要它
------------
没有这一层时，导出少了 `confirm_status` 一列，读取不会报错：
每行的值都是空字符串，三值逻辑如实把它记成"缺失"，
C6 于是报出"字段缺失但标记为已确认"——看起来像真问题，其实是导出少了一列。

真实场景里这很常见：不同人从不同工具导出，列名多一个空格、少一个字段都正常。
所以这里明确两类列：

- **必需列**：缺了就无法给出可信结论 → 整趟运行标 blocked，退出码 2。
- **可选列**：缺了只影响某一项判断 → 跳过那项判断，并写进警告。

宁可这一趟没有结论，也不能给假结论（对应失败方式 F9）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple

# col -> 缺了会影响什么（这个说明会原样出现在阻断原因里）
_WHY = {
    "positions.csv": {
        "position_id": "无法把班次关联到岗位",
        "category": "无法判断医疗/安保岗位是否已被排除（范围判断会变成假的）",
    },
    "shifts.csv": {
        "shift_id": "无法把签到、交接、编号关联到班次",
        "position_id": "无法判断点位要求与占位冲突",
        "person_code": "无法判断同一人是否被重复安排",
        "window_start": "无法判断时间窗重叠与倒置",
        "window_end": "无法判断时间窗重叠与倒置",
        "confirm_status": "无法区分已确认与未确认（三值判断失效）",
        "version_no": "无法核对版本有效期与交接版本",
        "occurred_at": "无法判断业务发生时间是否倒挂",
        "received_at": "无法判断系统接收时间与回填",
    },
    "checkins.csv": {
        "checkin_id": "无法追溯签到记录本身",
        "shift_id": "无法与排班交叉比对（缺岗判断会变成假的）",
        "person_code": "无法判断签到人与排班人是否一致",
        "occurred_at": "无法判断业务发生时间是否倒挂",
        "received_at": "无法判断系统接收时间与回填",
        "source_tool": "无法区分批量来源与实时来源（回填判定失效）",
    },
    "handover.csv": {
        "handover_id": "无法引用交接记录",
        "shift_id": "无法关联到班次版本",
        "from_person": "无法判断交出的责任人",
        "to_person": "无法判断接收人是否存在",
        "handover_at": "无法判断交接时间",
        "accepted_at": "会把每条交接都误判成未签收",
        "version_no": "无法核对交接版本与排班版本是否一致",
        "open_items": "无法判断未结项归属与截止时间",
    },
}

FILE_SCHEMAS: Dict[str, Dict[str, Tuple[str, ...]]] = {
    "positions.csv": {
        "required": ("position_id", "category"),
        "optional": ("position_name", "required_skill", "site_id"),
    },
    "shifts.csv": {
        "required": (
            "shift_id", "position_id", "person_code", "window_start", "window_end",
            "confirm_status", "version_no", "occurred_at", "received_at",
        ),
        "optional": (
            "batch_id", "skill_tags", "window_minutes",
            "version_valid_from", "version_valid_to", "superseded_by", "void_reason",
        ),
    },
    "checkins.csv": {
        "required": ("checkin_id", "shift_id", "person_code", "occurred_at", "received_at", "source_tool"),
        "optional": ("site_id", "checked_at"),
    },
    "handover.csv": {
        "required": (
            "handover_id", "shift_id", "from_person", "to_person",
            "handover_at", "accepted_at", "version_no", "open_items",
        ),
        "optional": ("notes",),
    },
}


@dataclass(frozen=True)
class ColumnCheck:
    file_name: str
    present: Tuple[str, ...] = ()
    missing_required: Tuple[str, ...] = ()
    missing_optional: Tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.missing_required

    def why(self) -> str:
        reasons = _WHY.get(self.file_name, {})
        return "；".join(f"{col}（{reasons.get(col, '相关判断失效')}）" for col in self.missing_required)

    def describe(self) -> str:
        head = f"{self.file_name} 缺少必需列：" + self.why()
        if self.missing_optional:
            head += f"；缺少可选列 {'、'.join(self.missing_optional)}（对应判断已跳过）"
        return head


def check_columns(file_name: str, header: Iterable[str]) -> ColumnCheck:
    schema = FILE_SCHEMAS.get(file_name)
    if schema is None:
        return ColumnCheck(file_name=file_name, present=tuple(header))
    present = tuple(header)
    have = set(present)
    return ColumnCheck(
        file_name=file_name,
        present=present,
        missing_required=tuple(c for c in schema["required"] if c not in have),
        missing_optional=tuple(c for c in schema["optional"] if c not in have),
    )


def required_columns(file_name: str) -> List[str]:
    return list(FILE_SCHEMAS.get(file_name, {}).get("required", ()))
