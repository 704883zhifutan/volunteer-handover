#!/usr/bin/env bash
# 发布前检查（不联网、不部署到任何服务器）。
#
# 这个工具是现场负责人桌上的一个只读核对器，没有服务端、没有数据库、没有账号体系。
# 所以"部署"在这里只有一个含义：把仓库打成可交接的压缩包。
#
# 但打之前必须确认三门禁已关闭（docs/design.md §6）。未关闭时出包，等于把一份
# 未经确认的判定标准发给现场，比不发更危险。
#
# 用法：
#   scripts/deploy.sh                 # 只做检查，不打包（默认）
#   VH_GATES_CLOSED=1 scripts/deploy.sh   # 三门禁已书面确认后，打出压缩包到 dist/
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VERSION="$(PYTHONPATH=src python3 -c 'import volunteer_handover; print(volunteer_handover.__version__)')"
GATE_FILE="docs/gates.md"
ARCHIVE="dist/volunteer-handover-${VERSION}.tar.gz"

echo "==> 发布前检查（版本 ${VERSION}）"

# 1) 先过构建，构建不过不谈发布
bash scripts/build.sh > /tmp/vh-build.log 2>&1 || { tail -20 /tmp/vh-build.log; exit 1; }
echo "    构建：通过"

# 2) 边界：配置里不得出现写回 / 外发 / 自动指派
python3 scripts/check_boundary.py

# 3) 三门禁（G1 判定方法 / G2 值守与叫停 / G3 "完成"的定义）
echo "    门禁："
GATES_OPEN=0
if [ -f "$GATE_FILE" ]; then
  while IFS= read -r line; do
    case "$line" in
      "- [x]"*) printf '      %s\n' "$line" ;;
      "- [ ]"*) printf '      %s   ← 未关闭\n' "$line"; GATES_OPEN=1 ;;
    esac
  done < "$GATE_FILE"
else
  echo "      缺少 ${GATE_FILE}，视为三门禁全部未关闭"
  GATES_OPEN=1
fi

if [ "$GATES_OPEN" -ne 0 ]; then
  echo
  echo "拒绝出包：三门禁未全部关闭。"
  echo "理由：判定方法、值守人、\"完成\"定义未定，出包就是把未确认的标准发给现场。"
  echo "关掉之后（在 ${GATE_FILE} 里改成 [x] 并由责任人签字）再执行："
  echo "  VH_GATES_CLOSED=1 scripts/deploy.sh"
  exit 3
fi

if [ "${VH_GATES_CLOSED:-0}" != "1" ]; then
  echo
  echo "门禁已关闭，但未显式确认。确认后加 VH_GATES_CLOSED=1 再执行一次。"
  exit 4
fi

echo
echo "==> 打包"
mkdir -p dist
tar -czf "$ARCHIVE" \
  --exclude='out' --exclude='dist' --exclude='__pycache__' --exclude='.git' \
  README.md LICENSE CHANGELOG.md CONTRIBUTING.md requirements.txt \
  src docs tests examples scripts config data .github
echo "    $ARCHIVE（$(du -h "$ARCHIVE" | cut -f1)）"
echo
echo "交接方式：把压缩包发给现场负责人，解压后按 README 的三条命令自检。"
echo "不做自动更新：版本不一致时以人手上报为准，避免'某台机器还在跑旧规则'。"
