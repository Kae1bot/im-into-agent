"""微信适配器：调用 wx-cli（本机 CLI），把输出映射到统一契约。

底层 key 提取 / SQLCipher 解密由 wx-cli 完成，本适配器不实现。
它只做两件事：
  1. QuerySpec → wx-cli 的 resolve_chat / chat_timeline 工具；
  2. wx-cli 输出 → Message / ReadResult。

调用方式按 wx-cli v2.0.2 及其本机 wrapper 的已验证约定：
  wechat-cli.exe --strict-read-only call-json <tool>  （JSON 参数走 stdin）
并通过环境变量注入 config（含 db_root + key）、WCDB 库、state 目录。
"""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from typing import Any

from ...contract import (
    Candidate,
    Message,
    QuerySpec,
    ReadResult,
    ResolveResult,
    Sender,
)
from ..base import Adapter
from .image import derive_image_key_from_config


class WechatAdapterError(Exception):
    """wx-cli 调用失败。"""


class WechatKeyMissingError(WechatAdapterError):
    """key 未缓存（strict-read-only 模式下无法自动提取）。"""


class WechatResolveError(Exception):
    """会话解析未唯一命中，携带 ResolveResult 供用户消歧。"""

    def __init__(self, result: ResolveResult):
        super().__init__(f"resolve_{result.status}")
        self.result = result


# 契约会话类型 → wx-cli type_filter 值
_KIND_TO_TYPE_FILTER = {"direct": "private", "group": "group", "any": ""}

# wx-cli kind_name → 契约 kind
_KIND_MAP = {
    "text": "text",
    "image": "image",
    "video": "video",
    "voice": "audio",
    "file": "file",
    "link": "link",
    "location": "location",
    "sticker": "sticker",
    "card": "card",
    "quote": "quote",
    "forward_chat": "forward",
    "system": "system",
    "transfer": "transfer",
    "red_packet": "red_packet",
    "miniprogram": "miniprogram",
}


def iso_to_unix(iso: str) -> int:
    """ISO 8601 → unix 秒（wx-cli after/before 接受 unix 秒或 YYYY-MM-DD）。"""
    dt = datetime.fromisoformat(iso)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


class WechatAdapter(Adapter):
    source = "wechat_local_db"

    def __init__(
        self,
        cli: str,
        *,
        config: str | None = None,
        state_dir: str | None = None,
        wcdb_lib: str | None = None,
        strict_read_only: bool = False,
        page_size: int = 200,
    ):
        self.cli = cli
        self.config = config
        self.state_dir = state_dir
        self.wcdb_lib = wcdb_lib
        self.strict_read_only = strict_read_only
        self.page_size = page_size

    # ---- wx-cli 调用 ----

    def _build_env(self) -> dict[str, str]:
        # 清掉继承的 wx-cli 环境变量，再注入本适配器的运行时配置。
        env = {
            k: v for k, v in os.environ.items()
            if not k.upper().startswith(("WECHAT_CLI_", "WX_MCP_"))
        }
        if self.config:
            env["WECHAT_CLI_CONFIG"] = self.config
            # 自动推导图片 key（md5(code+wxid)），避免独立 wxkey 进程/手动输入。
            image_key = derive_image_key_from_config(self.config)
            if image_key:
                env["WECHAT_CLI_IMAGE_KEY"] = image_key
        if self.state_dir:
            env["WECHAT_CLI_STATE_DIR"] = self.state_dir
        if self.wcdb_lib:
            env["WECHAT_CLI_WCDB_LIB"] = self.wcdb_lib
        env["WECHAT_CLI_STRICT_READ_ONLY"] = "1" if self.strict_read_only else "0"
        return env

    def _run(self, tool: str, params: dict[str, Any]) -> dict[str, Any]:
        cmd = [self.cli]
        if self.strict_read_only:
            cmd.append("--strict-read-only")
        cmd += ["call-json", tool]
        try:
            proc = subprocess.run(
                cmd,
                input=json.dumps(params, ensure_ascii=False),
                capture_output=True,
                text=True,
                encoding="utf-8",
                env=self._build_env(),
            )
        except OSError as exc:
            raise WechatAdapterError(f"无法调用 wx-cli（{self.cli}）：{exc}") from exc

        # wx-cli 失败时 returncode=1，但 JSON 错误在 stdout（stderr 通常为空），
        # 所以先解析 stdout，再判断 ok；只有 stdout 不是 JSON 才退回 stderr/退出码。
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise WechatAdapterError(
                proc.stderr.strip() or f"wx-cli 退出码 {proc.returncode}，输出非 JSON"
            ) from exc

        if not data.get("ok"):
            err = data.get("error") or {}
            if "key config is missing" in (err.get("message") or ""):
                raise WechatKeyMissingError(
                    "微信加密 key 未缓存：请先登录微信并运行一次 "
                    "`wechat-cli cache refresh --force` 提取 key，然后再重试"
                )
            raise WechatAdapterError(json.dumps(err, ensure_ascii=False))
        return data

    # ---- 适配器接口 ----

    def resolve(self, name: str, kind: str = "any") -> ResolveResult:
        params: dict[str, Any] = {"query": name}
        type_filter = _KIND_TO_TYPE_FILTER.get(kind)
        if type_filter:
            params["type_filter"] = type_filter
        data = self._run("resolve-chat", params)
        raw = data.get("data", {}).get("candidates", [])
        candidates = tuple(_map_candidate(c) for c in raw)
        if not candidates:
            return ResolveResult(status="not_found")
        if len(candidates) > 1:
            return ResolveResult(status="ambiguous", candidates=candidates)
        return ResolveResult(status="unique", candidates=candidates)

    def read(self, query: QuerySpec) -> ReadResult:
        resolved = self.resolve(query.conversation.name, query.conversation.kind)
        if resolved.status != "unique":
            raise WechatResolveError(resolved)
        talker = resolved.candidates[0].id

        since = str(iso_to_unix(query.range.since))
        until = str(iso_to_unix(query.range.until))

        # 单个游标循环读完整个时间范围（不是 legacy 的窗口切片/两趟读取）。
        messages: list[Message] = []
        cursor: str | None = None
        limitations = ["non_snapshot"]
        incomplete = False
        while True:
            params: dict[str, Any] = {
                "talker": talker,
                "limit": self.page_size,
                "order": "desc",
                "display_order": "asc",
                "after": since,
                "before": until,
                "include_media_paths": True,
                "include_debug": False,
            }
            if cursor:
                params["before_message_token"] = cursor
            data = self._run("timeline", params)
            body = data.get("data", data)
            messages.extend(_map_message(m) for m in body.get("messages", []))

            query_meta = body.get("query") or {}
            if not query_meta.get("has_more"):
                break
            cursor = (query_meta.get("cursor") or {}).get("next_before_message_token")
            if not cursor:
                # has_more 但没有游标：无法续读，如实标 partial。
                incomplete = True
                limitations.append("more_messages_unreachable_no_cursor")
                break

        messages.sort(key=lambda m: m.sent_at)
        return ReadResult(
            messages=tuple(messages),
            completeness="partial" if incomplete else "complete",
            source=self.source,
            limitations=tuple(limitations),
        )


