from datetime import datetime
import hashlib
from pathlib import Path
import runpy
import sqlite3
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

    def test_complete_range_removes_cache(self):
        paths = []

        def respond(args, scratch):
            paths.append(scratch)
            if args[0] == "contacts":
                return [self.contact]
            self.assertEqual(["--", "wxid_fixture"], args[-2:])
            (scratch / "temporary.db").write_bytes(b"fixture")
            return {"username": "wxid_fixture", "count": 1, "message_items": [self.row],
                    "message_shards_complete": True}

        with patch.object(self.adapter, "_run", side_effect=respond):
            result = self.adapter.read(self.query)
        self.assertEqual("complete", result.completeness)
        self.assertEqual("fixture", result.messages[0].content["text"])
        self.assertFalse(paths[0].exists())

    def test_unread_image_does_not_change_complete_range(self):
        row = {**self.row, "type": "image"}
        data = {"username": "wxid_fixture", "count": 1, "message_items": [row],
                "message_shards_complete": True}
        query = QuerySpec(self.query.conversation, self.query.range, kinds=None)
        with patch.object(self.adapter, "_run", side_effect=[[self.contact], data]):
            result = self.adapter.read(query)
        self.assertEqual("complete", result.completeness)
        self.assertEqual("not_read", result.messages[0].status)

    def test_partial_records_specific_shard_failures(self):
        data = {"username": "wxid_fixture", "count": 1, "message_items": [self.row],
                "message_shards_complete": False, "message_shard_failures": 1}
        with patch.object(self.adapter, "_run", side_effect=[[self.contact], data]):
            result = self.adapter.read(self.query)
        self.assertEqual("partial", result.completeness)
        self.assertIn("aurevior_shard_read_failures", result.limitations)

    def test_exceeding_result_limit_marks_partial(self):
        data = {"username": "wxid_fixture", "count": 2,
                "message_items": [self.row, {**self.row, "id": 2}], "message_shards_complete": True}
        with patch("im_bridge.adapters.wechat.adapter._HISTORY_LIMIT", 1):
            with patch.object(self.adapter, "_run", side_effect=[[self.contact], data]):
                result = self.adapter.read(self.query)
        self.assertEqual("partial", result.completeness)
        self.assertIn("aurevior_result_limit", result.limitations)
        self.assertEqual(1, len(result.messages))

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

    def test_shard_scan_distinguishes_no_matching_table_from_unreadable_shard(self):
        runner = Path(__file__).resolve().parents[1] / "scripts" / "run-aurevior.py"
        checked_tables = runpy.run_path(str(runner))["checked_message_tables"]
        with tempfile.TemporaryDirectory() as directory:
            scope = Path(directory)
            empty, good, broken = (scope / f"{name}.db" for name in ("empty", "good", "broken"))
            sqlite3.connect(empty).close()
            table = "Msg_" + hashlib.md5(b"wxid_fixture").hexdigest()
            connection = sqlite3.connect(good)
            connection.execute(f"CREATE TABLE [{table}] (create_time INTEGER)")
            connection.close()
            broken.write_bytes(b"not sqlite")
            coverage = {}
            paths = {"empty": empty, "good": good, "broken": broken}
            matches = checked_tables(coverage)("wxid_fixture", paths, paths)
        self.assertEqual({"checked": 2, "failures": 1}, coverage)
        self.assertEqual([table], [match["table_name"] for match in matches])


if __name__ == "__main__":
    unittest.main()
