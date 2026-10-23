"""编排：一次只读运行，产出一页缺项清单 + 交接责任清单 + 快照 + 审计。

刻意不做的事：
- 不合并两次运行的结论（避免"用旧结果冒充最新"，f35）；
- 不在越界配置下"尽力而为"——查到越界就把运行标成 blocked，退出码 2；
- 不把建议落地（没有执行入口）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from ..utils.logutil import AuditLog
from .boundary import Boundary
from .checks import all_checks
from .handover import HandoverCheck, build_checklist, render_markdown as render_handover
from .items import ItemSheet
from .loader import Dataset, index_by, load_dataset
from .times import parse_ts

SCOPE_NOTE = "医疗与安保岗位不进入试点范围，也不自动指派（f05）"


@dataclass
class RunResult:
    batch_id: str
    dataset: Dataset
    items: ItemSheet
    checks: List[HandoverCheck]
    audit: AuditLog
    as_of: Optional[datetime] = None
    blocked_reason: str = ""
    warnings: List[str] = field(default_factory=list)
    excluded_shifts: List[str] = field(default_factory=list)

    @property
    def blocked(self) -> bool:
        return bool(self.blocked_reason)

    def summary(self) -> Dict[str, object]:
        return {
            "batch_id": self.batch_id,
            "files_ok": self.dataset.ok,
            "missing_files": self.dataset.missing,
            "findings": len(self.items.findings),
            "unreviewed": self.items.counts_unreviewed(),
            "handovers": len(self.checks),
            "by_type": self.items.counts_by_type(),
            "out_of_scope": self.excluded_shifts,
            "blocked": self.blocked,
            "warnings": self.warnings,
        }


def _in_scope_shifts(shifts, positions_index, excluded_categories) -> tuple:
    in_scope = set()
    excluded = []
    for shift in shifts:
        position = positions_index.get(shift.get("position_id"))
        category = position.data.get("category", "") if position is not None else ""
        if category and category in excluded_categories:
            excluded.append(f"{shift.get('shift_id')}({shift.get('position_id')} {category})")
            continue
        if shift.get("shift_id"):
            in_scope.add(shift.get("shift_id"))
    return in_scope, excluded


def run(data_dir, config: Optional[dict] = None) -> RunResult:
    cfg = config or {}
    audit = AuditLog()

    pilot = cfg.get("pilot") or {}
    scope = cfg.get("scope") or {}
    boundary_cfg = cfg.get("boundary") or {}
    output = cfg.get("output") or {}

    batch_id = str(pilot.get("batch_id") or "UNKNOWN-BATCH")
    page_limit = int(output.get("max_page_items", pilot.get("page_item_limit", 40)))
    as_of = parse_ts(str((cfg.get("time") or {}).get("as_of") or ""))

    audit.record("run.start", str(data_dir), note=f"batch={batch_id}")

    dataset = load_dataset(data_dir)
    for snap in dataset.snapshots:
        audit.record(
            "read",
            snap.file_name,
            version=snap.sha256 or "unavailable",
            note=f"rows={snap.rows} status={snap.status} at={snap.taken_at}",
        )

    positions_index = index_by(dataset.get("positions.csv"), "position_id")
    shift_index = index_by(dataset.get("shifts.csv"), "shift_id")
    in_scope, excluded = _in_scope_shifts(
        dataset.get("shifts.csv"), positions_index, scope.get("excluded_position_categories") or []
    )

    checks = build_checklist(dataset.get("handover.csv"), shift_index, as_of)
    boundary = Boundary.from_config(boundary_cfg)

    items = ItemSheet(batch_id=batch_id, page_limit=page_limit)
    items.out_of_scope = excluded
    items.extend(all_checks(dataset, positions_index, in_scope, boundary, cfg, checks))
    # 现场类异常受白名单约束；治理类（版本/编号/失败/边界）始终保留
    items.filtered(scope.get("allowed_anomaly_types"))

    warnings: List[str] = []
    warn = items.page_warning()
    if warn:
        warnings.append(warn)
    if not dataset.available("checkins.csv"):
        warnings.append("签到记录不可读：缺岗与点位一致性判断已跳过——这不等于没有缺岗（C8）")
    if not dataset.available("handover.csv"):
        warnings.append("交接记录不可读：交接责任清单本次为空——不等于没有交接问题（C8）")
    if dataset.missing:
        warnings.append(
            "缺失文件：" + "、".join(dataset.missing) + " —— 本次结论不覆盖这些文件，也未沿用上次结果"
        )

    blocked_reason = ""
    if boundary.violations():
        blocked_reason = "配置中出现禁用能力：" + "、".join(k for k, _ in boundary.violations())

    audit.record("run.finish", f"{len(items.findings)} findings", note=f"blocked={bool(blocked_reason)}")
    return RunResult(
        batch_id=batch_id,
        dataset=dataset,
        items=items,
        checks=checks,
        audit=audit,
        as_of=as_of,
        blocked_reason=blocked_reason,
        warnings=warnings,
        excluded_shifts=excluded,
    )


def write_outputs(result: RunResult, out_dir) -> Dict[str, Path]:
    """写出全部产物。只写 out/ 目录，不触碰 data/ 与原始导出。"""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "items_csv": out / "items.csv",
        "items_md": out / "items.md",
        "handover_md": out / "handover.md",
        "snapshots_csv": out / "snapshots.csv",
        "audit_csv": out / "audit.csv",
    }
    result.items.to_csv(paths["items_csv"])
    paths["items_md"].write_text(result.items.render_markdown(), encoding="utf-8")
    paths["handover_md"].write_text(render_handover(result.checks, result.batch_id), encoding="utf-8")
    from .trace import write_snapshots

    write_snapshots(result.dataset.snapshots, paths["snapshots_csv"])
    result.audit.to_csv(paths["audit_csv"])
    return paths
