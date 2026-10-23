"""W0 桌面推演：用虚构样本走一遍"调班 → 发现 → 核对 → 确认"。

对应方案 §4 的 W0 门禁：不做系统改动，只用假数据验证两件事——
1. 一条缺项能不能从原始行一路指到具体位置（可追溯）；
2. 人机分工有没有越界（系统只提示，人确认）。

运行：
    PYTHONPATH=src python3 examples/demo.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from volunteer_handover.core.engine import run  # noqa: E402
from volunteer_handover.utils import config as config_util  # noqa: E402

LINE = "─" * 72


def title(text: str) -> None:
    print()
    print(LINE)
    print(text)
    print(LINE)


def main() -> int:
    config = config_util.load(ROOT / "config" / "default.yaml")
    result = run(ROOT / "data", config)
    items = result.items.findings

    title("场景（虚构）：2026-10-03 上午，补给站志愿者 Z0007 没出现在安排的点位")
    print("林亦舟（现场协调员）的说法：早上 9 点补给站没人，Z0007 说自己在咨询台。")
    print("唐映秋（流程协调员）的说法：排班表上 Z0007 在补给站。")
    print("两人的说法都对，因为表里确实有两行都写着 Z0007。")
    print()
    print("下面不是判断谁对，而是把'两边对不上'这件事定位到行。")

    title("L0 系统只提示：Z0007 的时间窗重叠")
    doubles = [f for f in items if f.type == "疑似重复占位"]
    if not doubles:
        print("（本批次没有重复占位，说明数据或校验被改过，请检查）")
    for finding in doubles:
        print(f"  对象    {finding.subject}")
        print(f"  事实    {finding.detail}")
        print(f"  位置    {finding.source_locator}")
        print(f"  建议    {finding.suggestion}")
        print(f"  复核    {finding.review_status} ← 系统到此为止，不替人做决定")
        break

    title("同一个人的两种记录：排班说 S-D，签到说 S-A")
    for finding in [f for f in items if f.type == "排班表与现场不一致"]:
        print(f"  {finding.subject}  {finding.detail}")
        print(f"  位置  {finding.source_locator}")

    title("版本问题：v3 已被 v4 替代，但交接仍按 v3 进行")
    for finding in [f for f in items if f.type in ("版本断链或过期", "版本未确认")]:
        print(f"  {finding.code} {finding.type}  {finding.subject}")
        print(f"       {finding.detail}")
        print(f"       位置 {finding.source_locator}")

    title("L1 → L2：人怎么接手（代码不参与这一步）")
    print("  L1 当班人员核对：打开 locator 指向的原始行，确认 Z0007 实际在哪。")
    print("  L2 业务负责人确认：决定是否改派、是否补签到、是否记为缺岗。")
    print("  L3 人工队列：核对不了的进队列，不默认通过；必要时暂停试点。")
    print()
    print("  本项目能做的到 L0 为止：给行号、给事实、给建议文字。")
    print("  改派与补录只能发生在业务系统里，由有权限的人操作。")

    title("本次推演结果")
    print(f"  缺项 {len(items)} 条，全部带来源位置；未复核 {result.items.counts_unreviewed()} 条")
    for kind, count in result.items.counts_by_type().items():
        print(f"    {kind:12s} {count}")
    print()
    print(f"  范围外已排除：{'、'.join(result.excluded_shifts) or '无'}")
    print("  说明：医疗与安保岗位不进入试点，也不做自动指派（f05）。")
    for warning in result.warnings:
        print(f"  ⚠️  {warning}")

    title("门禁自查（三门禁未关不进入 W1）")
    gates = [
        ("G1 判定方法", "缺失：'发现全部重叠'的判定人与抽样方式待傅景、秦芮确认", False),
        ("G2 值守与叫停", "缺失：队列值守人、响应时限、暂停批准人待确认", False),
        ("G3 '完成'的定义", "缺失：是否包含交接确认，待顾明岚、唐映秋确认", False),
    ]
    for name, note, ok in gates:
        print(f"  [{'x' if ok else ' '}] {name}  {note}")
    print()
    print("  三门禁为未关闭状态时，本工具只能跑桌面推演，不能进现场。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
