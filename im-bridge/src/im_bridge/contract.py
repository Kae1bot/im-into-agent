"""统一契约：IM 无关的查询输入与消息输出。

这是多 IM 桥接的公共语言。每个 IM 适配器负责：
  1. 把 QuerySpec 翻译成自己的调用（微信调 wx-cli，飞书/钉钉调 REST API）；
  2. 把自己的输出翻译成 Message / ReadResult。

契约里不出现任何具体 IM 的字段名（不出现 talker / open_id / msgId）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

#: 会话类型
ConversationKind = Literal["direct", "group", "any"]

#: 消息类型（现在只实现 text，其余预留，后续加类型 = 加解析器）
MESSAGE_KINDS = (
    "text", "image", "video", "audio", "file", "link", "location",
    "sticker", "card", "quote", "forward", "system", "transfer",
    "red_packet", "miniprogram", "unknown",
)

#: 消息读取状态
MessageStatus = Literal["ok", "not_read", "unsupported"]

#: 读取完整性
Completeness = Literal["complete", "partial"]


@dataclass(frozen=True)
class ConversationSpec:
    """用户指定的会话（自然语言）。"""
    name: str
    kind: ConversationKind = "any"


@dataclass(frozen=True)
class TimeRange:
    """时间范围，ISO 8601，含起点、不含终点。"""
    since: str
    until: str


@dataclass(frozen=True)
class QuerySpec:
    """查询输入。"""
    conversation: ConversationSpec
    range: TimeRange
    kinds: tuple[str, ...] = ("text",)


@dataclass(frozen=True)
class Candidate:
    """会话解析候选。id 是适配器内稳定 ID。"""
    id: str
    display: str
    kind: ConversationKind


@dataclass(frozen=True)
class ResolveResult:
    """会话解析结果。"""
    status: Literal["unique", "ambiguous", "not_found"]
    candidates: tuple[Candidate, ...] = ()


@dataclass(frozen=True)
class Sender:
    """发送者。display 是给人看的名字，id 是适配器内稳定 ID。"""
    display: str | None = None
    id: str | None = None


@dataclass(frozen=True)
class Message:
    """一条消息（IM 无关）。"""
    ref: str                       # 会话内稳定引用（不透明）
    conversation: str              # 会话引用
    sender: Sender
    sent_at: str                   # ISO 8601
    kind: str
    content: dict | None = None    # 按 kind 结构化；未实现类型为 None
    status: MessageStatus = "ok"


@dataclass(frozen=True)
class ReadResult:
    """读取结果信封。"""
    messages: tuple[Message, ...]
    completeness: Completeness
    source: str                    # wechat_local_db / feishu_api / dingtalk_api
    limitations: tuple[str, ...] = ()
