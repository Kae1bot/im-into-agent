"""命令行入口：解析自然语言参数 → 选适配器 → 读 → 输出 JSON。"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from typing import Any

from .adapters.wechat.adapter import (
    WechatAdapter,
    WechatAdapterError,
    WechatKeyMissingError,
    WechatResolveError,
)
from .contract import ConversationSpec, QuerySpec, TimeRange


def _ok(obj: Any) -> str:
    return json.dumps({"ok": True, "data": asdict(obj)}, ensure_ascii=False)


def _err(code: str, message: str, **extra: Any) -> str:
    body: dict[str, Any] = {"code": code, "message": message}
    body.update(extra)
    return json.dumps({"ok": False, "error": body}, ensure_ascii=False)


def _adapter(args, im: str) -> WechatAdapter:
    if im != "wechat":
        raise WechatAdapterError(f"尚未接入的 IM：{im}")
    return WechatAdapter(
        args.cli or "wechat-cli",
        config=args.config,
        state_dir=args.state_dir,
        wcdb_lib=args.wcdb_lib,
    )


def main(argv: list[str] | None = None) -> int:
    # 强制 UTF-8 输出，保证交给 agent 的 JSON 编码确定。
    sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(prog="im-bridge")
    sub = parser.add_subparsers(dest="command", required=True)

    # 两个子命令共享的公共参数。
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--im", default="wechat", help="IM 标识（当前只支持 wechat）")
    common.add_argument("--cli", help="wx-cli 可执行文件路径（默认 wechat-cli）")
    common.add_argument("--config", help="wx-cli 配置文件路径（WECHAT_CLI_CONFIG，含 db_root + key）")
    common.add_argument("--wcdb-lib", help="libWCDB.dll 路径（WECHAT_CLI_WCDB_LIB）")
    common.add_argument("--state-dir", help="wx-cli state 目录（WECHAT_CLI_STATE_DIR）")

    r = sub.add_parser("resolve", parents=[common], help="把名字解析为稳定 ID")
    r.add_argument("--chat", required=True)
    r.add_argument("--kind", choices=("direct", "group", "any"), default="any")

    rd = sub.add_parser("read", parents=[common], help="读指定会话时间范围")
    rd.add_argument("--chat", required=True)
    rd.add_argument("--kind", choices=("direct", "group", "any"), default="any")
    rd.add_argument("--since", required=True)
    rd.add_argument("--until", required=True)

    args = parser.parse_args(argv)

    try:
        adapter = _adapter(args, args.im)
        if args.command == "resolve":
            print(_ok(adapter.resolve(args.chat, args.kind)))
            return 0

        query = QuerySpec(
            conversation=ConversationSpec(name=args.chat, kind=args.kind),
            range=TimeRange(since=args.since, until=args.until),
        )
        print(_ok(adapter.read(query)))
        return 0
    except WechatKeyMissingError as exc:
        print(_err("key_missing", str(exc)))
        return 3
    except WechatResolveError as exc:
        print(
            _err(
                f"resolve_{exc.result.status}",
                "会话未唯一解析，请让用户从候选中选择",
                candidates=[asdict(c) for c in exc.result.candidates],
            )
        )
        return 2
    except WechatAdapterError as exc:
        print(_err("source_failed", str(exc)))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
