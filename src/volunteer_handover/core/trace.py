"""来源位置、快照与审计。

对应访谈事实：
- f15 每条缺项要能跳回来源位置；
- f35 读取失败保留快照并标记时间，不编造"最新状态"，也不悄悄重试；
- f45 审计要能回答谁查过、用的哪一版、提了什么建议、由谁确认。

快照 = 文件指纹（sha256 + mtime + 行数），落在 out/snapshots.csv。
它证明"我当时读的是这一份"，而不是"我当时读的是最新的"。
"""

from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional


@dataclass
class Snapshot:
    file_name: str
    path: str
    status: str              # ok / unavailable
    rows: int = 0
    sha256: str = ""
    mtime: str = ""
    taken_at: str = ""
    note: str = ""

    def as_row(self) -> dict:
        return {
            "file": self.file_name,
            "status": self.status,
            "rows": self.rows,
            "sha256": self.sha256,
            "mtime": self.mtime,
            "taken_at": self.taken_at,
            "note": self.note,
        }


def take_snapshot(path, row_count: int = 0) -> Snapshot:
    p = Path(path)
    taken = datetime.now().isoformat(timespec="seconds")
    try:
        raw = p.read_bytes()
    except OSError as exc:
        # 失败即标记：不编造、不重试、不用上一次的缓存冒充
        return Snapshot(
            file_name=p.name,
            path=str(p),
            status="unavailable",
            taken_at=taken,
            note=f"读取失败：{exc.__class__.__name__}",
        )
    digest = hashlib.sha256(raw).hexdigest()[:16]
    mtime = datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds")
    return Snapshot(
        file_name=p.name,
        path=str(p),
        status="ok",
        rows=row_count,
        sha256=digest,
        mtime=mtime,
        taken_at=taken,
    )


def write_snapshots(snapshots: List[Snapshot], path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["file", "status", "rows", "sha256", "mtime", "taken_at", "note"])
        writer.writeheader()
        for s in snapshots:
            writer.writerow(s.as_row())


def locate(file_name: str, line_no: Optional[int] = None) -> str:
    """统一的来源位置写法：文件名#L行号。"""
    return f"{file_name}#L{line_no}" if line_no else file_name
