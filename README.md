# IM-into-Agent

IM-into-Agent 是通用 Agent Skill，让 AI agent 按用户指定的联系人或群和时间范围读取本机微信消息，保留来源和引用。可搭配不同大模型使用。当前运行环境是 Windows x64 和 Windows 微信桌面版。

## 安装 Agent Skill

1. 下载并解压 [Windows x64 Skill 安装包](https://github.com/Kae1bot/im-into-agent/releases/latest/download/im-into-agent-windows-x64.zip)，保留 `im-into-agent` 整个目录。[下载校验值](https://github.com/Kae1bot/im-into-agent/releases/latest/download/im-into-agent-windows-x64.zip.sha256)
2. 按你的 agent 宿主说明安装这份 Skill。也可以把目录里的 `SKILL.md` 作为 agent 指令，并提供解压目录的本机路径。宿主需要能在运行微信的 Windows 电脑上，经用户授权执行 PowerShell 并访问所需本地文件。
3. 首次使用时，登录电脑版微信，打开任意一个有图片的聊天，点开一张图片，再回到 agent 回复「已初始化，请确认」。agent 会执行并验证本机初始化。
4. 验证通过后，直接指定会话和时间，例如「用 IM-into-Agent 读取项目讨论群昨天的消息，保留发言人、时间和引用」。

安装包自带 Python、`wx-cli` 和 WCDB。微信数据源按只读方式访问。初始化和查询可能在 `%LOCALAPPDATA%\IM-into-Agent` 保存本地读取所需的配置和缓存。

默认读取文字。按需查询其他类型时，返回值取决于本机媒体是否可用。图片解码尚未进入主线。下游可以通过 `completeness` 和 `limitations` 判断扫描状态和本地历史覆盖限制。

[开发说明](im-bridge/README.md) · [查询与结果契约](im-bridge/docs/contract.md) · [第三方组件](THIRD_PARTY_NOTICES.md)
