"""只读 CSV 读取。

每个结果行都带 locator（`文件名#L物理行号`），这样任何结论都能一跳回到原始行。
这是"可追溯"的最小实现：不是给人看的描述，是可定位的坐标。
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List


@dataclass(frozen=True)
class Row:
    data: Dict[str, str]
    locator: str          # 例：shifts.csv#L5
    file_name: str
    line_no: int

    def get(self, key: str, default: str = "") -> str:
        value = self.data.get(key, default)
        return default if value is None else value


def read_rows(path) -> List[Row]:
    """读取 CSV。第一行为表头，数据从物理第 2 行开始。"""
    p = Path(path)
    rows: List[Row] = []
    with p.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            return rows
        for offset, record in enumerate(reader, start=2):
            clean = {
                (k or "").strip(): (v if isinstance(v, str) else ("" if v is None else str(v))).strip()
                for k, v in record.items()
            }
            rows.append(Row(data=clean, locator=f"{p.name}#L{offset}", file_name=p.name, line_no=offset))
    return rows
