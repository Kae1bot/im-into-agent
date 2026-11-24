---
name: im-into-agent
description: 在 Windows 上按用户指定的联系人或群和时间范围读取本机微信消息，交给 agent，并保留消息引用、数据来源和读取状态。
---

# IM into Agent

使用本 Skill 根目录下的 `bridge.ps1`。发布版自带运行时，执行时使用 Skill 文件的绝对路径。

## 首次使用

请用户先登录本机 Windows 微信。首次使用或状态返回 `key_missing` 时，提示需要初始化本地微信读取环境，并在用户确认后运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File '<Skill目录>\setup.ps1'
```

初始化成功后会显示 `WeChat is ready for local reads.`。如果缺少运行时，使用 [Windows Skill ZIP](https://github.com/Kae1bot/im-into-agent/releases/latest)。

## 读取

查询需要用户指定会话与时间范围。使用带时区的 ISO 8601，起点包含，终点不包含。默认返回文字。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File '<Skill目录>\bridge.ps1' read --chat '项目讨论群' --kind group --since '2026-11-16T00:00:00+08:00' --until '2026-11-23T00:00:00+08:00'
```

- 遇到 `resolve_ambiguous` 时，让用户确认候选会话，再用 `--chat-id <候选ID>` 替代 `--chat`，沿用同一时间范围。
- 用可重复的 `--message-kind` 指定所需类型，或用 `--all-kinds` 读取所有类型。检查消息的 `status`，图片解码仍未进入主线。
- 保留 `ref`、发送者、时间、来源和读取状态。`complete` 表示扫描到微信本地时间线末页，本机可能缺少远端历史。`partial` 时保留已读结果，用 `limitations` 和 `oldest_scanned_at` 说明会影响任务的缺口。

## 授权与本地状态

每次读取只返回本次用户授权会话与时间范围内的信息。导出、归档、上传或共享需要单独授权。

微信数据源按只读方式访问。普通读取可更新当前 Windows 用户的 `%LOCALAPPDATA%\IM-into-Agent`，其中可能留存密钥配置、会话索引、媒体或转写缓存。将该目录留在本机用户配置目录。
