"""Build the Windows x64 preview from fixed public source and wheel inputs."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import tomllib
from urllib.request import Request, urlopen
from zipfile import ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
LOCK = Path(__file__).with_name("windows-release-inputs.json")
SKILL = "im-into-agent-aurevior"
FIXED_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
PACKAGE_FILES = (
    "SKILL.md", "INSTALL.md", "setup.ps1", "bridge.ps1", "scripts/runtime.ps1",
    "scripts/run-bridge.py", "scripts/run-aurevior.py",
)
SOURCE_FILES = (
    "wechat_cli/__init__.py", "wechat_cli/version.py",
    "wechat_cli/commands/__init__.py", "wechat_cli/commands/contacts.py",
    "wechat_cli/commands/history.py", "wechat_cli/core/__init__.py",
    "wechat_cli/core/config.py", "wechat_cli/core/contacts.py", "wechat_cli/core/context.py",
    "wechat_cli/core/crypto.py", "wechat_cli/core/db_cache.py", "wechat_cli/core/forwarded.py",
    "wechat_cli/core/key_utils.py", "wechat_cli/core/media.py", "wechat_cli/core/messages.py",
    "wechat_cli/core/voice.py", "wechat_cli/output/__init__.py", "wechat_cli/output/formatter.py",
)


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify(path, expected):
    if digest(path) != expected:
        raise ValueError(f"SHA-256 mismatch for {path.name}")


def release_input(directory, entry, download):
    target = directory / entry["name"]
    if not target.is_file():
        if not download:
            raise FileNotFoundError(f"Missing {target.name}. Run with --download or supply the locked input.")
        directory.mkdir(parents=True, exist_ok=True)
        pending = target.with_suffix(".part")
        try:
            request = Request(entry["url"], headers={"User-Agent": "IM-into-Agent release builder"})
            with urlopen(request, timeout=25) as remote, pending.open("wb") as local:
                shutil.copyfileobj(remote, local)
            verify(pending, entry["sha256"])
            pending.replace(target)
        finally:
            pending.unlink(missing_ok=True)
    verify(target, entry["sha256"])
    return target


def write_entry(package, name, body):
    item = ZipInfo(f"{SKILL}/{name}", FIXED_TIMESTAMP)
    item.create_system = 3
    item.external_attr = 0o100644 << 16
    package.writestr(item, body)


def checkout_text(path):
    return path.read_bytes().replace(b"\r\n", b"\n")


def add_source(package, source_zip, revision):
    source_root = f"wechat-cli-{revision}"
    with ZipFile(source_zip) as source:
        for name in SOURCE_FILES:
            write_entry(package, f"vendor/{name}", source.read(f"{source_root}/{name}"))
        write_entry(package, "licenses/AuRevior-LICENSE.txt", source.read(f"{source_root}/LICENSE"))
        write_entry(package, "licenses/AuRevior-THIRD_PARTY_NOTICES.md",
                    source.read(f"{source_root}/THIRD_PARTY_NOTICES.md"))


def add_wheel(package, wheel_path, entry):
    with ZipFile(wheel_path) as wheel:
        for item in sorted(wheel.namelist()):
            if item.endswith("/"):
                continue
            path = PurePosixPath(item)
            if not path.parts or path.is_absolute() or ".." in path.parts or "\\" in item:
                raise ValueError("Unsafe wheel path")
            if path.parts[0] == entry["metadata"] and (
                path.name.casefold().startswith(("license", "notice", "copying"))
                or "licenses" in path.parts
            ):
                write_entry(package, f"licenses/{path.as_posix()}", wheel.read(item))
            if path.parts[0] == entry["module"] and path.suffix in (".py", ".pyd", ".dll") and (
                "SelfTest" not in path.parts and "tests" not in path.parts
            ):
                write_entry(package, f"vendor/{path.as_posix()}", wheel.read(item))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, default=ROOT.parent / "build" / "release-inputs")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--download", action="store_true")
    args = parser.parse_args()
    inputs = json.loads(LOCK.read_text(encoding="utf-8"))
    source = release_input(args.inputs, inputs["source"], args.download)
    wheels = [(release_input(args.inputs, entry, args.download), entry) for entry in inputs["wheels"]]
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    pending = output.with_suffix(".tmp")
    try:
        with ZipFile(pending, "w") as package:
            for name in PACKAGE_FILES:
                write_entry(package, name, checkout_text(ROOT / name))
            write_entry(package, "VERSION", (metadata["project"]["version"] + "\n").encode())
            for path in sorted((ROOT / "src" / "im_bridge").rglob("*.py")):
                write_entry(package, path.relative_to(ROOT).as_posix(), checkout_text(path))
            add_source(package, source, inputs["source"]["revision"])
            for wheel_path, entry in wheels:
                add_wheel(package, wheel_path, entry)
        pending.replace(output)
    finally:
        pending.unlink(missing_ok=True)
    checksum = f"{digest(output)}  {output.name}\n"
    output.with_suffix(output.suffix + ".sha256").write_text(checksum, encoding="ascii")
    print(checksum.strip())


if __name__ == "__main__":
    main()
