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
from .metrics import Metrics, compute as compute_metrics, render_markdown as render_metrics
from .review import ReviewApply, apply_reviews, load_reviews
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
    review: Optional[ReviewApply] = None
    metrics: Optional[Metrics] = None
    run_at: str = ""

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
            "reviewed": self.review.reviewed if self.review else 0,
            "false_positive_rate": (
                None if self.metrics is None else self.metrics.false_positive_rate
            ),
            "confirmed_rate": None if self.metrics is None else self.metrics.confirmed_rate,
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


def run(data_dir, config: Optional[dict] = None, review_path=None, run_at: str = "") -> RunResult:
    """run_at = 清单生成时间。默认取当前时间；回放历史批次时应显式给出，
    否则"复核滞后"会用今天去减去年的复核时间，算出没有意义的负数。"""
    cfg = config or {}
    audit = AuditLog()
    run_at = run_at or datetime.now().isoformat(timespec="seconds")

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

    warnings.extend(dataset.column_warnings())

    blocked_reason = ""
    if boundary.violations():
        blocked_reason = "配置中出现禁用能力：" + "、".join(k for k, _ in boundary.violations())
    bad_columns = dataset.blocked_columns()
    if bad_columns:
        column_reason = "表头契约不满足，本次不出结论：" + "；".join(c.describe() for c in bad_columns)
        blocked_reason = f"{blocked_reason}；{column_reason}" if blocked_reason else column_reason

    review_result = None
    if review_path:
        entries, problems = load_reviews(review_path)
        review_result = apply_reviews(items.findings, entries)
        review_result.problems.extend(problems)
        items.review_note = review_result.note()
        for problem in review_result.problems:
            warnings.append(f"复核回填问题：{problem.locator} {problem.reason}")
        for entry in review_result.unmatched:
            warnings.append(
                f"复核结论对不上：{entry.fid}（{entry.locator}）。数据可能已变，编号已重新生成，"
                "这条结论没有生效，需要重新核对"
            )
        audit.record(
            "review.import",
            str(review_path),
            note=f"applied={review_result.applied} unmatched={len(review_result.unmatched)}",
        )

    metrics = compute_metrics(items.findings, run_at)

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
        review=review_result,
        metrics=metrics,
        run_at=run_at,
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
        "metrics_md": out / "metrics.md",
        "metrics_csv": out / "metrics.csv",
    }
    result.items.to_csv(paths["items_csv"])
    paths["items_md"].write_text(result.items.render_markdown(), encoding="utf-8")
    paths["handover_md"].write_text(render_handover(result.checks, result.batch_id), encoding="utf-8")
    from .trace import write_snapshots

    write_snapshots(result.dataset.snapshots, paths["snapshots_csv"])
    result.audit.to_csv(paths["audit_csv"])
    if result.metrics is not None:
        paths["metrics_md"].write_text(
            render_metrics(result.metrics, result.batch_id), encoding="utf-8"
        )
        _write_metrics_csv(result, paths["metrics_csv"])
    return paths


def _write_metrics_csv(result: RunResult, path: Path) -> None:
    """指标落 CSV，方便直接贴进复盘表。比率缺失时写空值，不写 0。"""
    import csv

    m = result.metrics
    with Path(path).open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["指标", "数值"])
        rows = [
            ("条目总数", m.total),
            ("已复核", m.reviewed),
            ("未复核", m.unreviewed),
            ("已确认", m.confirmed),
            ("已驳回", m.rejected),
            ("转人工队列", m.queued),
            ("误报率", "" if m.false_positive_rate is None else f"{m.false_positive_rate:.4f}"),
            ("确认率", "" if m.confirmed_rate is None else f"{m.confirmed_rate:.4f}"),
        ]
        for name, value in rows:
            writer.writerow([name, value])
