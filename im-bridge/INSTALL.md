# 安装 AuRevior 版 IM-into-Agent

这是 Windows x64 预发布版。安装和读取应在微信所在的电脑上进行。预先安装系统 Python 3.14，并确认 PowerShell 能找到该 Python。Skill 自带读取依赖，安装 ZIP 无需另行下载这些依赖。

1. 从 [GitHub 预发布](https://github.com/Kae1bot/im-into-agent/releases/tag/v0.2.0-alpha.1) 下载 Windows ZIP 和同名的 `.sha256` 文件。
2. 用 PowerShell 的 `Get-FileHash -Algorithm SHA256` 核对 ZIP 哈希。解压整个 `im-into-agent-aurevior` 目录，按 agent 宿主的说明安装。如果宿主没有目录安装入口，可以让 agent 使用解压目录的 `SKILL.md` 和脚本。
3. 先运行 `setup.ps1 -CheckOnly` 验证运行时。运行 `setup.ps1` 检测已关联的配置。首次安装显示 `key_missing` 时，请按照 `SKILL.md` 中的上游说明，在自己的 Windows 终端手动完成 AuRevior 初始化。
4. 只把生成的 `config.json` 本机路径告诉 agent。使用 `setup.ps1 -ConfigPath <配置文件路径>` 关联配置，再指定一个会话和时段验证读取。

读取时可能临时生成整个 SQLite 分片的明文副本。正常结束会清理，异常中断后可能遗留。预发布包未内置语音转写，部分 V2 图片无法解码。会话覆盖和单条媒体的可读状态分别报告。

上游 AuRevior 和随包依赖的许可文本位于 `licenses/`。AuRevior 的原始第三方声明也随包提供，声明里列出的 SILK 解码器和语音转写模型不在本安装包中。
