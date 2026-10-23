"""九条确定性校验 C1–C9。

每条校验对应方案 §3 的一种失败方式（F1–F10）。共同约束：

- **只判定，不修复**：不补值、不改写、不重试。
- **每条结论带 locator**：没有定位的结论直接丢弃（宁可少报，不留无法核对的条目）。
- **不让异常类型悄悄扩展**：C1/C2 的异常类型受配置白名单约束，其余属治理类，始终启用。
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, Iterable, List, Optional, Set

from .boundary import Boundary
from .fields import is_confirmed, missing_key_fields
from .ids import find_duplicate_ids, find_orphans
from .items import Finding
from .times import (
    dual_time_state,
    duration_minutes,
    gap_minutes,
    parse_ts,
    overlaps,
    version_active,
    window,
)

SUGGEST_VERIFY = "仅提示，不执行；请当班人员核对原始记录后确认"
SUGGEST_REVIEW = "仅提示，不执行；进入人工复核队列，等待当班负责人判断"


def _info(row):
    return (
        row.get("occurred_at"),
        row.get("received_at"),
        row.get("version_no"),
    )


# ---------------------------------------------------------------- C1 交叉比对
def c1_cross_check(shifts, checkins, positions_index: Dict[str, object], in_scope: Set[str]) -> List[Finding]:
    """排班表与签到记录互相对不上：缺岗未登记、点位不一致、人员不一致。"""
    findings: List[Finding] = []
    by_shift: Dict[str, list] = {}
    for row in checkins:
        by_shift.setdefault(row.get("shift_id"), []).append(row)

    # 有人到岗、排班表里却没有这个班次：多半是顶班或临时调人，不是数据错误。
    # 这类只出现在签到侧的情况以前由 C7 当成"编号断链"，语义是错的——
    # 断链是数据问题，顶班是现场事实，得让人去认。
    valid_ids = {s.get("shift_id") for s in shifts if s.get("shift_id")}
    for checkin in checkins:
        sid = checkin.get("shift_id")
        if not sid or sid in valid_ids:
            continue
        person = checkin.get("person_code") or "（未登记人员）"
        site = checkin.get("site_id") or "（未登记点位）"
        findings.append(
            Finding(
                code="C1",
                type="计划外到岗",
                subject=sid,
                detail=(
                    f"签到人员 {person}、点位 {site}，但排班表里没有班次 {sid}"
                    "（可能是顶班或临时调人，也可能排班表漏登记；需当班人确认是哪一种）"
                ),
                source_locator=checkin.locator,
                occurred_at=checkin.get("occurred_at"),
                received_at=checkin.get("received_at"),
                suggestion=SUGGEST_VERIFY,
            )
        )

    for shift in shifts:
        sid = shift.get("shift_id")
        if sid not in in_scope:
            continue
        occ, rec, ver = _info(shift)
        if not by_shift.get(sid):
            findings.append(
                Finding(
                    code="C1",
                    type="缺岗未登记",
                    subject=sid,
                    detail=f"排班存在于 {shift.locator}，签到记录中没有对应条目（未验证是否真的缺岗，只说明两边对不上）",
                    source_locator=shift.locator,
                    occurred_at=shift.get("window_start"),
                    received_at=rec,
                    version=ver,
                    suggestion=SUGGEST_VERIFY,
                )
            )
            continue
        position = positions_index.get(shift.get("position_id"))
        required_site = position.data.get("site_id", "") if position is not None else ""
        for checkin in by_shift[sid]:
            if required_site and checkin.get("site_id") and checkin.get("site_id") != required_site:
                findings.append(
                    Finding(
                        code="C1",
                        type="排班表与现场不一致",
                        subject=sid,
                        detail=f"岗位要求点位 {required_site}，签到记录点位 {checkin.get('site_id')}",
                        source_locator=f"{shift.locator} + {checkin.locator}",
                        occurred_at=checkin.get("occurred_at"),
                        received_at=checkin.get("received_at"),
                        version=ver,
                        suggestion=SUGGEST_VERIFY,
                    )
                )
            if checkin.get("person_code") and shift.get("person_code") and checkin.get("person_code") != shift.get("person_code"):
                findings.append(
                    Finding(
                        code="C1",
                        type="排班表与现场不一致",
                        subject=sid,
                        detail=f"排班人员 {shift.get('person_code')}，签到人员 {checkin.get('person_code')}",
                        source_locator=f"{shift.locator} + {checkin.locator}",
                        occurred_at=checkin.get("occurred_at"),
                        received_at=checkin.get("received_at"),
                        version=ver,
                        suggestion=SUGGEST_VERIFY,
                    )
                )
    return findings


# ---------------------------------------------------------------- C2 占位冲突
def c2_double_booking(shifts, in_scope: Set[str]) -> List[Finding]:
    """同一个人在时间重叠的两个点位上：替补被重复安排，是本次模拟异常的核心。"""
    findings: List[Finding] = []
    by_person: Dict[str, list] = {}
    for shift in shifts:
        if shift.get("shift_id") in in_scope and shift.get("person_code"):
            by_person.setdefault(shift.get("person_code"), []).append(shift)

    for person, rows in by_person.items():
        for i in range(len(rows)):
            for j in range(i + 1, len(rows)):
                a, b = rows[i], rows[j]
                a_start, a_end = window(a.data)
                b_start, b_end = window(b.data)
                if not overlaps(a_start, a_end, b_start, b_end):
                    continue
                if a.get("position_id") == b.get("position_id"):
                    continue  # 同一岗位的连班不算冲突
                findings.append(
                    Finding(
                        code="C2",
                        type="疑似重复占位",
                        subject=person,
                        detail=(
                            f"{a.get('shift_id')}({a.get('position_id')} {a.get('window_start')}–{a.get('window_end')}) "
                            f"与 {b.get('shift_id')}({b.get('position_id')} {b.get('window_start')}–{b.get('window_end')}) 重叠"
                        ),
                        source_locator=f"{a.locator} + {b.locator}",
                        occurred_at=a.get("window_start"),
                        received_at=a.get("received_at"),
                        version=a.get("version_no"),
                        suggestion=SUGGEST_VERIFY,
                        refs=f"{a.get('shift_id')},{b.get('shift_id')}",
                    )
                )
    return findings


# ---------------------------------------------------------------- C3 双时间
# 计划类记录：排班是"事先安排"，接收时间早于班次开始是正常的，不构成倒挂
PLANNED_FILES = frozenset({"shifts.csv"})


def c3_dual_time(rows_by_file: Dict[str, Iterable], threshold_minutes: Optional[float]) -> List[Finding]:
    """业务发生时间与系统接收时间的单调性。

    阈值未核实时（threshold_minutes is None），只标记倒挂与批量补录来源的回填，
    不对"晚了几分钟"报警——那会把误报刷成噪音，最终没人看清单。

    计划类记录（shifts.csv）不判倒挂：排班本来就写在班次开始之前。
    只对**事件类**记录（签到、交接）要求"接收不早于发生"。
    """
    findings: List[Finding] = []
    for file_name, rows in rows_by_file.items():
        planned = file_name in PLANNED_FILES
        for row in rows:
            occurred = row.get("occurred_at")
            received = row.get("received_at")
            if not occurred or not received:
                continue  # 缺失由 C6 负责，避免同一事实重复计数
            state = dual_time_state(occurred, received, threshold_minutes, row.get("source_tool", ""))
            if state == "时间倒挂" and planned:
                continue  # 事先安排，接收早于班次开始不算矛盾
            if state == "正常":
                continue
            if state.startswith("缺失"):
                continue
            delta = gap_minutes(parse_ts(occurred), parse_ts(received))
            findings.append(
                Finding(
                    code="C3",
                    type="时间倒挂" if state == "时间倒挂" else "疑似回填",
                    subject=row.get("shift_id") or row.get("checkin_id") or row.get("handover_id") or file_name,
                    detail=(
                        f"业务发生 {occurred}、系统接收 {received}，相差 {delta:+.0f} 分钟；"
                        + ("接收早于发生，两个时间戳必有其一不可信" if state == "时间倒挂"
                           else "批量补录来源晚于发生，只能证明补录时间")
                    ),
                    source_locator=row.locator,
                    occurred_at=occurred,
                    received_at=received,
                    version=row.get("version_no", ""),
                    suggestion="仅提示，不执行；以业务发生时间为口径（f53），回填时间不得当发生时间",
                )
            )
    return findings


# ---------------------------------------------------------------- C4 版本有效性
def c4_version(shifts, in_scope: Set[str], as_of: Optional[datetime], require_validity: bool = True) -> List[Finding]:
    """版本靠"有效期 + 确认状态"两条件判定，不靠文件名猜（f24）。"""
    findings: List[Finding] = []
    for shift in shifts:
        if shift.get("shift_id") not in in_scope:
            continue
        occ, rec, ver = _info(shift)
        problems = []
        if shift.get("superseded_by"):
            problems.append(f"已被 {shift.get('superseded_by')} 替代，但仍以 {ver} 出现")
        if shift.get("void_reason"):
            problems.append(f"已作废（{shift.get('void_reason')}）")
        if not is_confirmed(shift.get("confirm_status")):
            problems.append(f"确认状态为 {shift.get('confirm_status') or '空'}")
        if require_validity and not version_active(shift.data, as_of):
            problems.append("有效期覆盖不到当前时点或有效期缺失")
        if not problems:
            continue
        findings.append(
            Finding(
                code="C4",
                type="版本断链或过期" if any("替代" in p or "有效期" in p for p in problems) else "版本未确认",
                subject=shift.get("shift_id"),
                detail="；".join(problems) + "。过期版本不得覆盖已确认的新版本（f34）。",
                source_locator=shift.locator,
                occurred_at=occ,
                received_at=rec,
                version=ver,
                suggestion=SUGGEST_REVIEW,
            )
        )
    return findings


# ---------------------------------------------------------------- C6 三值逻辑
def c6_tri_state(shifts, in_scope: Set[str]) -> List[Finding]:
    """确认状态为"已确认"，但关键字段缺失或时间缺失：缺失被当成了"已知"。"""
    findings: List[Finding] = []
    for shift in shifts:
        if shift.get("shift_id") not in in_scope:
            continue
        if not is_confirmed(shift.get("confirm_status")):
            continue
        holes = [f"{name}={state.value}" for name, state in missing_key_fields(shift.data)]
        for field_name, label in (("occurred_at", "业务发生时间"), ("received_at", "系统接收时间")):
            if not shift.get(field_name):
                holes.append(f"{label}=缺失")
        if not holes:
            continue
        findings.append(
            Finding(
                code="C6",
                type="缺失与未确认混同",
                subject=shift.get("shift_id"),
                detail="该行标记为已确认，但存在空洞：" + "、".join(holes) + "。缺失值不等于默认值。",
                source_locator=shift.locator,
                occurred_at=shift.get("occurred_at"),
                received_at=shift.get("received_at"),
                version=shift.get("version_no"),
                suggestion="仅提示，不执行；不得补默认值，退回提交人补录或转未确认",
            )
        )
    return findings


# ---------------------------------------------------------------- C7 编号与单位
def c7_numbering(shifts, checkins, handovers) -> List[Finding]:
    """重复编号、孤儿引用、单位差异、时间窗倒置。保留原行，不改写（f33）。"""
    findings: List[Finding] = []
    for sid, locators in find_duplicate_ids(shifts).items():
        findings.append(
            Finding(
                code="C7",
                type="重复编号",
                subject=sid,
                detail=f"同一班次编号出现在 {len(locators)} 行：{'、'.join(locators)}",
                source_locator="、".join(locators),
                suggestion=SUGGEST_REVIEW,
            )
        )

    # 签到侧的孤儿引用不在 C7 报：那是"计划外到岗"，由 C1 报（同一行不重复计数）
    valid_ids = {s.get("shift_id") for s in shifts if s.get("shift_id")}
    for locator, ref in find_orphans(handovers, valid_ids):
        findings.append(
            Finding(
                code="C7",
                type="编号断链",
                subject=ref,
                detail=f"交接记录引用了不存在的班次编号 {ref}",
                source_locator=locator,
                suggestion=SUGGEST_REVIEW,
            )
        )

    for shift in shifts:
        start, end = window(shift.data)
        if start is not None and end is not None and end <= start:
            findings.append(
                Finding(
                    code="C7",
                    type="时间窗倒置",
                    subject=shift.get("shift_id"),
                    detail=f"开始 {shift.get('window_start')} 不早于结束 {shift.get('window_end')}",
                    source_locator=shift.locator,
                    suggestion=SUGGEST_REVIEW,
                )
            )
        declared_raw = shift.get("window_minutes")
        if not declared_raw:
            continue
        try:
            declared = float(declared_raw)
        except ValueError:
            findings.append(
                Finding(
                    code="C7",
                    type="单位差异",
                    subject=shift.get("shift_id"),
                    detail=f"时长字段 {declared_raw!r} 不是数字",
                    source_locator=shift.locator,
                    suggestion=SUGGEST_REVIEW,
                )
            )
            continue
        actual = duration_minutes(start, end)
        if actual is None:
            continue
        if abs(declared - actual) <= 1:
            continue
        hint = "（疑似把小时填进了分钟字段）" if abs(declared * 60 - actual) <= 1 else ""
        findings.append(
            Finding(
                code="C7",
                type="单位差异",
                subject=shift.get("shift_id"),
                detail=f"声明 {declared:.0f} 分钟，按时间窗实算 {actual} 分钟{hint}",
                source_locator=shift.locator,
                suggestion=SUGGEST_REVIEW,
            )
        )
    return findings


# ---------------------------------------------------------------- C8 失败即标记
def c8_failure_marks(snapshots) -> List[Finding]:
    """读取失败必须留下带时间的快照记录，且不得用旧数据或默认值充数（f35）。"""
    findings: List[Finding] = []
    for snap in snapshots:
        if snap.status == "ok":
            continue
        findings.append(
            Finding(
                code="C8",
                type="数据读取失败",
                subject=snap.file_name,
                detail=f"{snap.taken_at} 读取 {snap.file_name} 失败（{snap.note}）；本次结论不覆盖该文件",
                source_locator=f"{snap.file_name}（快照 {snap.taken_at}）",
                occurred_at="",
                received_at=snap.taken_at,
                suggestion="仅提示，不执行；补齐导出后重跑，不得沿用上一次结果冒充最新",
            )
        )
    return findings


# ---------------------------------------------------------------- C9 能力边界
def c9_boundary(boundary: Boundary) -> List[Finding]:
    """写回、外部发送、自动指派一类的配置出现即报，且运行失败（见 engine）。"""
    findings: List[Finding] = []
    for key, value in boundary.violations():
        findings.append(
            Finding(
                code="C9",
                type="能力越界",
                subject=key,
                detail=f"配置里出现了越界能力：{key} = {value}",
                source_locator="config/default.yaml#boundary",
                suggestion="仅提示，不执行；从配置中删除该项，改由人工流程处理",
            )
        )
    return findings


def all_checks(dataset, positions_index, in_scope, boundary: Boundary, config: dict,
               checks: List[HandoverCheck] = None) -> List[Finding]:
    """按固定顺序跑 C1/C2/C3/C4/C6/C7/C8/C9；C5 由 handover 模块产出。"""
    from .handover import checklist_findings

    threshold = None
    if isinstance(config, dict):
        time_cfg = config.get("time") or {}
        threshold = time_cfg.get("backfill_threshold_minutes")
    as_of = parse_ts((config.get("time") or {}).get("as_of") or "") if isinstance(config, dict) else None
    require_validity = bool(((config.get("versions") or {}).get("require_validity_window", True))) if isinstance(config, dict) else True

    findings: List[Finding] = []
    # 依赖不可读就整条跳过：把"没读到签到"当成"没人签到"会凭空造出缺岗（F9 假状态）
    if dataset.available("shifts.csv"):
        if dataset.available("checkins.csv") and dataset.available("positions.csv"):
            findings += c1_cross_check(
                dataset.get("shifts.csv"), dataset.get("checkins.csv"), positions_index, in_scope
            )
        findings += c2_double_booking(dataset.get("shifts.csv"), in_scope)
    findings += c3_dual_time(
        {name: dataset.get(name) for name in ("checkins.csv", "shifts.csv") if dataset.available(name)},
        threshold,
    )
    findings += c4_version(dataset.get("shifts.csv"), in_scope, as_of, require_validity)
    if checks:
        findings += checklist_findings(checks)
    findings += c6_tri_state(dataset.get("shifts.csv"), in_scope)
    findings += c7_numbering(dataset.get("shifts.csv"), dataset.get("checkins.csv"), dataset.get("handover.csv"))
    findings += c8_failure_marks(dataset.snapshots)
    findings += c9_boundary(boundary)
    return findings
