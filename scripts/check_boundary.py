"""边界守卫：配置里不允许出现写回、外发、自动指派。

单独成文件，是为了让 CI、deploy.sh 和本地自检用同一份判断，不各写一遍。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from volunteer_handover.core.boundary import Boundary  # noqa: E402
from volunteer_handover.utils import config  # noqa: E402


def main(argv) -> int:
    target = Path(argv[1]) if len(argv) > 1 else Path("config/default.yaml")
    cfg = config.load(target)
    bad = Boundary.from_config(cfg.get("boundary") or {}).violations()
    if bad:
        print("边界越界：" + "、".join(f"{k}={v!r}" for k, v in bad))
        return 1
    print("boundary ok：只读 / 无外发通道 / 无自动指派")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
