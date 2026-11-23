# IM-into-Agent v2

把 IM 聊天记录交给 AI agent 的最小多 IM 桥接框架。

- **统一契约**：查询输入 / 会话解析 / 消息 / 读取结果四件套，IM 无关，飞书/钉钉后续各接一个适配器。
- **微信适配器**：直接调用 [wx-cli](https://github.com/r266-tech/wx-cli)（本地只读），不自己实现 key 提取 / SQLCipher。
- **可自安装**：`setup.ps1` 完成"装二进制 + 提取 key"；Windows 二进制可由 `scripts/build-wx-cli.ps1` 从源码编译。

## 目录结构

```
im-bridge/
├── SKILL.md                     # skill 说明（agent 读取用）
├── setup.ps1                    # 首次使用：装二进制 + 提取 key
├── README.md                    # 本文档
├── docs/contract.md             # 统一契约设计
├── scripts/
│   ├── build-wx-cli.ps1         # 从源码编译 wechat-cli.exe + libWCDB.dll
│   ├── demo_read.py             # 真实读取示例
│   └── probe_raw_error.py       # 探测 wx-cli 原始报错（调试用）
├── src/im_bridge/
│   ├── contract.py              # 契约 dataclass
│   ├── cli.py                   # 命令行入口
│   └── adapters/
│       ├── base.py              # Adapter 接口
│       └── wechat/adapter.py    # 微信适配器（调 wx-cli，映射到契约）
└── tests/test_wechat_adapter.py # 单元测试（13 个）
```

## 统一契约（IM 无关）

四件套：`QuerySpec`（查询输入）、`ResolveResult`（会话解析）、`Message`（消息）、`ReadResult`（读取结果）。
详见 [docs/contract.md](docs/contract.md)。

## 微信适配器

调用 wx-cli（锁定 v2.0.2 接口），通过 `call-json` + 环境变量注入 config / WCDB 库。底层 key 提取和
SQLCipher 解密都由 wx-cli 完成，本项目不实现。见
[adapter.py](src/im_bridge/adapters/wechat/adapter.py)。

## 编译 Windows 二进制（开发者）

官方 release 目前只有 macOS 包，Windows 的 `wechat-cli.exe` + `libWCDB.dll` 需自己编译：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build-wx-cli.ps1
```

需求：Go >= 1.26、CMake >= 3.31、Visual Studio 2022 BuildTools（C++ 工作负载）。
产物在 `out\` 下，含 SHA256。

已在本机编译验证通过（`live_read_ok=True`）：

| 文件 | 大小 | SHA256 |
|---|---|---|
| wechat-cli.exe | 13.63 MB | 93e8144988ade1526171aa8070ee865d8e2114bf25d7bf606642a7237a54333b |
| libWCDB.dll | 5.05 MB | 669ef5f9245505e18cc4f06dc7cde3e654d65c5a961f73cb71c810cc7380593a |

## 首次使用 / 换机器（新用户）

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File setup.ps1 -PackagePath <含exe和dll的zip路径>
```

- 把二进制装到 `%LOCALAPPDATA%\wechat-cli\bin`；
- 跑 `cache refresh --force` 提取 key（需微信已登录）。

## 使用

```powershell
$env:PYTHONPATH = 'src'
python -m im_bridge.cli resolve --chat <名字> --kind group `
  --cli <wechat-cli.exe路径> --wcdb-lib <libWCDB.dll路径>

python -m im_bridge.cli read --chat <名字> --kind group `
  --since 2026-11-16T00:00:00+08:00 --until 2026-11-23T00:00:00+08:00 `
  --cli <wechat-cli.exe路径> --wcdb-lib <libWCDB.dll路径>
```

## key 与授权

- key **按账号、按机器**，只能从登录微信的内存提取一次，之后缓存；清缓存/换机器需重新提取。
- 不做白名单/续期，每次现授权；适配器遇到 key 缺失会报 `key_missing` 并提示跑 `cache refresh --force`。
- 微信 4.x 进程名是 `WeChatAppEx`（不是 `WeChat`/`Weixin`）。

## 信息披露（发布前必做）

wx-cli（MIT）、WCDB（腾讯）、OpenSSL 等第三方组件的许可 + 署名 + 清单；所用二进制的版本与来源。
详见 legacy 中 `docs/research/T2-C0-source-provenance.md` 关于 Windows 二进制来源的历史疑问。

## 状态

- [x] 统一契约 + 微信适配器 + CLI
- [x] 单元测试 13/13
- [x] 真实最小闭环读取验收（群「❤鲁乔(一一）亲子分享群❤」上周记录）
- [x] Windows 二进制从源码编译 + 验证
- [x] setup.ps1 + SKILL.md
- [ ] 飞书适配器
- [ ] 钉钉适配器
- [ ] 媒体类型（图片/视频/语音/链接/嵌套转发）解析
