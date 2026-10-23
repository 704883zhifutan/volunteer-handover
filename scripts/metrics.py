#!/usr/bin/env python3
"""离线复算复核指标：从 out/items.csv + data/review.csv 算出误报率与确认率。

为什么单独给一个脚本
--------------------
`main.py --review` 已经会在跑核对时顺带算，但复盘时更常见的场景是：
清单是昨天导的、复核是今天才补的，这时候不想重跑核对，只想重算数。
所以这里读的是已经落盘的 CSV，不重新读 data/ 里的原始导出。

用法：
    python3 scripts/metrics.py --items out/items.csv --review data/review.csv
    python3 scripts/metrics.py --items out/items.csv --review data/review.csv --out out/metrics.md
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from volunteer_handover.core.items import finding_from_row  # noqa: E402
from volunteer_handover.core.metrics import compute, render_markdown, render_text  # noqa: E402
from volunteer_handover.core.review import apply_reviews, load_reviews  # noqa: E402
from volunteer_handover.utils.csvio import read_rows  # noqa: E402


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(description="复核指标：误报率 / 确认率 / 复核滞后")
    parser.add_argument("--items", default="out/items.csv", help="缺项清单（默认 out/items.csv）")
    parser.add_argument("--review", default="data/review.csv", help="人工复核回填表")
    parser.add_argument("--run-at", default="", help="清单生成时间（默认取 items.csv 文件修改时间）")
    parser.add_argument("--out", default="out/metrics.md", help="Markdown 输出路径")
    parser.add_argument("--batch", default="", help="批次号（仅用于标题）")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)
    items_path = Path(args.items)
    if not items_path.exists():
        print(f"找不到 {items_path}：请先跑一次核对（python3 -m volunteer_handover.main）", file=sys.stderr)
        return 2

    findings = [finding_from_row(row) for row in read_rows(items_path)]
    entries, problems = load_reviews(args.review)
    applied = apply_reviews(findings, entries)
    applied.problems.extend(problems)

    run_at = args.run_at or datetime.fromtimestamp(items_path.stat().st_mtime).isoformat(timespec="seconds")
    metrics = compute(findings, run_at)

    print(render_text(metrics))
    if applied.applied or applied.unmatched or problems:
        print()
        print(f"回填：{applied.note()}")
        for entry in applied.unmatched:
            print(f"  对不上：{entry.fid}（{entry.locator}）——数据可能已变，需重新核对")
        for problem in applied.problems:
            print(f"  格式问题：{problem.locator} {problem.reason}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_markdown(metrics, args.batch), encoding="utf-8")
    print()
    print(f"已写出 {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
