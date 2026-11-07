#!/usr/bin/env bash
# Install xuexitong-mcp from a release tag (Linux / macOS).
#   bash install.sh [--profile student|reviewer|teacher] [--ref v0.4.0] [--dir DIR] [--repo URL]
# The install is a git checkout so that `update` / `rollback` work later.
# No account, password, cookie or token is asked for or stored by this script.
set -euo pipefail
REPO="https://github.com/Leoliny87/chaoxing-teaching-mcp.git"
DIR="$HOME/.local/share/xuexitong-mcp/app"
VENV="$HOME/.local/share/xuexitong-mcp/venv"
REF=""
PROFILE="student"
PY="${PYTHON:-python3}"
CFG_DIR="$HOME/.config/xuexitong-mcp"
while [ $# -gt 0 ]; do
  case "$1" in
    --repo) REPO="$2"; shift 2;; --dir) DIR="$2"; shift 2;; --venv) VENV="$2"; shift 2;;
    --ref) REF="$2"; shift 2;; --profile) PROFILE="$2"; shift 2;; --python) PY="$2"; shift 2;;
    --config-dir) CFG_DIR="$2"; shift 2;;
    *) echo "未知参数 $1" >&2; exit 2;;
  esac
done
case "$PROFILE" in student|reviewer|teacher) ;; *) echo "profile 只能是 student/reviewer/teacher" >&2; exit 2;; esac
command -v git >/dev/null || { echo "缺少 git" >&2; exit 1; }
command -v "$PY" >/dev/null || { echo "缺少 $PY（需要 Python 3.10+）" >&2; exit 1; }
[ -e "$DIR/.git" ] && { echo "$DIR 已经安装过；更新请运行：$VENV/bin/python -I $DIR/scripts/launch_stdio.py update" >&2; exit 1; }

if [ -z "$REF" ]; then
  REF=$(git ls-remote --tags --refs "$REPO" | sed 's#.*refs/tags/##' | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' | sort -V | tail -1)
  [ -n "$REF" ] || { echo "仓库里没有发布版本（vX.Y.Z 标签）" >&2; exit 1; }
fi
echo "安装 $REF 到 $DIR（角色：$PROFILE）"
mkdir -p "$(dirname "$DIR")"
git clone --quiet "$REPO" "$DIR"
git -C "$DIR" -c advice.detachedHead=false checkout --quiet --detach "$REF"

"$PY" -m venv "$VENV"
P="$VENV/bin/python"
"$P" -I -c "import sys; sys.path.insert(0, '$DIR/server'); from pathlib import Path; from xuexitong_mcp.updater import check_manifest; p = check_manifest(Path('$DIR')); print('文件校验通过' if not p else '文件校验失败：' + '; '.join(p[:5])); sys.exit(1 if p else 0)"
"$P" -m pip install --disable-pip-version-check -q -r "$DIR/requirements-lock-py314-linux.txt"

CFG="$CFG_DIR/config.toml"
if [ ! -e "$CFG" ]; then
  mkdir -p "$CFG_DIR"; chmod 700 "$CFG_DIR"
  sed "s/^profile = \"teacher\"/profile = \"$PROFILE\"/" "$DIR/config/config.example.toml" > "$CFG"
  echo "已生成配置 $CFG（请按需填写 write_allow_courses、[tutor] 等）"
else
  echo "保留已有配置 $CFG"
fi
"$P" -I "$DIR/scripts/launch_stdio.py" --config "$CFG" --list-tools >/dev/null
cat <<EOF

安装完成。MCP 客户端配置示例：
{"mcpServers": {"xuexitong": {"command": "$P", "args": ["-I", "$DIR/scripts/launch_stdio.py"],
  "env": {"XUEXITONG_MCP_BROWSER": "填你的 BrowserSkill 实例 ID", "BSK_AUTO_START": "0", "BSK_AUTO_UPDATE": "off"}}}}

以后更新：$P -I $DIR/scripts/launch_stdio.py update      回退：... rollback
每日自动更新：$P -I $DIR/scripts/launch_stdio.py schedule  会打印要加入 crontab 的一行
EOF
