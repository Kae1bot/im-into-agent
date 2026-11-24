# IM Bridge 开发说明

生产入口是 [Windows Skill 安装包](https://github.com/Kae1bot/im-into-agent/releases/latest)。源码目录包含 Python CLI、微信适配器和 [统一契约](docs/contract.md)。当前适配器为微信，底层使用 wx-cli 和 WCDB。

## 测试

在本目录运行以下命令，需要 Python 3.11 或更高版本。测试使用合成消息和模拟 subprocess。

```powershell
$env:PYTHONPATH = 'src'
python -B -m unittest discover -s tests
```

## 构建 Windows 依赖

使用 x64 Windows、Go 1.26.5 或更高版本、CMake 3.31 或更高版本和 Visual Studio 2022 Build Tools 的 C++ 工作负载。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build-wx-cli.ps1
```

在 `build\native\bin` 下生成 `wechat-cli.exe` 与 `libWCDB.dll`。构建脚本固定 wx-cli 源码提交和 WCDB 发布档案的 SHA256。

## 组装 Skill 发行包

```powershell
python scripts/package-windows-skill.py --bin build/native/bin `
  --python-archive <Python官方嵌入包> --licenses <第三方许可目录> --output build/release
```

Python 档案及其固定校验值见 [第三方组件](../THIRD_PARTY_NOTICES.md)。许可目录包含 `wx-cli.txt`、`wcdb.txt`、`go.txt`、`purego.txt`、`klauspost-compress.txt` 以及 WCDB 所用的 `openssl.txt`、`sqlcipher.txt` 和 `zstd.txt`。嵌入式 Python 的许可随原包带入。

组装后，从全新解压目录运行 `setup.ps1 -CheckOnly` 和 `bridge.ps1 --help`，核对 Python、WCDB DLL 和 CLI 能启动。初始化与实际读取需 Windows 微信登录和本机用户授权。
