# IM-into-Agent

让 Codex 按指定联系人或群和时间范围读取本机微信消息。当前支持 Windows x64 和 Windows 微信桌面版。

## 安装 Codex Skill

1. 下载并解压 [Windows x64 Skill 安装包](https://github.com/Kae1bot/im-into-agent/releases/latest/download/im-into-agent-windows-x64.zip)。将解压出的 `im-into-agent` 整个文件夹放到 `%USERPROFILE%\.codex\skills`。如果配置了 `CODEX_HOME`，使用其中的 `skills` 目录。[下载校验值](https://github.com/Kae1bot/im-into-agent/releases/latest/download/im-into-agent-windows-x64.zip.sha256)
2. 登录 Windows 微信，在 Codex 新开对话并输入 `$im-into-agent`。按提示确认首次初始化。也可以从 Skill 目录手动运行 `powershell -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1`。
3. 指定会话和时间。例如：`用 $im-into-agent 读取项目讨论群昨天的消息，保留发言人、时间和引用。`

安装包自带 Python、`wx-cli` 和 WCDB。微信数据源按只读方式访问。初始化和查询可能在 `%LOCALAPPDATA%\IM-into-Agent` 保存本地读取所需的配置和缓存。

默认读取文字。按需查询其他类型时，返回值取决于本机媒体是否可用。图片解码尚未进入主线。下游可以通过 `completeness` 和 `limitations` 判断扫描状态和本地历史覆盖限制。

[开发说明](im-bridge/README.md) · [查询与结果契约](im-bridge/docs/contract.md) · [第三方组件](THIRD_PARTY_NOTICES.md)
