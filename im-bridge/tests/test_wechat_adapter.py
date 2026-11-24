from datetime import datetime
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from im_bridge.adapters.wechat.adapter import WechatAdapter, WechatAdapterError, WechatKeyMissingError
from im_bridge.contract import ConversationSpec, QuerySpec, TimeRange


class WechatAdapterTests(unittest.TestCase):
    def setUp(self):
        self.adapter = WechatAdapter()
        self.query = QuerySpec(ConversationSpec(name="Fixture"),
                               TimeRange("2025-11-30T00:00:00+08:00", "2025-12-01T00:00:00+08:00"))
        self.contact = {"username": "wxid_fixture", "nick_name": "Fixture", "remark": ""}
        self.row = {"chat_username": "wxid_fixture", "id": 1, "type": "text", "text": "fixture",
                    "timestamp": int(datetime.fromisoformat("2025-11-30T00:00:00+08:00").timestamp())}

    def test_exact_contact_resolution_preserves_ambiguity(self):
        matches = [self.contact, {**self.contact, "username": "wxid_fixture_2"}]
        with patch.object(self.adapter, "_run", return_value=matches):
            result = self.adapter.resolve("Fixture")
        self.assertEqual("ambiguous", result.status)

    def test_returns_rows_with_explicit_coverage_limits_and_removes_cache(self):
        paths = []

        def respond(args, scratch):
            paths.append(scratch)
            if args[0] == "contacts":
                return [self.contact]
            self.assertEqual(["--", "wxid_fixture"], args[-2:])
            (scratch / "temporary.db").write_bytes(b"fixture")
            return {"username": "wxid_fixture", "count": 1, "message_items": [self.row]}

        with patch.object(self.adapter, "_run", side_effect=respond):
            result = self.adapter.read(self.query)
        self.assertEqual("partial", result.completeness)
        self.assertEqual("fixture", result.messages[0].content["text"])
        self.assertFalse(paths[0].exists())

    def test_rejects_message_at_exclusive_end(self):
        row = {**self.row, "timestamp": self.row["timestamp"] + 86400}
        data = {"username": "wxid_fixture", "count": 1, "message_items": [row]}
        with patch.object(self.adapter, "_run", side_effect=[[self.contact], data]):
            with self.assertRaisesRegex(WechatAdapterError, "时段"):
                self.adapter.read(self.query)

    def test_empty_install_reports_missing_configuration_before_starting_backend(self):
        with tempfile.TemporaryDirectory() as directory:
            adapter = WechatAdapter(config=str(Path(directory) / "config.json"))
            with patch("subprocess.run") as subprocess:
                with self.assertRaises(WechatKeyMissingError):
                    adapter.resolve("Fixture")
                subprocess.assert_not_called()


if __name__ == "__main__":
    unittest.main()
