"""微信适配器映射函数与调用构造的单元测试。

用 wx-cli v2.0.2 输出形状的 fixture 与 subprocess mock，不读取真实微信数据。
"""
import hashlib
import io
import json
import unittest
from unittest import mock

from im_bridge.adapters.wechat.adapter import (
    WechatAdapter,
    WechatAdapterError,
    WechatKeyMissingError,
    _map_candidate,
    _map_kind,
    _map_message,
    iso_to_unix,
)
from im_bridge.adapters.wechat.image import normalize_wxid
from im_bridge.cli import main
from im_bridge.contract import ConversationSpec, QuerySpec, TimeRange


class TestTimeConversion(unittest.TestCase):
    def test_iso_with_offset(self):
        # 2026-11-19T00:00:00+08:00 == 2026-11-18T16:00:00Z
        self.assertEqual(
            iso_to_unix("2026-11-19T00:00:00+08:00"),
            iso_to_unix("2026-11-18T16:00:00Z"),
        )

    def test_naive_iso_treated_as_utc(self):
        self.assertEqual(
            iso_to_unix("2026-11-19T00:00:00"),
            iso_to_unix("2026-11-19T00:00:00Z"),
        )


class TestKindMapping(unittest.TestCase):
    def test_common_kinds(self):
        self.assertEqual(_map_kind("text"), "text")
        self.assertEqual(_map_kind("voice"), "audio")
        self.assertEqual(_map_kind("forward_chat"), "forward")

    def test_unknown_kind(self):
        self.assertEqual(_map_kind("voip"), "unknown")


class TestCandidateMapping(unittest.TestCase):
    def test_private(self):
        c = _map_candidate(
            {"username": "wxid_abc", "display_name": "小明", "chat_type": "private"}
        )
        self.assertEqual(c.id, "wxid_abc")
        self.assertEqual(c.display, "小明")
        self.assertEqual(c.kind, "direct")

    def test_group(self):
        c = _map_candidate(
            {"username": "x@chatroom", "display_name": "群", "chat_type": "group"}
        )
        self.assertEqual(c.kind, "group")


