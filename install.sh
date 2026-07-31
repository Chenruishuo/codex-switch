#!/usr/bin/env bash
# 安装 codex-switch + codex-mcp-keeper 到 ~/bin,并把 Claude Code 的 codex MCP 注册指向 keeper
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p "$HOME/bin"
cp bin/codex-switch bin/codex-mcp-keeper "$HOME/bin/"
chmod +x "$HOME/bin/codex-switch" "$HOME/bin/codex-mcp-keeper"
case ":$PATH:" in
  *":$HOME/bin:"*) ;;
  *) echo "提示: ~/bin 不在 PATH 里,请自行加入 shell 配置 (export PATH=\"\$HOME/bin:\$PATH\")" ;;
esac
if command -v claude >/dev/null 2>&1; then
  claude mcp remove codex -s user >/dev/null 2>&1 || true
  claude mcp add-json codex "{\"type\":\"stdio\",\"command\":\"python3\",\"args\":[\"$HOME/bin/codex-mcp-keeper\"]}" -s user
  echo "已把 Claude Code 的 codex MCP 注册指向 keeper (user scope)"
else
  echo "未找到 claude CLI,跳过 MCP 注册;之后手动执行:"
  echo "  claude mcp add-json codex '{\"type\":\"stdio\",\"command\":\"python3\",\"args\":[\"'\"\$HOME\"'/bin/codex-mcp-keeper\"]}' -s user"
fi
echo
echo "下一步:"
echo "  1) 写入 relay token:  printf '%s' 'sk-xxx' > ~/.codex/cctq.key && chmod 600 ~/.codex/cctq.key"
echo "  2) codex-switch status   # 查看当前模式"
echo "  3) codex-switch relay | official   # 切换"
