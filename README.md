# codex-switch

在 Codex 的**官方 ChatGPT 订阅**与**中转 relay**(默认 cctq, `https://www.cctq.ai/v1`)之间一键切换,并保证:

- 官方登录态自动备份/恢复(`~/.codex/auth.official.json`);
- 历史会话不"消失"——自动同步 `state_*.sqlite` 与 `sessions/` rollout 的 provider 元数据
  (Codex 禁止覆写内置 provider id,中转必须用独立 id,否则 `/resume` 按 provider 过滤会看不到历史);
- 切换对运行中的 Claude Code 会话无感——`codex-mcp-keeper` 作为 MCP 注册命令保持与
  Claude Code 的 stdio 管道,内层 `codex mcp-server`(auth 为进程级缓存,切换后必须重启)
  被杀后自动重拉并重放 MCP 握手,在途请求返回明确错误而非挂死。

## 安装

```bash
git clone git@github.com:Chenruishuo/codex-switch.git
cd codex-switch && ./install.sh
printf '%s' 'sk-你的token' > ~/.codex/cctq.key && chmod 600 ~/.codex/cctq.key
```

依赖: bash、python3 (≥3.6)、sqlite3 CLI、codex CLI;可选 claude CLI(用于自动注册 MCP)。
Linux / macOS 通用(keeper 会自动定位各平台的 codex 原生二进制,找不到则退回 PATH 上的 codex)。

## 使用

```bash
codex-switch status     # 当前模式、auth 类型、历史会话 provider 分布
codex-switch relay      # 切到中转 (token 读 ~/.codex/cctq.key)
codex-switch official   # 切回官方订阅 (恢复备份的登录态;若无备份需先 codex login)
codex-switch sync       # 只同步会话元数据到当前 provider,不切换
```

机制细节见两个脚本的头部注释。keeper 日志: `~/.codex/mcp-keeper.log`。

## 安全说明

token、登录态备份都只存在本机 `~/.codex/` 下,不进仓库。
