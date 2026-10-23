"""语法检查：解析全部 .py，不写字节码（沙箱里 compileall 会往 HOME 缓存写文件）。"""

from __future__ import annotations

import ast
import pathlib
import sys


def main() -> int:
    bad = 0
    for path in sorted(pathlib.Path(".").glob("**/*.py")):
        if "__pycache__" in path.parts:
            continue
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            bad += 1
            print(f"    语法错误 {path}:{exc.lineno}: {exc.msg}")
    if bad:
        return 1
    print("    语法 OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