class TestMessageMapping(unittest.TestCase):
    def test_text(self):
        raw = {
            "id": {"talker": "wxid_abc", "local_id": 1,
                   "server_id_str": "9", "message_token": "tok1"},
            "sender": "小明", "sender_wxid": "wxid_abc",
            "sender_contact_display": "小明",
            "time_iso": "2026-11-19T09:30:00+08:00",
            "kind": "text", "text": "你好",
        }
        m = _map_message(raw)
        self.assertEqual(m.ref, "tok1")
        self.assertEqual(m.conversation, "wxid_abc")
        self.assertEqual(m.sender.display, "小明")
        self.assertEqual(m.kind, "text")
        self.assertEqual(m.content, {"text": "你好"})
        self.assertEqual(m.status, "ok")

    def test_voice_not_transcribed(self):
        raw = {
            "id": {"talker": "x@chatroom", "local_id": 2},
            "sender_wxid": "wxid_b",
            "time_iso": "2026-11-19T10:00:00+08:00",
            "kind": "voice", "text": "[语音]",
        }
        m = _map_message(raw)
        self.assertEqual(m.kind, "audio")
        self.assertIsNone(m.content)
        self.assertEqual(m.status, "not_read")

    def test_image_with_path(self):
        raw = {
            "id": {"talker": "g@chatroom", "local_id": 10, "message_token": "t10"},
            "sender_wxid": "wxid_a",
            "time_iso": "2026-11-19T10:00:00+08:00",
            "kind": "image", "text": "[图片]",
            "images": [{"path": "C:/media-cache/a.jpg"}],
        }
        m = _map_message(raw)
        self.assertEqual(m.kind, "image")
        self.assertEqual(m.content, {"images": ["C:/media-cache/a.jpg"]})
        self.assertEqual(m.status, "ok")

    def test_image_no_path_not_read(self):
        raw = {
            "id": {"talker": "g@chatroom", "local_id": 11},
            "sender_wxid": "wxid_a",
            "time_iso": "2026-11-19T10:00:00+08:00",
            "kind": "image", "text": "[图片]",
        }
        m = _map_message(raw)
        self.assertEqual(m.kind, "image")
        self.assertIsNone(m.content)
        self.assertEqual(m.status, "not_read")

    def test_voice_with_transcript(self):
        raw = {
            "id": {"talker": "g@chatroom", "local_id": 12},
            "sender_wxid": "wxid_a",
            "time_iso": "2026-11-19T10:00:00+08:00",
            "kind": "voice", "voice": {"transcript": "开会改到明天"},
        }
        m = _map_message(raw)
        self.assertEqual(m.kind, "audio")
        self.assertEqual(m.content, {"transcript": "开会改到明天"})
        self.assertEqual(m.status, "ok")

    def test_link(self):
        raw = {
            "id": {"talker": "g@chatroom", "local_id": 13},
            "sender_wxid": "wxid_a",
            "time_iso": "2026-11-19T10:00:00+08:00",
            "kind": "link", "link": {"title": "标题", "url": "https://example.com"},
        }
        m = _map_message(raw)
        self.assertEqual(m.kind, "link")
        self.assertEqual(m.content, {"title": "标题", "url": "https://example.com"})
        self.assertEqual(m.status, "ok")

    def test_transfer_unsupported(self):
        raw = {
            "id": {"talker": "g@chatroom", "local_id": 14},
            "sender_wxid": "wxid_a",
            "time_iso": "2026-11-19T10:00:00+08:00",
            "kind": "transfer", "text": "[转账]",
        }
        m = _map_message(raw)
        self.assertEqual(m.kind, "transfer")
        self.assertIsNone(m.content)
        self.assertEqual(m.status, "unsupported")

    def test_ref_fallback_to_server_id_str(self):
        raw = {
            "id": {"talker": "wxid_abc", "local_id": 3, "server_id_str": "42"},
            "sender_wxid": "wxid_c",
            "time_iso": "2026-11-19T11:00:00+08:00",
            "kind": "text", "text": "ok",
        }
        m = _map_message(raw)
        self.assertEqual(m.ref, "42")


class TestAdapterCall(unittest.TestCase):
    def _make_adapter(self):
        return WechatAdapter(
            "wxcli.exe",
            config="C:/cfg/config.json",
            state_dir="C:/cfg/state",
            wcdb_lib="C:/bin/libWCDB.dll",
        )

    def test_resolve_command_env_and_params(self):
        adapter = self._make_adapter()
        fake = {"ok": True, "data": {"candidates": [
            {"username": "wxid_abc", "display_name": "小明", "chat_type": "private"},
        ]}}
        with mock.patch(
            "subprocess.run",
            return_value=mock.Mock(returncode=0, stdout=json.dumps(fake), stderr=""),
        ) as run:
            result = adapter.resolve("小明", "direct")

        self.assertEqual(result.status, "unique")
        cmd = run.call_args.args[0]
        self.assertEqual(cmd, ["wxcli.exe", "call-json", "resolve-chat"])
        params = json.loads(run.call_args.kwargs["input"])
        self.assertEqual(params, {"query": "小明", "type_filter": "private"})
        env = run.call_args.kwargs["env"]
        self.assertEqual(env["WECHAT_CLI_CONFIG"], "C:/cfg/config.json")
        self.assertEqual(env["WECHAT_CLI_WCDB_LIB"], "C:/bin/libWCDB.dll")
        self.assertEqual(env["WECHAT_CLI_STRICT_READ_ONLY"], "0")

    def test_read_builds_timeline_params(self):
        adapter = self._make_adapter()
        resolve_out = {"ok": True, "data": {"candidates": [
            {"username": "wxid_abc", "display_name": "小明", "chat_type": "private"},
        ]}}
        timeline_out = {"ok": True, "data": {"query": {"has_more": False}, "messages": []}}
        with mock.patch(
            "subprocess.run",
            side_effect=[
                mock.Mock(returncode=0, stdout=json.dumps(resolve_out), stderr=""),
                mock.Mock(returncode=0, stdout=json.dumps(timeline_out), stderr=""),
            ],
        ) as run:
            result = adapter.read(QuerySpec(
                conversation=ConversationSpec(name="小明", kind="direct"),
                range=TimeRange(
                    since="2026-11-19T00:00:00+08:00",
                    until="2026-11-20T00:00:00+08:00",
                ),
            ))

        self.assertEqual(result.completeness, "complete")
        cmd = run.call_args_list[1].args[0]
        self.assertEqual(cmd, ["wxcli.exe", "call-json", "timeline"])
        params = json.loads(run.call_args_list[1].kwargs["input"])
        self.assertEqual(params["talker"], "wxid_abc")
        self.assertEqual(params["after"], str(iso_to_unix("2026-11-19T00:00:00+08:00")))
        self.assertEqual(params["before"], str(iso_to_unix("2026-11-20T00:00:00+08:00")))
        self.assertEqual(params["order"], "desc")
        self.assertEqual(params["display_order"], "asc")

    def test_key_missing_raises_friendly_error(self):
        adapter = self._make_adapter()
        key_missing = {
            "ok": False,
            "error": {
                "code": "tool_error",
                "message": "strict_read_only: key config is missing; run wxkey/bootstrap "
                           "or cache refresh outside strict read-only mode, then retry",
            },
        }
        with mock.patch(
            "subprocess.run",
            return_value=mock.Mock(returncode=1, stdout=json.dumps(key_missing), stderr=""),
        ):
            with self.assertRaises(WechatKeyMissingError) as ctx:
                adapter.resolve("小明", "direct")
        self.assertIn("cache refresh --force", str(ctx.exception))

    def test_non_key_error_passes_through(self):
        adapter = self._make_adapter()
        other = {"ok": False, "error": {"code": "tool_error", "message": "别的错误"}}
        with mock.patch(
            "subprocess.run",
            return_value=mock.Mock(returncode=1, stdout=json.dumps(other), stderr=""),
        ):
            with self.assertRaises(WechatAdapterError) as ctx:
                adapter.resolve("小明", "direct")
        self.assertNotIsInstance(ctx.exception, WechatKeyMissingError)


