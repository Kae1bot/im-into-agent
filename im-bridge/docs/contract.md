# 统一契约（IM-into-Agent v2）

多 IM 桥接的公共语言。所有 IM（微信、飞书、钉钉……）的读取适配器都实现这份契约，
下游 agent 只面向这份契约，不感知具体 IM。

## 设计原则

- **IM 无关**：契约里不出现任何具体 IM 的字段名（不出现 talker / open_id / msgId）。
- **最小**：只定义"输入四件套 + 输出四件套"，不往上加东西。
- **消息类型可扩展**：`kind` 枚举预留全类型，现在只实现 `text`，后续加类型 = 加解析器。
- **来源/完整性可表达**：不同 IM 的差异（本地库缺远端历史、云端有保留期、撤回消息缺失）
  全部收敛到 `source` + `limitations` 两个字段。

## 1. 查询输入 QuerySpec（agent → 适配器）

agent 解析用户话术（"读测试联系人在 11 月 19 日的聊天"）后，生成统一输入：

```json
{
  "conversation": {
    "name": "测试联系人",
    "kind": "direct"
  },
  "range": {
    "since": "2026-11-19T00:00:00+08:00",
    "until": "2026-11-20T00:00:00+08:00"
  },
  "kinds": ["text"]
}
```

| 字段 | 说明 |
|---|---|
| `conversation.name` | 用户指定的会话名，由适配器解析。与 `conversation.id` 二选一 |
| `conversation.id` | 已确认的稳定会话 ID，例如用户选定的 `candidates[].id`。按 ID 直接读取 |
| `conversation.kind` | 名称解析时使用 `direct`（单聊）/ `group`（群）/ `any` |
| `range.since` | ISO 8601，**含起点** |
| `range.until` | ISO 8601，**不含终点** |
| `kinds` | 需要的消息类型，默认 `["text"]`，可指定多种。显式传 `null` 读取所有类型 |

同名歧义时不猜，返回候选让用户选（见 Resolve）。

## 2. 会话解析 Resolve（适配器 → agent）

```json
{
  "status": "unique",
  "candidates": [
    { "id": "<适配器内稳定ID>", "display": "显示名", "kind": "direct" }
  ]
}
```

- `status`：`unique`（唯一，直接读）/ `ambiguous`（同名多个，让用户选）/ `not_found`。
- `candidates[].id` 是适配器内稳定 ID，后续查询用它，不用自然名重复解析。

## 3. 消息 Message（统一输出）

```json
{
  "ref": "<会话内稳定引用>",
  "conversation": "<会话引用>",
  "sender": { "display": "昵称", "id": "<适配器内发送者ID>" },
  "sent_at": "2026-11-19T09:30:00+08:00",
  "kind": "text",
  "content": { "text": "你好" },
  "status": "ok"
}
```

- `ref` 是不透明字符串，适配器各自生成（微信用 message_token，飞书用 message_id，钉钉用 msgId）。
  公共层不理解其内部格式，只用于后续 context / search 定位。
- `status`：`ok` / `not_read` / `unsupported`。某类型该适配器还没实现时标 `unsupported`、
  `content` 为 `null`，不假装读到了。

### kind 枚举（现在只实现 `text`）

```
text, image, video, audio, file, link, location, sticker, card,
quote, forward, system, transfer, red_packet, miniprogram, unknown
```

`content` 按 kind 结构化：

- `text` → `{ "text": "..." }`
- `image` / `video` / `file` / `audio` → `{ "path": "...", "name": "...", ... }`
- `link` → `{ "title": "...", "url": "..." }`
- 未实现类型 → `content: null`，`status: "unsupported"`

## 4. 读取结果 ReadResult（信封）

```json
{
  "messages": [ "...Message" ],
  "completeness": "complete",
  "source": "wechat_local_db",
  "limitations": ["non_snapshot", "remote_history_may_be_missing"],
  "oldest_scanned_at": "2026-11-19T09:30:00+08:00"
}
```

- `completeness`：`complete` 表示数据源明确报告已扫描到指定范围的末页，包括合法空结果。`partial` 表示扫描中断或来源覆盖有缺口，同时返回已读消息和停止原因。消息本身的可读性由 `Message.status` 单独表达。
- `oldest_scanned_at`：已通过分页校验的页面中最早的消息时间，包含被类型筛选掉的消息。没有可确认的时间时为 `null`。
- `source`：`wechat_local_db` / `feishu_api` / `dingtalk_api` / ...。
- `limitations`：承载各 IM 差异，例如：
  - 微信本地库：`non_snapshot`（非固定快照）、`remote_history_may_be_missing`（本机可能没存全远端历史）
  - 飞书：`retention_window`（有保留期）、`revoked_messages_missing`（撤回的拿不到）

微信适配器从上一个已确认游标重试异常页，最多重试两次。仍无法继续时，`limitations` 会包含相应原因，例如 `invalid_pagination_metadata`、`more_messages_unreachable_no_cursor`、`repeated_pagination_cursor`、`message_shard_coverage_partial` 或 `timeline_call_failed`。首个读取调用持续失败且没有可用页时返回结构化错误。已读到内容后遇到密钥缺失时，返回 `partial` 和 `key_missing`，供 agent 判断是否需要用户重新初始化。

## 5. 分层

| 层 | 职责 | IM 无关？ |
|---|---|---|
| QuerySpec / Resolve / Message / ReadResult | 公共语言 | ✅ 完全无关 |
| 微信适配器 | QuerySpec → wx-cli 命令；wx-cli 输出 → Message | ❌ 微信专属（薄层） |
| 飞书适配器 | QuerySpec → 飞书 REST API；响应 → Message | ❌ 飞书专属 |
| 钉钉适配器 | 同理 | ❌ 钉钉专属 |

每个 IM 适配器只做两件事：

1. 把 QuerySpec 翻译成该 IM 的调用（微信调 wx-cli，飞书/钉钉调 REST API）；
2. 把该 IM 的输出翻译成 Message / ReadResult。

## 授权语义

- 不做白名单、不做续期、不做持久化授权。
- 每次请求，agent 显式给出（对象、时间范围）即本次授权；缺参就报错让 agent 问。
- 适配器把会话与时间范围传给 wx-cli。微信数据库按只读方式访问，普通读取可以更新本地支持文件。
