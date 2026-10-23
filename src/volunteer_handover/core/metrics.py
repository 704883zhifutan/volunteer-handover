"""把复核结果算成能拿去会议上的数字。

算的是三件事，对应方案里的 S2/S5 和"复核滞后"：

1. **误报率** = 已驳回 / 已复核。分母是"人实际核过的"，不是"全部条目"——
   拿未复核的当误报会把数字做得很好看，但那是假的。
2. **确认完整率** = 已确认 / 全部条目。这是硬门：试点要求 100%，
   因为每一条没确认的缺项，在交接现场就等于没人负责。
3. **复核滞后** = 复核时间 − 本次生成时间。它不是工时，只是"压了多久"。

没复核的样本一律不算进比率，并显式写出"样本不足"——
宁可说"还不能算"，也不给一个看着精确其实没分母的百分比。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Tuple

from .items import Finding
from .times import gap_minutes, parse_ts


@dataclass
class TypeStat:
    type: str
    total: int = 0
    confirmed: int = 0
    rejected: int = 0
    queued: int = 0

    @property
    def reviewed(self) -> int:
        return self.confirmed + self.rejected + self.queued

    @property
    def rejected_rate(self) -> Optional[float]:
        return None if self.reviewed == 0 else self.rejected / self.reviewed


@dataclass
class Metrics:
    total: int = 0
    confirmed: int = 0
    rejected: int = 0
    queued: int = 0
    unreviewed: int = 0
    by_type: List[TypeStat] = field(default_factory=list)
    lag_hours: List[float] = field(default_factory=list)
    lag_anomalies: List[float] = field(default_factory=list)
    run_at: str = ""

    @property
    def reviewed(self) -> int:
        return self.confirmed + self.rejected + self.queued

    @property
    def false_positive_rate(self) -> Optional[float]:
        """已驳回 / 已复核。没有已复核样本时返回 None（不是 0）。"""
        return None if self.reviewed == 0 else self.rejected / self.reviewed

    @property
    def confirmed_rate(self) -> Optional[float]:
        """已确认 / 全部条目。这是硬门指标，分母必须是全部。"""
        return None if self.total == 0 else self.confirmed / self.total

    @property
    def noisy_types(self) -> List[TypeStat]:
        """被驳回过的类型，按驳回率从高到低。用来决定下一轮收窄哪一类。"""
        return sorted(
            [t for t in self.by_type if t.rejected],
            key=lambda t: (-(t.rejected_rate or 0.0), -t.rejected),
        )

    def lag_summary(self) -> Tuple[Optional[float], Optional[float]]:
        if not self.lag_hours:
            return None, None
        return sum(self.lag_hours) / len(self.lag_hours), max(self.lag_hours)


def _pct(value: Optional[float]) -> str:
    return "样本不足，暂不计算" if value is None else f"{value * 100:.1f}%"


def compute(findings: Iterable[Finding], run_at: str = "") -> Metrics:
    findings = list(findings)
    m = Metrics(total=len(findings), run_at=run_at)
    per_type: Dict[str, TypeStat] = {}
    start = parse_ts(run_at) if run_at else None

    for f in findings:
        stat = per_type.setdefault(f.type, TypeStat(type=f.type))
        stat.total += 1
        if f.review_status == "已确认":
            stat.confirmed += 1
            m.confirmed += 1
        elif f.review_status == "已驳回":
            stat.rejected += 1
            m.rejected += 1
        elif f.review_status == "转人工队列":
            stat.queued += 1
            m.queued += 1
        else:
            m.unreviewed += 1

        if start is not None and f.review_at:
            reviewed_at = parse_ts(f.review_at)
            if reviewed_at is not None:
                minutes = gap_minutes(start, reviewed_at)
                if minutes is None:
                    continue
                # 复核时间早于本次运行：多半是把复核时间填成了业务当天。
                # 不钳成 0，也不计入平均——把它单独列出来，让填错的人看见。
                if minutes < 0:
                    m.lag_anomalies.append(minutes / 60.0)
                else:
                    m.lag_hours.append(minutes / 60.0)

    m.by_type = sorted(per_type.values(), key=lambda t: (-t.total, t.type))
    return m


def render_text(m: Metrics) -> str:
    mean_lag, max_lag = m.lag_summary()
    lines = [
        f"条目 {m.total} 条 · 已复核 {m.reviewed} 条 · 未复核 {m.unreviewed} 条",
        f"  误报率（已驳回/已复核）：{_pct(m.false_positive_rate)}",
        f"  确认率（已确认/全部，试点硬门 100%）：{_pct(m.confirmed_rate)}",
    ]
    if mean_lag is None:
        lines.append("  复核滞后：暂无可算样本")
    else:
        lines.append(f"  复核滞后：平均 {mean_lag:.1f} 小时，最长 {max_lag:.1f} 小时（不是工时，只是压了多久）")
    if m.lag_anomalies:
        lines.append(f"  ⚠️ {len(m.lag_anomalies)} 条复核时间早于本次运行，未计入平均：请确认是不是把复核时间填成了业务当天")
    if m.unreviewed:
        lines.append(f"  ⚠️ 还有 {m.unreviewed} 条未复核：以上比率只覆盖已复核部分，不能当整体结论")
    return "\n".join(lines)


def render_markdown(m: Metrics, batch_id: str = "") -> str:
    mean_lag, max_lag = m.lag_summary()
    lines = [
        f"# 复核指标 · 批次 {batch_id or '（未标注）'}",
        "",
        f"- 生成时间：{datetime.now().isoformat(timespec='seconds')}",
        f"- 本次运行时间：{m.run_at or '（未提供）'}",
        "",
        "## 口径",
        "",
        "- 误报率 = 已驳回 / 已复核。分母是**人实际核过的**，未复核的不进分母，也不算误报。",
        "- 确认率 = 已确认 / 全部条目。试点要求 100%：每条没确认的缺项，在现场就等于没人负责。",
        "- 复核滞后 = 复核时间 − 本次运行时间。它是滞后，不是工时；工时要靠人记录。",
        "- 本文件不产生任何动作，只描述已发生的人工复核结果。",
        "",
        "## 总览",
        "",
        "| 项目 | 数值 |",
        "|---|---|",
        f"| 条目总数 | {m.total} |",
        f"| 已复核 | {m.reviewed} |",
        f"| 未复核 | {m.unreviewed} |",
        f"| 已确认 | {m.confirmed} |",
        f"| 已驳回（误报） | {m.rejected} |",
        f"| 转人工队列 | {m.queued} |",
        f"| 误报率 | {_pct(m.false_positive_rate)} |",
        f"| 确认率 | {_pct(m.confirmed_rate)} |",
        f"| 复核滞后（平均/最长） | "
        + ("暂无可算样本" if mean_lag is None else f"{mean_lag:.1f} / {max_lag:.1f} 小时")
        + " |",
        "",
    ]
    if m.unreviewed:
        lines += [f"> ⚠️ 还有 {m.unreviewed} 条未复核。上面的比率只覆盖已复核部分，不能当整体结论。", ""]
    if m.lag_anomalies:
        lines += [
            f"> ⚠️ {len(m.lag_anomalies)} 条复核时间早于本次运行，未计入平均滞后："
            "请确认是不是把复核时间填成了业务当天。",
            "",
        ]

    lines += [
        "## 按异常类型",
        "",
        "| 类型 | 条目 | 已确认 | 已驳回 | 转人工 | 驳回率 |",
        "|---|---|---|---|---|---|",
    ]
    for stat in m.by_type:
        lines.append(
            f"| {stat.type} | {stat.total} | {stat.confirmed} | {stat.rejected} | {stat.queued} | "
            f"{_pct(stat.rejected_rate)} |"
        )
    lines.append("")

    noisy = m.noisy_types
    if noisy:
        names = "、".join(f"{t.type}（{t.rejected}/{t.reviewed}）" for t in noisy[:3])
        lines += [
            "## 下一步该收窄哪一类",
            "",
            f"驳回集中在：{names}。按设计，一页装不下、噪声压不住时应当**收窄触发条件或提高门槛**，"
            "而不是加页——所以下一轮先动这三类，别动清单结构。",
            "",
        ]
    return "\n".join(lines)
