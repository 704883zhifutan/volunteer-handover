"""命令行入口。

用法（二选一，都只用标准库）：
    PYTHONPATH=src python3 -m volunteer_handover.main
    python3 src/volunteer_handover/main.py

退出码：
    0  正常产出（可能有缺项，但流程完整）
    2  配置越界（出现写回/外发/自动指派能力），运行被标记为 blocked
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

if __package__ in (None, ""):  # 允许直接 python3 运行本文件
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from volunteer_handover import __version__            # noqa: E402
from volunteer_handover.core.engine import run, write_outputs  # noqa: E402
from volunteer_handover.utils import config as config_util      # noqa: E402

DEFAULT_FILES = ("positions.csv", "shifts.csv", "checkins.csv", "handover.csv")


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="volunteer-handover",
        description="志愿者班次交接 · 只读核对（不出建议以外的任何动作）",
    )
    parser.add_argument("--data", default="data", help="脱敏导出目录（默认 data/）")
    parser.add_argument("--config", default="config/default.yaml", help="配置文件路径")
    parser.add_argument("--out", default="out", help="产物输出目录（默认 out/）")
    parser.add_argument("--max-print", type=int, default=8, help="终端最多打印几条（默认 8）")
    parser.add_argument("--json", action="store_true", help="额外打印机器可读的摘要")
    parser.add_argument(
        "--simulate-failure",
        action="append",
        default=[],
        metavar="FILE",
        help="模拟某文件读取失败（演示 C8 失败即标记），可重复",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser.parse_args(argv)


def _with_simulated_failure(data_dir: str, failing) -> str:
    """建一个临时目录，把正常文件软链过去，故意缺几个——用来演示"失败即标记"。"""
    tmp = Path(tempfile.mkdtemp(prefix="vh-fail-"))
    for name in DEFAULT_FILES:
        if name in failing:
            continue
        src = Path(data_dir) / name
        if src.exists():
            os.symlink(src.resolve(), tmp / name)
    return str(tmp)


def main(argv=None) -> int:
    args = _parse_args(argv)
    cfg = config_util.load(args.config)

    data_dir = args.data
    tmp_dir = None
    if args.simulate_failure:
        tmp_dir = _with_simulated_failure(args.data, set(args.simulate_failure))
        data_dir = tmp_dir

    try:
        result = run(data_dir, cfg)
        paths = write_outputs(result, args.out)
    finally:
        if tmp_dir:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    summary = result.summary()
    print(f"批次 {summary['batch_id']} · 只读核对完成 · {summary['findings']} 条待复核")
    print(f"  交接责任清单：{summary['handovers']} 条")
    print(f"  范围外已排除：{len(summary['out_of_scope'])} 个班次（医疗/安保不进入试点）")
    if summary["by_type"]:
        print("  按类型：" + "、".join(f"{k} {v}" for k, v in summary["by_type"].items()))
    print()

    if result.items.findings:
        print(result.items.render_text(max_rows=args.max_print))
        print()

    for warning in result.warnings:
        print(f"⚠️  {warning}")
    if result.blocked:
        print(f"⛔ 运行被阻断：{result.blocked_reason}")
    print()
    print("产物：")
    for key, path in paths.items():
        print(f"  {key:14s} {path}")
    print()
    print("提醒：清单只是待复核建议，不写回任何系统；确认动作由当班负责人完成（L2）。")

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))

    return 2 if result.blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
