"""产物 B：交接责任清单。

对应访谈事实 f20/f23（每次交接必须有接收人、版本、未结项清单）、f24（版本靠有效期+确认状态）、
f25（未确认项不归对方、变更要有责任人）。

一条边界：**"完成"的定义尚未确认（G3，见方案 §3）。**
所以 `HandoverCheck` 只输出可核对的信号（未签收 / 无责任人 / 逾期 / 版本无效），
不输出 `is_complete` 这样的判断题——那是业务负责人的判断，不是代码的。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from .items import Finding
from .times import parse_ts, version_active

OPEN_ITEM_SEP = "|"
FIELD_SEP = ";"
STATUS_OPEN = "未结"


@dataclass
class OpenItem:
    item_id: str
    desc: str
    deadline: Optional[datetime]
    owner: str
    status: str
    raw: str = ""

    @property
    def is_open(self) -> bool:
        return self.status != "已结"

    @property
    def has_owner(self) -> bool:
        return bool((self.owner or "").strip())


def parse_open_items(text: str) -> List[OpenItem]:
    """解析 `OI-1;事项;截止;责任人;状态`，多项用 | 分隔。

    形状不对的项不丢弃，而是保留 raw 并标记为无法判定——丢弃等于掩盖数据问题。
    """
    items: List[OpenItem] = []
    for chunk in (text or "").split(OPEN_ITEM_SEP):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = [p.strip() for p in chunk.split(FIELD_SEP)]
        if len(parts) < 5:
            items.append(OpenItem(item_id=parts[0] if parts else "?", desc=chunk, deadline=None,
                                  owner="", status="格式无法判定", raw=chunk))
            continue
        items.append(
            OpenItem(
                item_id=parts[0],
                desc=parts[1],
                deadline=parse_ts(parts[2]),
                owner=parts[3],
                status=parts[4],
                raw=chunk,
            )
        )
    return items


@dataclass
class HandoverCheck:
    handover_id: str
    shift_id: str
    from_person: str
    to_person: str
    handover_at: str
    accepted_at: str
    version_no: str
    version_state: str
    items: List[OpenItem] = field(default_factory=list)
    flags: List[str] = field(default_factory=list)
    source_locator: str = ""
    shift_locator: str = ""

    @property
    def open_items(self) -> List[OpenItem]:
        return [i for i in self.items if i.is_open]

    def as_row(self) -> Dict[str, str]:
        return {
            "交接编号": self.handover_id,
            "班次": self.shift_id,
            "交出": self.from_person,
            "接收": self.to_person or "（缺失）",
            "交接时间": self.handover_at,
            "签收时间": self.accepted_at or "（缺失）",
            "版本": self.version_no,
            "版本状态": self.version_state,
            "未结项": "；".join(f"{i.item_id}:{i.desc}" for i in self.open_items) or "无",
            "信号": "；".join(self.flags) or "无",
            "来源位置": self.source_locator,
        }


def _version_state(shift_row: Optional[dict], as_of: Optional[datetime]) -> str:
    if shift_row is None:
        return "找不到对应班次（断链）"
    if shift_row.get("superseded_by"):
        return f"已被 {shift_row.get('superseded_by')} 替代"
    if shift_row.get("void_reason"):
        return "已作废"
    if str(shift_row.get("confirm_status", "")).lower() not in ("confirmed", "已确认"):
        return "未确认"
    if not version_active(shift_row, as_of):
        return "不在有效期内"
    return "有效"


def build_checklist(handover_rows, shift_index: Dict[str, object], as_of: Optional[datetime]) -> List[HandoverCheck]:
    """把交接记录 + 对应班次版本，组装成可核对的清单。"""
    checks: List[HandoverCheck] = []
    for row in handover_rows:
        shift = shift_index.get(row.get("shift_id"))
        shift_row = shift.data if shift is not None else None
        check = HandoverCheck(
            handover_id=row.get("handover_id"),
            shift_id=row.get("shift_id"),
            from_person=row.get("from_person"),
            to_person=row.get("to_person"),
            handover_at=row.get("handover_at"),
            accepted_at=row.get("accepted_at"),
            version_no=row.get("version_no"),
            version_state=_version_state(shift_row, as_of),
            items=parse_open_items(row.get("open_items")),
            source_locator=row.locator,
            shift_locator=shift.locator if shift is not None else "",
        )

        if not check.accepted_at:
            check.flags.append("未签收")
        if not check.to_person:
            check.flags.append("接收人缺失")
        elif check.to_person == check.from_person:
            check.flags.append("交出人与接收人为同一人")
        if check.version_state != "有效":
            check.flags.append(f"版本{check.version_state}")
        if shift_row is not None and shift_row.get("version_no") and check.version_no:
            if shift_row.get("version_no") != check.version_no:
                check.flags.append(f"交接版本({check.version_no})≠排班版本({shift_row.get('version_no')})")

        for item in check.items:
            if item.status == "格式无法判定":
                check.flags.append(f"{item.item_id} 未结项格式无法判定")
                continue
            if not item.is_open:
                continue
            if not item.has_owner:
                check.flags.append(f"{item.item_id} 未结项无责任人")
            if item.deadline is None:
                check.flags.append(f"{item.item_id} 未结项无截止时间")
            elif as_of is not None and item.deadline < as_of:
                check.flags.append(f"{item.item_id} 逾期未结")
        checks.append(check)
    return checks


def checklist_findings(checks: List[HandoverCheck]) -> List[Finding]:
    """把清单信号转成缺项条目，保证每条都能回溯。"""
    findings: List[Finding] = []
    for c in checks:
        for flag in c.flags:
            kind = "交接确认链缺失"
            if "版本" in flag:
                kind = "版本断链或过期"
            elif "逾期" in flag:
                kind = "未确认项超时"
            elif "责任人" in flag or "截止时间" in flag:
                kind = "未结项归属缺失"
            findings.append(
                Finding(
                    code="C5",
                    type=kind,
                    subject=f"{c.handover_id}/{c.shift_id}",
                    detail=f"交接 {c.handover_id}：{flag}",
                    source_locator=c.source_locator,
                    occurred_at=c.handover_at,
                    received_at="",
                    version=c.version_no,
                    suggestion="仅提示，不执行；由交接双方与当班负责人现场核对",
                )
            )
    return findings


def render_markdown(checks: List[HandoverCheck], batch_id: str) -> str:
    stamp = datetime.now().isoformat(timespec="seconds")
    lines = [
        f"# 交接责任清单 · 批次 {batch_id}",
        "",
        f"- 生成时间：{stamp}",
        "- 性质：**待人工复核的核对清单**；本工具不写回、不发送、不指派。",
        "- “完成”的定义：**待确认（G3：是否包含交接确认，由业务负责人与项目流程协调员共同确认）**",
        "",
        "| 交接 | 班次 | 交出 | 接收 | 交接时间 | 签收 | 版本 | 版本状态 | 未结项 | 信号 | 来源位置 |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for c in checks:
        cells = [
            c.handover_id, c.shift_id, c.from_person, c.to_person or "（缺失）", c.handover_at,
            c.accepted_at or "（缺失）", c.version_no, c.version_state,
            "；".join(f"{i.item_id} {i.desc}" for i in c.open_items) or "无",
            "；".join(c.flags) or "无",
            f"`{c.source_locator}`",
        ]
        lines.append("| " + " | ".join(str(x).replace("|", "\\|") for x in cells) + " |")
    lines += ["", "> 表内信号不等于结论。逾期是否可接受、未结项能否随班移交，由当班负责人判断。", ""]
    return "\n".join(lines)
