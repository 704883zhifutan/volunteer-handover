#!/usr/bin/env python3
"""金标比对：算出召回率与精确率，并回答"G1 能不能关"。

用法：
    python3 scripts/score.py --items out/items.csv --gold data/gold_overlap.csv
    python3 scripts/score.py --gold data/gold_overlap.csv --out out/score.md

金标格式（data/gold_overlap.csv）：
    shift_a,shift_b,是否真重叠,标注人,备注
    S004,S005,是,傅景,同一替补被排在两个点位

判定规则：
- 召回 = 工具发现的真重叠 / 金标里全部真重叠。这是 G1 的唯一判别依据。
- 精确 = 工具报对 / 工具报出的（分母只算金标明确标过"否"的）。
- 工具报了、但金标没标过这一对 → 记"金标未覆盖"，不算误报，单独列出。
  没标注不等于没异常；把它算成误报会让人误以为该收窄条件。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from volunteer_handover.core.gold import load_gold, render_markdown, score  # noqa: E402
from volunteer_handover.core.items import finding_from_row  # noqa: E402
from volunteer_handover.utils.csvio import read_rows  # noqa: E402


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(description="金标比对：召回率 / 精确率 / G1 判定")
    parser.add_argument("--items", default="out/items.csv", help="缺项清单（默认 out/items.csv）")
    parser.add_argument("--gold", default="data/gold_overlap.csv", help="金标标注表")
    parser.add_argument("--code", default="C2", help="比对哪条校验（默认 C2 占位冲突）")
    parser.add_argument("--out", default="out/score.md", help="Markdown 输出路径")
    parser.add_argument("--batch", default="", help="批次号（仅用于标题）")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)
    gold_pairs, gold_problems = load_gold(args.gold)
    findings = []
    items_path = Path(args.items)
    if items_path.exists():
        findings = [finding_from_row(row) for row in read_rows(items_path)]

    result = score(gold_pairs, findings, code=args.code)
    result.problems.extend(gold_problems)

    recall = "无法计算" if result.recall is None else f"{result.recall * 100:.1f}%"
    precision = "无法计算" if result.precision is None else f"{result.precision * 100:.1f}%"
    print(f"金标 {result.gold_true} 对真重叠 / {result.gold_false} 对非重叠；工具报出 {result.tool_pairs} 对")
    print(f"  命中 {result.tp} · 漏报 {result.fn} · 误报 {result.fp} · 金标未覆盖 {len(result.unlabeled)}")
    print(f"  召回 {recall} · 精确 {precision}")
    print(f"  G1（能不能说“发现全部重叠”）：{'可以关闭' if result.g1_ready else '还不能关闭'}")

    for pair in result.missed:
        print(f"  漏报：{pair.key[0]} ↔ {pair.key[1]}（{pair.locator}）")
    for pair in result.unlabeled:
        print(f"  未标注：{pair[0]} ↔ {pair[1]}")
    for problem in result.problems:
        print(f"  金标问题：{problem.locator} {problem.reason}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_markdown(result, args.batch, args.gold), encoding="utf-8")
    print()
    print(f"已写出 {out}")
    return 0 if result.g1_ready else 3


if __name__ == "__main__":
    raise SystemExit(main())
