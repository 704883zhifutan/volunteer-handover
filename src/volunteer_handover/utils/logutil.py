"""本地审计日志。

注意区分：
- 审计日志 = 本地证据文件（谁在什么时候读了什么、用了哪一版）。
- 写回业务系统 = 本项目明确禁止的能力，不存在于代码中。

审计日志落本地 out/ 目录，不向外发送。
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List


@dataclass
class AuditEntry:
    at: str
    actor: str
    action: str
    target: str
    version: str = ""
    note: str = ""


@dataclass
class AuditLog:
    """只追加、不修改的审计记录。对应 f45：谁查过、用哪版、提了什么建议、谁确认。"""

    entries: List[AuditEntry] = field(default_factory=list)

    def record(self, action: str, target: str, version: str = "", note: str = "", actor: str = "system") -> None:
        self.entries.append(
            AuditEntry(
                at=datetime.now().isoformat(timespec="seconds"),
                actor=actor,
                action=action,
                target=target,
                version=version,
                note=note,
            )
        )

    def to_csv(self, path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["at", "actor", "action", "target", "version", "note"])
            for e in self.entries:
                writer.writerow([e.at, e.actor, e.action, e.target, e.version, e.note])
