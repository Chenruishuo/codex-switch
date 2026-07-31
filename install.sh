#!/usr/bin/env bash
# 安装 codex-switch + codex-mcp-keeper 到 ~/bin,并把 Claude Code 的 codex MCP 注册指向 keeper
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p "$HOME/bin"
cp bin/codex-switch bin/codex-mcp-keeper bin/codex-diff "$HOME/bin/"
chmod +x "$HOME/bin/codex-switch" "$HOME/bin/codex-mcp-keeper" "$HOME/bin/codex-diff"
case ":$PATH:" in
  *":$HOME/bin:"*) ;;
  *)
    case "${SHELL:-}" in */zsh) rc="$HOME/.zshrc" ;; *) rc="$HOME/.bashrc" ;; esac
    if ! grep -qs 'HOME/bin' "$rc" 2>/dev/null; then
      printf '\nexport PATH="$HOME/bin:$PATH"\n' >> "$rc"
    fi
    echo "已把 ~/bin 加入 PATH ($rc);重开终端或 source $rc 后生效"
    ;;
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
