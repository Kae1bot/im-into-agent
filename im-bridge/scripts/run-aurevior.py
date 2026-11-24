"""Run only the read commands included in the AuRevior Skill."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "vendor"))


def usable_media(data, account: Path):
    for row in data.get("message_items", ()):
        media = row.get("media")
        if not isinstance(media, dict) or not media.get("exists"):
            continue
        media.pop("bridge_verified_path", None)
        candidate = media.get("path")
        if isinstance(candidate, str):
            path = Path(candidate).resolve()
            if path.is_relative_to(account) and path.is_file():
                media["bridge_verified_path"] = str(path)


def check_config(config: Path):
    if not config.is_file():
        return None, "key_missing"
    try:
        payload = json.loads(config.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return None, "config_invalid"
        db_dir = Path(payload["db_dir"])
        if not db_dir.is_absolute() or not db_dir.is_dir():
            return None, "source_unavailable"
        key_file = (config.parent / payload.get("keys_file", "all_keys.json")).resolve()
        if not key_file.is_relative_to(config.parent):
            return None, "config_invalid"
        if not key_file.is_file():
            return None, "key_missing"
        keys = json.loads(key_file.read_text(encoding="utf-8"))
        if not isinstance(keys, dict):
            return None, "config_invalid"
        if not any(isinstance(entry, dict) and entry.get("enc_key")
                   for name, entry in keys.items() if not name.startswith("_")):
            return None, "key_missing"
    except (KeyError, OSError, TypeError, ValueError):
        return None, "config_invalid"
    return db_dir, None


def main():
    from click.testing import CliRunner
    from wechat_cli import keys
    from wechat_cli.main import cli

    if sys.argv[1:] == ["--version"]:
        result = CliRunner().invoke(cli, ["--version"])
        print(result.stdout.strip())
        return result.exit_code
    if len(sys.argv) == 3 and sys.argv[1] == "--check-config":
        _, error = check_config(Path(sys.argv[2]).resolve())
        if error:
            print(json.dumps({"ok": False, "error": {"code": error}}))
            return 3 if error == "key_missing" else 2
        print(json.dumps({"ok": True, "status": "config_validated", "live_read_verified": False}))
        return 0
    if len(sys.argv) < 4 or sys.argv[1] != "--config" or sys.argv[3] not in ("contacts", "history"):
        return 2
    config = Path(sys.argv[2]).resolve()
    db_dir, error = check_config(config)
    if error:
        return 3 if error == "key_missing" else 2

    def unavailable(*_args, **_kwargs):
        raise RuntimeError("aurevior_read_only_keys_unavailable")

    keys.extract_keys = unavailable
    result = CliRunner().invoke(cli, sys.argv[1:])
    if result.exit_code:
        return 3 if "aurevior_read_only_keys_unavailable" in result.stderr else 1
    try:
        data = json.loads(result.stdout)
        if sys.argv[3] == "history":
            usable_media(data, db_dir.resolve().parent)
    except (OSError, TypeError, ValueError):
        return 1
    print(json.dumps(data, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
