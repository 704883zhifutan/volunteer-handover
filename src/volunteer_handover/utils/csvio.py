"""只读 CSV 读取。

每个结果行都带 locator（`文件名#L物理行号`），这样任何结论都能一跳回到原始行。
这是"可追溯"的最小实现：不是给人看的描述，是可定位的坐标。

另外把表头单独交出来（read_table）：缺列必须能被上层看见。
否则少一列会被读成"整列都是空值"，再被三值逻辑解释成"字段缺失"，
最后变成一页看起来像真问题的假缺项。宁可这一趟不出结论。
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class Row:
    data: Dict[str, str]
    locator: str          # 例：shifts.csv#L5
    file_name: str
    line_no: int

    def get(self, key: str, default: str = "") -> str:
        value = self.data.get(key, default)
        return default if value is None else value


def read_table(path) -> Tuple[List[str], List[Row]]:
    """读取 CSV，返回 (表头, 数据行)。表头为空表示文件是空的或只有一行。"""
    p = Path(path)
    rows: List[Row] = []
    with p.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        header = list(reader.fieldnames or [])
        if reader.fieldnames is None:
            return [], rows
        for offset, record in enumerate(reader, start=2):
            clean = {
                (k or "").strip(): (v if isinstance(v, str) else ("" if v is None else str(v))).strip()
                for k, v in record.items()
            }
            rows.append(Row(data=clean, locator=f"{p.name}#L{offset}", file_name=p.name, line_no=offset))
    return [h.strip() for h in header], rows


def read_rows(path) -> List[Row]:
    """读取 CSV。第一行为表头，数据从物理第 2 行开始。"""
    return read_table(path)[1]
