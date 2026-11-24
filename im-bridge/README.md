# IM-into-Agent for AuRevior

Windows x64 evaluation Skill. The Skill requires an installed Windows x64 Python 3.14 and uses an offline copy of the public AuRevior 0.6.1 reader.

- `setup.ps1 -CheckOnly` verifies the packaged Python imports and CLI.
- The user prepares a local AuRevior configuration independently. Run `setup.ps1 -ConfigPath <path to config.json>` to validate and select it once. Only the selected path is saved.
- `setup.ps1` rechecks the selected configuration. `config_validated` verifies the required files and source directory. An authorized read is needed to verify database connectivity.
- `bridge.ps1 read --chat <name> --since <time> --until <time>` accepts a half-open interval with explicit offsets.

Queries use a single bounded history request to avoid offset shifts between calls. Results are complete for the current local data when all discovered message shards could be checked and the requested interval was read without failure or truncation. Shard and query failures are reported separately from media availability. An individual message is marked unread when its underlying media is unavailable. This implementation does not transcribe audio.

AuRevior decrypts the database shards touched by a read into a temporary directory. The bridge removes that directory at the end of each ordinary call. Abrupt process termination can leave it behind. This evaluation should be run with synthetic data unless the user expressly allows temporary whole-shard plaintext.

See [contract](docs/contract.md).

## 构建可分发 ZIP

在仓库根目录使用 Python 3.14 运行以下命令。输出路径可自选。

```powershell
python -I -B im-bridge/scripts/package-windows-skill.py --download --output build/im-into-agent-aurevior-win-x64-0.2.0a1.zip
```

构建器核对 [锁定的公开源码和依赖轮包](scripts/windows-release-inputs.json) 的 SHA-256，将输入留在 `build/release-inputs`。有这些已验证输入时可省略 `--download`。输出包含顺序和时间戳固定的 ZIP 与同名 `.sha256` 文件。

AuRevior 来自锁文件指定的公开源码提交。打包清单只包含联系人解析、聊天读取和所需的运行模块。其余上游命令、密钥扫描组件、测试、发布脚本与本机配置不进入 ZIP。上游及随包依赖的许可证位于 ZIP 的 `licenses/`。

[用户安装说明](INSTALL.md) 随包提供。
