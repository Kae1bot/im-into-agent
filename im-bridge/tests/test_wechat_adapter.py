"""微信适配器映射函数与调用构造的单元测试。

用 wx-cli v2.0.2 输出形状的 fixture 与 subprocess mock，不读取真实微信数据。
"""
import hashlib
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


class TestImageKey(unittest.TestCase):
    def test_normalize_wxid(self):
        self.assertEqual(normalize_wxid("leokingleo_6d7d"), "leokingleo")
        self.assertEqual(normalize_wxid("leokingleo"), "leokingleo")

    def test_derive_matches_known_key(self):
        # 已知真实结果：code=1475319100, wxid=leokingleo -> md5 前 16 hex
        key = hashlib.md5("1475319100leokingleo".encode()).hexdigest()[:16]
        self.assertEqual(key, "8ad3072e7efe0a2e")


if __name__ == "__main__":
    unittest.main()
