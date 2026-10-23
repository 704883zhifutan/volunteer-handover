"""只读加载。

两条规则来自访谈事实：

- f35：**读取失败保留快照并标记时间，不编造"最新状态"，也不悄悄重试。**
  所以这里不抛异常中断，而是把失败变成一条可见的记录，让缺项清单自己说出来。
- f31/f33：关键字段缺失必须能被看见。
  所以表头单独校验（core/schema.py）：缺必需列就阻断，缺可选列就跳过对应判断。

注意"读到 0 行"与"没读到"是两回事：前者说明当天确实没有记录，后者说明这次没看到。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List

from ..utils.csvio import Row, read_table
from .schema import ColumnCheck, check_columns
from .trace import Snapshot, take_snapshot

DEFAULT_FILES = ("positions.csv", "shifts.csv", "checkins.csv", "handover.csv")


@dataclass
class Dataset:
    root: str
    rows: Dict[str, List[Row]] = field(default_factory=dict)
    snapshots: List[Snapshot] = field(default_factory=list)
    missing: List[str] = field(default_factory=list)
    columns: Dict[str, ColumnCheck] = field(default_factory=dict)

    def get(self, file_name: str) -> List[Row]:
        return self.rows.get(file_name, [])

    def available(self, file_name: str) -> bool:
        """文件读到了才算可用；"读到 0 行"与"没读到"是两回事。"""
        return file_name not in self.missing

    @property
    def ok(self) -> bool:
        return not self.missing

    def blocked_columns(self) -> List[ColumnCheck]:
        """缺必需列的文件——这些文件得出的结论不可信。"""
        return [c for c in self.columns.values() if not c.ok]

    def column_warnings(self) -> List[str]:
        """缺可选列的警告：只影响某一项判断，不阻断。"""
        out: List[str] = []
        for check in self.columns.values():
            if check.ok and check.missing_optional:
                out.append(
                    f"{check.file_name} 缺少可选列 {'、'.join(check.missing_optional)}：对应判断已跳过，"
                    "这不等于那些判断的结果是「无异常」"
                )
        return out


def load_dataset(data_dir, files: Iterable[str] = DEFAULT_FILES) -> Dataset:
    root = Path(data_dir)
    dataset = Dataset(root=str(root))
    for name in files:
        path = root / name
        try:
            header, rows = read_table(path)
        except (OSError, UnicodeDecodeError):
            dataset.missing.append(name)
            dataset.rows[name] = []
            # take_snapshot 自己会返回 status=unavailable 并带上读取时间
            dataset.snapshots.append(take_snapshot(path, row_count=0))
            continue
        dataset.rows[name] = rows
        dataset.columns[name] = check_columns(name, header)
        dataset.snapshots.append(take_snapshot(path, row_count=len(rows)))
    return dataset


def index_by(rows: Iterable[Row], key: str) -> Dict[str, Row]:
    out: Dict[str, Row] = {}
    for row in rows:
        value = row.get(key)
        if value and value not in out:
            out[value] = row
    return out
