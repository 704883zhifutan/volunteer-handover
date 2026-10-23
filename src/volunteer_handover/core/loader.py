"""只读加载。

一条规则来自访谈事实 f35：**读取失败保留快照并标记时间，不编造"最新状态"，也不悄悄重试。**
所以这里不抛异常中断，而是把失败变成一条可见的记录，让缺项清单自己说出来。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List

from ..utils.csvio import Row, read_rows
from .trace import Snapshot, take_snapshot

DEFAULT_FILES = ("positions.csv", "shifts.csv", "checkins.csv", "handover.csv")


@dataclass
class Dataset:
    root: str
    rows: Dict[str, List[Row]] = field(default_factory=dict)
    snapshots: List[Snapshot] = field(default_factory=list)
    missing: List[str] = field(default_factory=list)

    def get(self, file_name: str) -> List[Row]:
        return self.rows.get(file_name, [])

    def available(self, file_name: str) -> bool:
        """文件读到了才算可用；"读到 0 行"与"没读到"是两回事。"""
        return file_name not in self.missing

    @property
    def ok(self) -> bool:
        return not self.missing


def load_dataset(data_dir, files: Iterable[str] = DEFAULT_FILES) -> Dataset:
    root = Path(data_dir)
    dataset = Dataset(root=str(root))
    for name in files:
        path = root / name
        try:
            rows = read_rows(path)
        except (OSError, UnicodeDecodeError):
            dataset.missing.append(name)
            dataset.rows[name] = []
            # take_snapshot 自己会返回 status=unavailable 并带上读取时间
            dataset.snapshots.append(take_snapshot(path, row_count=0))
            continue
        dataset.rows[name] = rows
        dataset.snapshots.append(take_snapshot(path, row_count=len(rows)))
    return dataset


def index_by(rows: Iterable[Row], key: str) -> Dict[str, Row]:
    out: Dict[str, Row] = {}
    for row in rows:
        value = row.get(key)
        if value and value not in out:
            out[value] = row
    return out
