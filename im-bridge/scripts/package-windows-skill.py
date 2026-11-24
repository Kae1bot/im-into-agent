"""Assemble the installable Windows x64 Skill from verified release inputs."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path, PurePosixPath
from zipfile import ZIP_DEFLATED, ZipFile

PYTHON_SHA256 = "90905e64a840557d8c1bc4f5b74db3d7ee85e3ffb217611cac1c7813acea4159"
ARCHIVE_NAME = "im-into-agent-windows-x64.zip"
SKILL_DIR = "im-into-agent"
LICENSES = ("wx-cli", "wcdb", "go", "purego", "klauspost-compress", "openssl", "sqlcipher", "zstd")


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("bin", "python-archive", "licenses", "output"):
        parser.add_argument(f"--{option}", type=Path, required=True)
    args = parser.parse_args()
    if sha256(args.python_archive) != PYTHON_SHA256:
        parser.error("The embedded Python archive SHA256 does not match.")

    root = Path(__file__).resolve().parents[1]
    files = {
        name: root / name for name in (
            "SKILL.md", "setup.ps1", "bridge.ps1", "scripts/runtime.ps1", "scripts/run-bridge.py"
        )
    }
    files["THIRD_PARTY_NOTICES.md"] = root.parent / "THIRD_PARTY_NOTICES.md"
    for path in sorted((root / "src" / "im_bridge").rglob("*.py")):
        files[path.relative_to(root).as_posix()] = path
    for name in ("wechat-cli.exe", "libWCDB.dll"):
        files[f"bin/{name}"] = args.bin / name
    for name in LICENSES:
        files[f"licenses/{name}.txt"] = args.licenses / f"{name}.txt"
    for path in files.values():
        if not path.is_file():
            parser.error(f"Missing input: {path}")

    args.output.mkdir(parents=True, exist_ok=True)
    archive = args.output / ARCHIVE_NAME
    with ZipFile(args.python_archive) as python_zip, ZipFile(archive, "w", ZIP_DEFLATED) as skill_zip:
        for name, source in files.items():
            skill_zip.writestr(f"{SKILL_DIR}/{name}", source.read_bytes())
        for name in python_zip.namelist():
            if PurePosixPath(name).name != name or "\\" in name:
                parser.error(f"Unexpected Python archive entry: {name}")
            skill_zip.writestr(f"{SKILL_DIR}/python/{name}", python_zip.read(name))
    digest = sha256(archive)
    archive.with_suffix(".zip.sha256").write_text(f"{digest}  {archive.name}\n", encoding="ascii")
    print(f"{archive.name}: {digest}")


if __name__ == "__main__":
    main()