class TestTimelinePagination(unittest.TestCase):
    def setUp(self):
        self.adapter = WechatAdapter("wxcli.exe")
        self.range = TimeRange("2026-11-19T00:00:00+08:00", "2026-11-20T00:00:00+08:00")
        self.query = QuerySpec(ConversationSpec(id="synthetic-id"), self.range)

    @staticmethod
    def row(token, hour, kind="text"):
        return {
            "id": {"talker": "synthetic-id", "message_token": token},
            "time_iso": f"2026-11-19T{hour:02}:00:00+08:00",
            "kind": kind,
            "text": token,
        }

    @staticmethod
    def page(rows, **query):
        return {"ok": True, "data": {"query": query, "messages": rows}}

    def test_default_text_filters_after_scanning_all_pages(self):
        responses = [
            self.page([self.row("newest", 12, "image")], has_more=True,
                      cursor={"next_before_message_token": "next"}),
            self.page([self.row("text", 10), self.row("oldest", 9, "video")], has_more=False),
        ]
        with mock.patch.object(self.adapter, "_run", side_effect=responses) as run:
            result = self.adapter.read(self.query)

        self.assertEqual(result.completeness, "complete")
        self.assertEqual(result.limitations, ("non_snapshot", "remote_history_may_be_missing"))
        self.assertEqual([item.ref for item in result.messages], ["text"])
        self.assertEqual(result.oldest_scanned_at, "2026-11-19T09:00:00+08:00")
        self.assertEqual([call.args[0] for call in run.call_args_list], ["timeline", "timeline"])
        first, second = [call.args[1] for call in run.call_args_list]
        self.assertEqual(first["talker"], "synthetic-id")
        self.assertFalse(first["include_media_paths"])
        self.assertNotIn("before_message_token", first)
        self.assertEqual(second, {**first, "before_message_token": "next"})

    def test_explicit_empty_last_page(self):
        response = {"ok": True, "data": {"query": {"has_more": False, "returned": 0}}}
        with mock.patch.object(self.adapter, "_run", return_value=response) as run:
            result = self.adapter.read(self.query)
        run.assert_called_once()
        self.assertEqual(result.completeness, "complete")
        self.assertEqual(result.messages, ())
        self.assertIsNone(result.oldest_scanned_at)

    def test_terminal_metadata_cannot_hide_missing_messages(self):
        response = {"ok": True, "data": {"query": {"has_more": False, "returned": 1}}}
        with mock.patch.object(self.adapter, "_run", return_value=response) as run:
            result = self.adapter.read(self.query)
        self.assertEqual(run.call_count, 3)
        self.assertEqual(result.completeness, "partial")
        self.assertIn("invalid_timeline_page", result.limitations)

    def test_retry_recovers_from_invalid_pagination_and_deduplicates(self):
        newest = self.row("newest", 12)
        responses = [
            self.page([newest], has_more=True, cursor={"next_before_message_token": "anchor"}),
            self.page([self.row("older", 8)], has_more="false"),
            self.page([newest, self.row("older", 8)], has_more=False),
        ]
        with mock.patch.object(self.adapter, "_run", side_effect=responses) as run:
            result = self.adapter.read(self.query)

        self.assertEqual(run.call_args_list[1], run.call_args_list[2])
        self.assertEqual(result.completeness, "complete")
        self.assertEqual([item.ref for item in result.messages], ["older", "newest"])

    def test_persistent_invalid_metadata_returns_partial_with_readable_rows(self):
        for query, reason in [
            ({}, "invalid_pagination_metadata"),
            ({"has_more": 0}, "invalid_pagination_metadata"),
            ({"has_more": True}, "more_messages_unreachable_no_cursor"),
            ({"has_more": True, "cursor": {"next_before_message_token": 1}},
             "more_messages_unreachable_no_cursor"),
        ]:
            with self.subTest(query=query):
                response = self.page([self.row("row", 9)], **query)
                with mock.patch.object(self.adapter, "_run", return_value=response) as run:
                    result = self.adapter.read(self.query)
                self.assertEqual(run.call_count, 3)
                self.assertEqual(result.completeness, "partial")
                self.assertIn(reason, result.limitations)
                self.assertEqual([item.ref for item in result.messages], ["row"])
                self.assertIsNone(result.oldest_scanned_at)

    def test_cursor_cycle_stops_and_preserves_confirmed_progress(self):
        def page_with_cursor(row, cursor):
            return self.page([row], has_more=True, cursor={"next_before_message_token": cursor})

        newest, middle, oldest = [
            self.row("newest", 12), self.row("middle", 10), self.row("oldest", 8),
        ]
        responses = [
            page_with_cursor(newest, "first"),
            page_with_cursor(middle, "second"),
            *[page_with_cursor(oldest, "first")] * 3,
        ]
        with mock.patch.object(self.adapter, "_run", side_effect=responses) as run:
            result = self.adapter.read(self.query)
        self.assertEqual(
            [call.args[1].get("before_message_token") for call in run.call_args_list],
            [None, "first", "second", "second", "second"],
        )
        self.assertEqual(result.completeness, "partial")
        self.assertIn("repeated_pagination_cursor", result.limitations)
        self.assertEqual([item.ref for item in result.messages], ["oldest", "middle", "newest"])
        self.assertEqual(result.oldest_scanned_at, middle["time_iso"])

    def test_missing_shard_prevents_complete_even_on_terminal_page(self):
        response = self.page([self.row("row", 9)], has_more=False)
        response["data"]["warnings"] = ["message_shard_coverage_partial:1_of_2_unchecked"]
        with mock.patch.object(self.adapter, "_run", return_value=response) as run:
            result = self.adapter.read(self.query)
        self.assertEqual(run.call_count, 3)
        self.assertEqual(result.completeness, "partial")
        self.assertIn("message_shard_coverage_partial", result.limitations)

    def test_midstream_failure_preserves_messages_and_first_failure_raises(self):
        success = self.page([self.row("newest", 12)], has_more=True,
                            cursor={"next_before_message_token": "anchor"})
        failure = WechatAdapterError("source unavailable")
        with mock.patch.object(self.adapter, "_run", side_effect=[success, failure, failure, failure]) as run:
            result = self.adapter.read(self.query)
        self.assertEqual(run.call_count, 4)
        self.assertEqual(result.completeness, "partial")
        self.assertIn("timeline_call_failed", result.limitations)
        self.assertEqual([item.ref for item in result.messages], ["newest"])
        with mock.patch.object(self.adapter, "_run", side_effect=failure) as run:
            with self.assertRaises(WechatAdapterError):
                self.adapter.read(self.query)
        self.assertEqual(run.call_count, 3)

    def test_midstream_key_missing_preserves_rows_without_retrying(self):
        success = self.page([self.row("newest", 12)], has_more=True,
                            cursor={"next_before_message_token": "anchor"})
        failure = WechatKeyMissingError("log in to WeChat")
        with mock.patch.object(self.adapter, "_run", side_effect=[success, failure]) as run:
            result = self.adapter.read(self.query)
        self.assertEqual(run.call_count, 2)
        self.assertEqual(result.completeness, "partial")
        self.assertIn("key_missing", result.limitations)
        self.assertEqual([item.ref for item in result.messages], ["newest"])

    def test_ambiguous_name_stops_before_timeline(self):
        candidates = [
            {"username": chat_id, "display_name": "同名", "chat_type": "private"}
            for chat_id in ("synthetic-id", "other-id")
        ]
        args = ["read", "--chat", "同名", "--since", self.range.since, "--until", self.range.until]
        response = {"ok": True, "data": {"candidates": candidates}}
        with io.TextIOWrapper(io.BytesIO()) as stdout, mock.patch("sys.stdout", stdout):
            with mock.patch.object(WechatAdapter, "_run", return_value=response) as run:
                self.assertEqual(main(args), 2)
            stdout.flush()
            output = json.loads(stdout.buffer.getvalue())
        run.assert_called_once_with("resolve-chat", {"query": "同名"})
        self.assertEqual(output["error"]["code"], "resolve_ambiguous")
        self.assertEqual([row["id"] for row in output["error"]["candidates"]], ["synthetic-id", "other-id"])

    def test_message_kinds_cli_and_stable_id(self):
        rows = [self.row("text", 8), self.row("photo", 9, "image"), self.row("voice", 10, "voice")]
        response = self.page(rows, has_more=False)
        for flags, expected in [
            ([], ["text"]),
            (["--message-kind", "image", "--message-kind", "audio"], ["image", "audio"]),
            (["--all-kinds"], ["text", "image", "audio"]),
        ]:
            with self.subTest(flags=flags):
                args = [
                    "read", "--chat-id", "synthetic-id", "--cli", "wxcli.exe",
                    "--since", self.range.since, "--until", self.range.until, *flags,
                ]
                process = mock.Mock(returncode=0, stdout=json.dumps(response), stderr="")
                with io.TextIOWrapper(io.BytesIO()) as stdout, mock.patch("sys.stdout", stdout):
                    with mock.patch("subprocess.run", return_value=process) as run:
                        self.assertEqual(main(args), 0)
                    stdout.flush()
                    output = json.loads(stdout.buffer.getvalue())
                run.assert_called_once()
                self.assertEqual(run.call_args.args[0], ["wxcli.exe", "call-json", "timeline"])
                params = json.loads(run.call_args.kwargs["input"])
                self.assertEqual(params["talker"], "synthetic-id")
                self.assertEqual([item["kind"] for item in output["data"]["messages"]], expected)
                if "image" in expected:
                    image = next(item for item in output["data"]["messages"] if item["kind"] == "image")
                    self.assertEqual(image["status"], "not_read")
                    self.assertEqual(output["data"]["completeness"], "complete")


class TestImageKey(unittest.TestCase):
    def test_normalize_wxid(self):
        self.assertEqual(normalize_wxid("wxid_example_a1b2"), "wxid_example")
        self.assertEqual(normalize_wxid("wxid_example"), "wxid_example")

    def test_derive_matches_known_key(self):
        key = hashlib.md5(b"123456wxid_example").hexdigest()[:16]
        self.assertEqual(key, "e12dcdddb9f6af1c")


if __name__ == "__main__":
    unittest.main()