# ---- 输出映射（纯函数，便于用 fixture 单测） ----

def _map_chat_type(chat_type: Any) -> str:
    return "group" if chat_type == "group" else "direct"


def _map_kind(kind: Any) -> str:
    return _KIND_MAP.get(kind, "unknown")


def _map_candidate(raw: dict[str, Any]) -> Candidate:
    username = raw.get("username") or ""
    return Candidate(
        id=username,
        display=raw.get("display_name") or username,
        kind=_map_chat_type(raw.get("chat_type")),
    )


# 契约已结构化支持的 kind（其余如 transfer/red_packet/sticker 暂标 unsupported）
_SUPPORTED_KINDS = frozenset(
    {"text", "image", "video", "audio", "file", "link", "forward", "quote"}
)


def _paths(items: Any) -> list[str] | None:
    """从 wx-cli 的 images/videos/files 列表提取可直接读取的本地 path。"""
    if not isinstance(items, list):
        return None
    out = [it["path"] for it in items if isinstance(it, dict) and it.get("path")]
    return out or None


def _extract_content(raw: dict[str, Any], kind: str) -> dict | None:
    """按 kind 从 wx-cli 消息行提取契约 content（path/转写/链接/转发等）。"""
    if kind == "text":
        return {"text": raw.get("text")}
    if kind == "image":
        p = _paths(raw.get("images"))
        return {"images": p} if p else None
    if kind == "video":
        p = _paths(raw.get("videos"))
        return {"videos": p} if p else None
    if kind == "file":
        p = _paths(raw.get("files"))
        return {"files": p} if p else None
    if kind == "audio":
        # 语音：优先转写文本（wx-cli 已本地转写），未转写则为 None
        voice = raw.get("voice")
        transcript = voice.get("transcript") if isinstance(voice, dict) else None
        return {"transcript": transcript} if transcript else None
    if kind == "link":
        link = raw.get("link")
        if not isinstance(link, dict):
            return None
        return {"title": link.get("title"), "url": link.get("url")}
    if kind == "forward":
        fw = raw.get("forward_chat")
        if not isinstance(fw, dict):
            return None
        return {"title": fw.get("title"), "items": fw.get("items")}
    if kind == "quote":
        q = raw.get("quote")
        if not isinstance(q, dict):
            return None
        return {"text": q.get("text"), "sender": q.get("sender")}
    return None


def _map_message(raw: dict[str, Any]) -> Message:
    rid = raw.get("id") or {}
    ref = (
        rid.get("message_token")
        or str(rid.get("server_id_str") or rid.get("local_id") or "")
    )
    sender = Sender(
        display=raw.get("sender_contact_display")
        or raw.get("sender")
        or raw.get("sender_wxid"),
        id=raw.get("sender_wxid"),
    )
    kind = _map_kind(raw.get("kind"))
    content = _extract_content(raw, kind)
    if kind in _SUPPORTED_KINDS:
        status = "ok" if content is not None else "not_read"
    else:
        status = "unsupported"
    return Message(
        ref=ref,
        conversation=rid.get("talker") or "",
        sender=sender,
        sent_at=raw.get("time_iso") or "",
        kind=kind,
        content=content,
        status=status,
    )
