#!/usr/bin/env bash
# 本地构建校验：不需要网络、不需要第三方包，只证明"这台机器上跑得起来"。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PY="${PYTHON:-python3}"
export PYTHONDONTWRITEBYTECODE=1

echo "==> 1/5 检查 Python 版本"
"$PY" - <<'EOF'
import sys
if sys.version_info < (3, 9):
    sys.exit(f"需要 Python 3.9+，当前 {sys.version.split()[0]}")
print(f"    Python {sys.version.split()[0]} OK")
EOF

echo "==> 2/5 语法、导入、图表与脚本一致"
"$PY" scripts/check_syntax.py
PYTHONPATH=src "$PY" -c "import volunteer_handover.main"
echo "    导入 OK"

# 流程图是脚本生成的。有人手改 SVG 就会和脚本对不上，这里当场拦住。
FC_BAK="$(mktemp)"
cp docs/flowchart.svg "$FC_BAK"
"$PY" scripts/make_flowchart.py > /dev/null
if ! cmp -s docs/flowchart.svg "$FC_BAK"; then
  cp "$FC_BAK" docs/flowchart.svg
  echo "    docs/flowchart.svg 与 scripts/make_flowchart.py 不一致（手改过？）"
  echo "    改流程请改脚本里的 NODES，然后重新生成"
  exit 1
fi
echo "    流程图与脚本一致 OK"

echo "==> 3/5 单元测试"
"$PY" -m unittest discover -s tests -t tests 2>&1 | tail -3

echo "==> 4/5 桌面推演（W0）"
PYTHONPATH=src "$PY" examples/demo.py > /tmp/vh-demo.log 2>&1 || {
  echo "    demo 失败，日志："; tail -20 /tmp/vh-demo.log; exit 1
}
echo "    demo OK（$(wc -l < /tmp/vh-demo.log | tr -d ' ') 行输出）"

echo "==> 5/5 端到端跑一次只读核对（含复核回填与金标比对）并检查产物"
OUT="$(mktemp -d)"
PYTHONPATH=src "$PY" -m volunteer_handover.main --out "$OUT" \
  --review data/review.csv --run-at 2026-10-03T17:00:00 > /dev/null
for f in items.csv items.md handover.md snapshots.csv audit.csv metrics.md metrics.csv; do
  [ -s "$OUT/$f" ] || { echo "    缺少产物：$f"; exit 1; }
done
"$PY" scripts/metrics.py --items "$OUT/items.csv" --review data/review.csv \
  --run-at 2026-10-03T17:00:00 --out "$OUT/metrics.md" > /dev/null
"$PY" scripts/score.py --items "$OUT/items.csv" --gold data/gold_overlap.csv \
  --out "$OUT/score.md" > /dev/null || { echo "    金标比对未通过（G1 还关不掉），这不算构建失败但要知道"; }
for f in metrics.md score.md; do
  [ -s "$OUT/$f" ] || { echo "    缺少产物：$f"; exit 1; }
done
echo "    产物 OK：$(ls "$OUT" | tr '\n' ' ')"
rm -rf "$OUT"

echo
echo "构建通过。注意：通过构建 ≠ 可以上现场，三门禁在 docs/gates.md。"
