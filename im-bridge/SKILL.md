---
name: im-into-agent
description: 读取本机微信聊天记录（指定联系人/群 + 时间范围）交给 agent。基于 wx-cli 本地只读，不发送消息、不控制微信界面。首次使用需先跑 setup.ps1 提取 key。
---

# IM into Agent —— 微信聊天记录读取

把微信聊天记录按"指定对象 + 时间范围"读出来，交给 agent。底层用
[wx-cli](https://github.com/r266-tech/wx-cli)（MIT）本地只读，不发送消息、不控制微信界面。

## 首次使用（每台新机器一次性）

先跑 setup，安装二进制并提取 key：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File setup.ps1 -PackagePath <含exe和dll的zip路径>
```

setup 会：① 把 `wechat-cli.exe` + `libWCDB.dll` 装到 `%LOCALAPPDATA%\wechat-cli\bin`；② 跑
`cache refresh --force` 提取 key（这一步需要**微信已登录**，最好开一个聊天窗口）。

## 读取方式（两种，任选）

### 方式 1：im-bridge 统一契约（推荐，多 IM 一致）

```powershell
$env:PYTHONPATH = '<im-bridge目录>\src'
python -m im_bridge.cli read --chat "<联系人/群名>" --kind group `
  --since 2026-11-16T00:00:00+08:00 --until 2026-11-23T00:00:00+08:00 `
  --cli "$env:LOCALAPPDATA\wechat-cli\bin\wechat-cli.exe" `
  --wcdb-lib "$env:LOCALAPPDATA\wechat-cli\bin\libWCDB.dll"
```

### 方式 2：wx-cli 直接调

```powershell
$cli = "$env:LOCALAPPDATA\wechat-cli\bin\wechat-cli.exe"
& $cli resolve-chat "<名字>"          # 名字 → 稳定 ID（同名歧义返回候选）
& $cli timeline "<名字>" --after 2026-11-16 --before 2026-11-23 --limit 50 --display-order asc
```

## 授权语义

- **不做白名单、不做续期**。用户明确指定"对象 + 时间范围"即本次授权，每次现授权。
- 读取用 `--strict-read-only` 或 `WECHAT_CLI_STRICT_READ_ONLY=1`，不写本地支持文件。
- 遇到 `key_missing` / `strict_read_only: key config is missing` → 提示用户先登录微信并跑
  `cache refresh --force`，不要自己绕过。

## 关键事实（排查时用）

- 微信 4.x 进程名是 **`WeChatAppEx`**，不是 `WeChat` / `Weixin`（探测"微信是否在跑"别查错）。
- key **按账号、按机器**，一次性提取后缓存；清缓存 / 换机器必须重新登录微信提取，无法通用。
- 官方 release 目前**只有 macOS（darwin-arm64）包**，Windows 二进制需自己编译（`scripts/build-wx-cli.ps1`）
  或由 skill 分发。
- 输出字段：`id(message_token/local_id/server_id_str/talker)`、`time_iso`、`sender`、`kind`、`text` 等。
