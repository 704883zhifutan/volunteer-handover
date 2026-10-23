"""金标比对：把"发现全部重叠"从一句口号变成可算的数。

背景
----
方案里 W3 的验收是"回放 50 次调班，能从里面还原出全部重叠"。
但"全部"需要一个分母，否则这句话永远无法判定真假——
这正是报告里最容易被含糊过去的一处。

所以这里要求先有一张人标过的表（data/gold_overlap.csv）：

    shift_a,shift_b,是否真重叠,标注人
    S004,S005,是,傅景
    S001,S003,否,傅景

然后：
- **召回** = 工具报出的真重叠 / 金标里的全部真重叠。这是 G1 的唯一判别依据。
- **精确** = 工具报对的 / 工具报出的。分母只算金标明确标过"否"的。
- **未标注** = 工具报出、但金标没标过这一对。单独列出来，**不算误报**——
  没标注不等于没异常，把它算成误报会让人误以为该收窄条件。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

from ..utils.csvio import read_rows
from .items import Finding

GOLD_COLUMNS = ("shift_a", "shift_b", "是否真重叠", "标注人")
_TRUE = {"是", "y", "yes", "true", "1", "重叠", "有"}
_FALSE = {"否", "n", "no", "false", "0", "不重叠", "无"}

Pair = Tuple[str, str]


def _pair(a: str, b: str) -> Pair:
    a, b = a.strip(), b.strip()
    return (a, b) if a <= b else (b, a)


@dataclass(frozen=True)
class GoldPair:
    a: str
    b: str
    overlaps: bool
    annotator: str = ""
    locator: str = ""

    @property
    def key(self) -> Pair:
        return _pair(self.a, self.b)


@dataclass(frozen=True)
class GoldProblem:
    locator: str
    reason: str


@dataclass
class ScoreResult:
    gold_true: int = 0
    gold_false: int = 0
    tool_pairs: int = 0
    tp: int = 0
    fn: int = 0
    fp: int = 0
    unlabeled: List[Pair] = field(default_factory=list)
    missed: List[GoldPair] = field(default_factory=list)
    false_alarms: List[GoldPair] = field(default_factory=list)
    problems: List[GoldProblem] = field(default_factory=list)

    @property
    def recall(self) -> Optional[float]:
        total = self.tp + self.fn
        return None if total == 0 else self.tp / total

    @property
    def precision(self) -> Optional[float]:
        total = self.tp + self.fp
        return None if total == 0 else self.tp / total

    @property
    def g1_ready(self) -> bool:
        """G1 能否关闭：金标覆盖足够、召回 100%、且没有未标注的工具结论。"""
        return self.recall == 1.0 and not self.unlabeled and self.gold_true > 0


def parse_gold(rows: Iterable) -> Tuple[List[GoldPair], List[GoldProblem]]:
    pairs: List[GoldPair] = []
    problems: List[GoldProblem] = []
    for row in rows:
        a, b = row.get("shift_a"), row.get("shift_b")
        truth = row.get("是否真重叠")
        if not a or not b:
            problems.append(GoldProblem(row.locator, "缺班次号：无法组成一对"))
            continue
        if a == b:
            problems.append(GoldProblem(row.locator, f"同一班次 {a} 与自己配对，忽略"))
            continue
        if truth not in _TRUE and truth not in _FALSE:
            problems.append(
                GoldProblem(row.locator, f"「是否真重叠」取值「{truth or '空'}」无法判定，只认 是/否")
            )
            continue
        pairs.append(
            GoldPair(a=a, b=b, overlaps=truth in _TRUE, annotator=row.get("标注人"), locator=row.locator)
        )
    return pairs, problems


def load_gold(path) -> Tuple[List[GoldPair], List[GoldProblem]]:
    p = Path(path)
    if not p.exists():
        return [], [GoldProblem(str(p), "金标文件不存在：没有标注就无法算召回，G1 无法关闭")]
    return parse_gold(read_rows(p))


def extract_pairs(findings: Iterable[Finding], code: str = "C2") -> Dict[Pair, Finding]:
    """从缺项条目里取出"成对"的结论（默认 C2 占位冲突）。"""
    out: Dict[Pair, Finding] = {}
    for f in findings:
        if f.code != code:
            continue
        parts = [p.strip() for p in f.refs.split(",") if p.strip()]
        if len(parts) < 2:
            continue
        for i in range(len(parts)):
            for j in range(i + 1, len(parts)):
                out.setdefault(_pair(parts[i], parts[j]), f)
    return out


def score(gold: List[GoldPair], findings: Iterable[Finding], code: str = "C2") -> ScoreResult:
    tool = extract_pairs(findings, code)
    gold_index: Dict[Pair, GoldPair] = {}
    for g in gold:
        gold_index.setdefault(g.key, g)

    result = ScoreResult(
        gold_true=sum(1 for g in gold if g.overlaps),
        gold_false=sum(1 for g in gold if not g.overlaps),
        tool_pairs=len(tool),
    )
    for key, finding in tool.items():
        labeled = gold_index.get(key)
        if labeled is None:
            result.unlabeled.append(key)
        elif labeled.overlaps:
            result.tp += 1
        else:
            result.fp += 1
            result.false_alarms.append(labeled)
    for key, g in gold_index.items():
        if g.overlaps and key not in tool:
            result.fn += 1
            result.missed.append(g)
    return result


def _pct(value: Optional[float]) -> str:
    return "无法计算" if value is None else f"{value * 100:.1f}%"


def render_markdown(result: ScoreResult, batch_id: str = "", gold_path: str = "") -> str:
    lines = [
        f"# 金标比对 · 批次 {batch_id or '（未标注）'}",
        "",
        f"- 生成时间：{datetime.now().isoformat(timespec='seconds')}",
        f"- 金标文件：{gold_path or '（未提供）'}",
        f"- 比对校验：C2 占位冲突",
        "",
        "## 结果",
        "",
        "| 项目 | 数值 |",
        "|---|---|",
        f"| 金标真重叠对数 | {result.gold_true} |",
        f"| 金标非重叠对数 | {result.gold_false} |",
        f"| 工具报出对数 | {result.tool_pairs} |",
        f"| 命中（真正例） | {result.tp} |",
        f"| 漏报 | {result.fn} |",
        f"| 误报 | {result.fp} |",
        f"| 金标未覆盖 | {len(result.unlabeled)} |",
        f"| **召回率** | {_pct(result.recall)} |",
        f"| 精确率 | {_pct(result.precision)} |",
        "",
    ]

    if result.missed:
        lines += ["## 漏报（金标说真重叠，工具没发现）", ""]
        for g in result.missed:
            lines.append(f"- {g.key[0]} ↔ {g.key[1]}（标注人 {g.annotator or '未写'}，{g.locator}）")
        lines.append("")
    if result.false_alarms:
        lines += ["## 误报（金标说不是重叠，工具报了）", ""]
        for g in result.false_alarms:
            lines.append(f"- {g.key[0]} ↔ {g.key[1]}（标注人 {g.annotator or '未写'}，{g.locator}）")
        lines.append("")
    if result.unlabeled:
        lines += ["## 金标未覆盖（工具报了，但没人标过这一对）", ""]
        for a, b in result.unlabeled:
            lines.append(f"- {a} ↔ {b}")
        lines += ["", "> 这些既不算命中也不算误报。想关 G1，先把它们补进金标。", ""]
    if result.problems:
        lines += ["## 金标格式问题", ""]
        for p in result.problems:
            lines.append(f"- {p.locator}：{p.reason}")
        lines.append("")

    lines += ["## 能不能关 G1", ""]
    if result.g1_ready:
        lines += ["可以：金标里全部真重叠都被发现，且工具没有报出任何未标注的对。", ""]
    else:
        reasons = []
        if result.gold_true == 0:
            reasons.append("金标里没有一条真重叠（分母为 0）")
        if result.recall is not None and result.recall < 1.0:
            reasons.append(f"召回 {_pct(result.recall)}，还有 {result.fn} 对真重叠没发现")
        if result.unlabeled:
            reasons.append(f"{len(result.unlabeled)} 对结论金标没覆盖")
        if result.problems:
            reasons.append(f"{len(result.problems)} 条金标格式问题")
        lines += ["**还不能关闭**：" + "；".join(reasons or ["样本不足"]) + "。", ""]
    return "\n".join(lines)
