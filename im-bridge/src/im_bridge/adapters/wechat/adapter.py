"""Read one authorized conversation through AuRevior's public CLI."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any

from ...contract import Candidate, Message, QuerySpec, ReadResult, ResolveResult, Sender
from ..base import Adapter

_HISTORY_LIMIT = 10_000
_MATCH_LIMIT = 500
_KIND_ALIASES = {"voice": "audio", "forwarded": "forward"}
_TEXT_KINDS = {"text", "system", "location", "link", "quote", "card"}
_PATH_FIELDS = {"image": "images", "video": "videos", "file": "files"}
_STABLE_ID = re.compile(r"^[A-Za-z0-9_.@-]{1,128}$")


class WechatAdapterError(Exception):
    """A failure from the authorized read."""


class WechatKeyMissingError(WechatAdapterError):
    """No provisioned local configuration is available."""


class WechatResolveError(Exception):
    def __init__(self, result: ResolveResult):
        super().__init__(f"resolve_{result.status}")
        self.result = result


def _parse_time(value: str) -> datetime:
    result = datetime.fromisoformat(value)
    if result.utcoffset() is None:
        raise WechatAdapterError("起止时间必须包含时区")
    return result


def _local_time(timestamp: int) -> str:
    local = datetime.fromtimestamp(timestamp)
    if datetime(*local.timetuple()[:6]).timestamp() != timestamp:
        raise WechatAdapterError("此时段的本地时钟时间存在歧义")
    return local.strftime("%Y-%m-%d %H:%M:%S")


def _candidate_kind(username: str) -> str:
    return "group" if username.endswith("@chatroom") else "direct"


def _contact_names(contact: dict) -> tuple[str, ...]:
    return tuple(value for key in ("remark", "nick_name", "alias", "username")
                 if isinstance(value := contact.get(key), str) and value)


class WechatAdapter(Adapter):
    source = "wechat_local_db"

    def __init__(self, config: str | None = None):
        default = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "IM-into-Agent-AuRevior/config.json"
        self.config = Path(config).expanduser().resolve() if config else default

    def _run(self, args: list[str], scratch: Path) -> Any:
        if not self.config.is_file():
            raise WechatKeyMissingError("缺少独立的 AuRevior 只读配置")
        package = Path(__file__).resolve().parents[4]
        runner = package / "scripts" / "run-aurevior.py"
        env = {key: value for key, value in os.environ.items()
               if not key.upper().startswith(("WECHAT_CLI_", "WX_MCP_"))}
        env.update(TEMP=str(scratch), TMP=str(scratch), USERPROFILE=str(scratch), HOME=str(scratch))
        try:
            process = subprocess.run(
                [sys.executable, "-I", "-B", str(runner), "--config", str(self.config), *args],
                cwd=scratch, env=env, stdin=subprocess.DEVNULL, capture_output=True,
                encoding="utf-8", timeout=120,
            )
        except (OSError, UnicodeError, subprocess.TimeoutExpired) as error:
            raise WechatAdapterError("AuRevior 调用未完成") from error
        if process.returncode == 3:
            raise WechatKeyMissingError("AuRevior 缺少可用的只读配置或分片密钥")
        if process.returncode:
            raise WechatAdapterError(f"AuRevior {args[0]} 调用失败")
        try:
            return json.loads(process.stdout)
        except json.JSONDecodeError as error:
            raise WechatAdapterError("AuRevior 输出格式无效") from error

    def _resolve(self, name: str, kind: str, scratch: Path) -> ResolveResult:
        if not name.strip():
            return ResolveResult("not_found")
        rows = self._run(["contacts", "--query", name, "--limit", str(_MATCH_LIMIT)], scratch)
        if not isinstance(rows, list) or len(rows) >= _MATCH_LIMIT:
            raise WechatAdapterError("会话解析输出无效或已截断")
        candidates: dict[str, Candidate] = {}
        for contact in rows:
            if not isinstance(contact, dict):
                raise WechatAdapterError("会话解析输出无效")
            username = contact.get("username")
            if not isinstance(username, str) or not _STABLE_ID.fullmatch(username):
                continue
            names = _contact_names(contact)
            candidate_kind = _candidate_kind(username)
            if name.casefold() not in {value.casefold() for value in names}:
                continue
            if kind != "any" and candidate_kind != kind:
                continue
            candidates[username] = Candidate(username, names[0], candidate_kind)
        choices = tuple(candidates.values())
        return ResolveResult("not_found" if not choices else "unique" if len(choices) == 1 else "ambiguous", choices)

    def resolve(self, name: str, kind: str = "any") -> ResolveResult:
        with tempfile.TemporaryDirectory(prefix="im-bridge-aurevior-") as directory:
            return self._resolve(name, kind, Path(directory))

    def read(self, query: QuerySpec) -> ReadResult:
        since, until = _parse_time(query.range.since), _parse_time(query.range.until)
        if since >= until:
            raise WechatAdapterError("起始时间必须早于结束时间")
        first_second, end_second = math.ceil(since.timestamp()), math.ceil(until.timestamp()) - 1
        limitations = ["non_snapshot", "remote_history_may_be_missing"]
        with tempfile.TemporaryDirectory(prefix="im-bridge-aurevior-") as directory:
            scratch = Path(directory)
            identity = query.conversation.id or query.conversation.name
            resolved = self._resolve(identity, query.conversation.kind, scratch)
            if resolved.status != "unique":
                raise WechatResolveError(resolved)
            candidate = resolved.candidates[0]
            if query.conversation.id and candidate.id != query.conversation.id:
                raise WechatResolveError(ResolveResult("not_found"))
            if first_second > end_second:
                return ReadResult((), "complete", self.source, tuple(limitations))
            args = ["history", "--start-time", _local_time(first_second),
                    "--end-time", _local_time(end_second), "--limit", str(_HISTORY_LIMIT + 1)]
            if query.kinds != ("text",):
                args.append("--media")
            data = self._run([*args, "--", candidate.id], scratch)
        if not isinstance(data, dict) or data.get("username") != candidate.id:
            raise WechatAdapterError("AuRevior 返回的会话与授权不匹配")
        rows = data.get("message_items")
        if not isinstance(rows, list) or data.get("count") != len(rows) or len(rows) > _HISTORY_LIMIT + 1:
            raise WechatAdapterError("AuRevior 返回的记录数量无效")
        issues = []
        if data.get("message_shards_complete") is not True:
            issues.append("aurevior_shard_read_failures" if data.get("message_shard_failures")
                          else "aurevior_shard_coverage_unverified")
        if data.get("failures"):
            issues.append("aurevior_read_failures")
        if len(rows) > _HISTORY_LIMIT:
            issues.append("aurevior_result_limit")
        messages: list[Message] = []
        timestamps: list[str] = []
        for row in rows[-_HISTORY_LIMIT:]:
            if not isinstance(row, dict) or row.get("chat_username") != candidate.id:
                raise WechatAdapterError("AuRevior 返回了其他会话的记录")
            stamp = row.get("timestamp")
            if type(stamp) is not int or not first_second <= stamp <= end_second:
                raise WechatAdapterError("AuRevior 返回了授权时段以外的记录")
            sent_at = datetime.fromtimestamp(stamp, tz=timezone.utc).isoformat()
            timestamps.append(sent_at)
            kind = _KIND_ALIASES.get(row.get("type"), row.get("type"))
            if kind not in ("audio", "forward", "sticker", "transfer", "red_packet", "miniprogram",
                            *_TEXT_KINDS, *_PATH_FIELDS):
                kind = "unknown"
            if query.kinds is None or kind in query.kinds:
                messages.append(_message(row, candidate.id, kind, sent_at))
        return ReadResult(tuple(sorted(messages, key=lambda m: m.sent_at)),
                          "partial" if issues else "complete", self.source,
                          tuple(limitations + issues), min(timestamps) if timestamps else None)


def _message(row: dict, chat: str, kind: str, sent_at: str) -> Message:
    sender = Sender(row.get("sender"), row.get("sender_username"))
    content = None
    status = "not_read"
    if kind in _TEXT_KINDS and isinstance(row.get("text"), str):
        content = {"text": row["text"]}
    elif kind == "forward" and isinstance(row.get("forwarded"), dict):
        forward = row["forwarded"]
        content = {key: forward[key] for key in ("title", "items", "truncated") if key in forward}
    elif kind in _PATH_FIELDS:
        media = row.get("media")
        if isinstance(media, dict) and media.get("bridge_verified_path"):
            path = media["bridge_verified_path"]
            if Path(path).suffix.lower() != ".dat":
                content = {_PATH_FIELDS[kind]: [path]}
    elif kind not in (*_TEXT_KINDS, *_PATH_FIELDS, "audio", "sticker", "forward"):
        status = "unsupported"
    identity = json.dumps([chat, row.get("id"), row["timestamp"], row.get("sender_username"),
                           row.get("type"), row.get("text")], ensure_ascii=False)
    ref = "ar:" + hashlib.sha256(identity.encode()).hexdigest()
    return Message(ref, chat, sender, sent_at, kind, content, "ok" if content is not None else status)
