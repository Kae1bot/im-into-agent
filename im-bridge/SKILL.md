---
name: im-into-agent
description: 在 Windows 上按用户指定的联系人或群和时间范围读取本机微信消息，交给 agent，并保留消息引用、数据来源和读取状态。
---

# IM into Agent

这是通用 Agent Skill，可搭配不同大模型使用。宿主需能加载本文件或将它提供给 agent 作为指令，并能在安装了微信的 Windows x64 电脑上，经用户授权运行 PowerShell 和访问所需本地文件。使用本 Skill 根目录下的 `bridge.ps1`。发布版自带运行时，执行时使用脚本的绝对路径。

## 安装与首次使用

当用户请你安装或验证本 Skill 时，安装前先读本节。默认用两三句话说明安装结果、当前能否读取真实微信消息，以及用户下一步需要做什么。只做了模拟验证时，可以说“已安装，模拟验证通过。”遇到安装或识别问题时，说明用户实际会遇到什么以及怎么继续。

当用户要求详细报告，或技术信息会影响安全决定或阻止使用时，再说明校验值、签名、命令输出等相关细节。用户要求的技术结果放在简短结论之后。进度消息只报告有意义的变化，最终回复无需复述检查过程。

首次使用或状态返回 `key_missing` 时，给用户明确的操作指引：

> 请登录电脑版微信，任意打开一个有图片的聊天，点开其中一张图片。完成后回到这里，回复「已初始化，请确认」。

收到这句回复后，由 agent 运行下方命令完成并验证本机初始化。用户的回复表示准备步骤已完成；只有脚本验证成功后，才告诉用户可以指定联系人或群以及时间范围来读取。

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
