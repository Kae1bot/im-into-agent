"""Package the Windows read-only backend and its offline dependencies."""
import argparse
import hashlib
from pathlib import Path, PurePosixPath
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
SOURCE_WHEEL_SHA256 = "8a0ff346784412026cf24faf4b8bef171070559ee4c8c870bf8d921d9d1c4b97"
DEPENDENCIES = {
    "click": "click-8.5.1.dist-info",
    "Crypto": "pycryptodome-3.24.1.dist-info",
    "zstandard": "zstandard-0.25.0.dist-info",
}
PACKAGE_FILES = ("SKILL.md", "setup.ps1", "bridge.ps1", "scripts/runtime.ps1",
                 "scripts/run-bridge.py", "scripts/run-aurevior.py")
DEST = "im-into-agent-aurevior"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("wheel", "site-packages", "notices", "output"):
        parser.add_argument(f"--{option}", required=True, type=Path)
    args = parser.parse_args()
    if hashlib.sha256(args.wheel.read_bytes()).hexdigest() != SOURCE_WHEEL_SHA256:
        parser.error("Unexpected AuRevior wheel digest")
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp")
    try:
        with ZipFile(temporary, "w", ZIP_DEFLATED) as package:
            for name in PACKAGE_FILES:
                package.write(ROOT / name, f"{DEST}/{name}")
            package.write(args.notices, f"{DEST}/THIRD_PARTY_NOTICES.md")
            for source in sorted((ROOT / "src" / "im_bridge").rglob("*.py")):
                package.write(source, f"{DEST}/{source.relative_to(ROOT).as_posix()}")
            with ZipFile(args.wheel) as wheel:
                for entry in wheel.infolist():
                    relative = PurePosixPath(entry.filename)
                    if relative.is_absolute() or any(piece == ".." for piece in relative.parts) or "\\" in entry.filename:
                        raise ValueError("Unexpected wheel member")
                    if entry.is_dir() or relative.parts[:2] == ("wechat_cli", "bin"):
                        continue
                    if relative.parts[:2] == ("wechat_cli", "keys") and relative.name != "__init__.py":
                        continue
                    package.writestr(f"{DEST}/vendor/{relative}", wheel.read(entry))
            for module, metadata in DEPENDENCIES.items():
                for directory in (module, metadata):
                    source = args.site_packages / directory
                    if not source.is_dir():
                        raise FileNotFoundError(directory)
                    for path in sorted(source.rglob("*")):
                        if path.is_file() and "__pycache__" not in path.parts:
                            package.write(path, f"{DEST}/vendor/{path.relative_to(args.site_packages).as_posix()}")
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
