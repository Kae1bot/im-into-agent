"""Generate an artificial profile for the offline packaged-Skill smoke test."""
import ctypes
from contextlib import closing
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys

vendor, profile, account = map(Path, sys.argv[1:])
sys.path.insert(0, str(vendor))
from Crypto.Cipher import AES

database = ctypes.CDLL(str(Path(sys.base_prefix) / "DLLs" / "sqlite3.dll"))
database.sqlite3_open.argtypes = [ctypes.c_char_p, ctypes.POINTER(ctypes.c_void_p)]
database.sqlite3_file_control.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_void_p]
database.sqlite3_close.argtypes = [ctypes.c_void_p]
database.sqlite3_exec.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_void_p,
                                 ctypes.c_void_p, ctypes.c_void_p]
profile.mkdir()
account.mkdir(parents=True)
key = b"fixture only".ljust(32, b"-")
fake_iv = bytes(16)


def make_database(relative, schema, data):
    clear = profile / "fixture.sqlite"
    handle = ctypes.c_void_p()
    assert database.sqlite3_open(os.fsencode(clear), ctypes.byref(handle)) == 0
    reserve = ctypes.c_int(80)
    assert database.sqlite3_file_control(handle, b"main", 38, ctypes.byref(reserve)) == 0
    assert database.sqlite3_exec(handle, b"VACUUM", None, None, None) == 0
    assert database.sqlite3_close(handle) == 0
    with closing(sqlite3.connect(clear)) as connection:
        connection.executescript(schema)
        connection.executemany(data[0], data[1])
        connection.commit()
    content = clear.read_bytes()
    clear.unlink()
    assert content[20] == 80 and len(content) % 4096 == 0
    destination = account / relative
    destination.parent.mkdir(parents=True)
    with destination.open("wb") as output:
        for offset in range(0, len(content), 4096):
            page = content[offset:offset + 4096]
            start = 16 if offset == 0 else 0
            if start:
                output.write(b"synthetic-salt!!")
            output.write(AES.new(key, AES.MODE_CBC, fake_iv).encrypt(page[start:-80]))
            output.write(fake_iv + bytes(64))


chat_id = "wxid_fixture"
table = "Msg_" + hashlib.md5(chat_id.encode()).hexdigest()
make_database("contact/contact.db",
              "CREATE TABLE contact (username TEXT, nick_name TEXT, remark TEXT);",
              ("INSERT INTO contact VALUES (?, ?, ?)", [(chat_id, "Fixture", "")]))
start = int(datetime.fromisoformat("2025-11-30T00:00:00+08:00").timestamp())
message_rows = [
    (1, 1, start, 1, "included at start", 0),
    (2, 1, start + 1, 1, "included after start", 0),
    (3, 1, start + 86400, 1, "excluded at end", 0),
]
make_database("message/message_0.db",
              f"CREATE TABLE {table} (local_id INTEGER, local_type INTEGER, create_time INTEGER, "
              "real_sender_id INTEGER, message_content TEXT, WCDB_CT_message_content INTEGER);",
              (f"INSERT INTO {table} VALUES (?, ?, ?, ?, ?, ?)", message_rows))
(profile / "config.json").write_text(json.dumps({"db_dir": str(account)}), encoding="utf-8")
(profile / "all_keys.json").write_text(json.dumps({
    name: {"enc_key": key.hex()} for name in ("contact/contact.db", "message/message_0.db")
}), encoding="utf-8")
