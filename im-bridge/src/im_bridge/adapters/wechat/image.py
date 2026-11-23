"""微信图片 key 推导 + 动态位置发现。

纯算法（md5 + 读 kvcomm 文件名），不需要独立进程、不需要内存扫描。
安装位置不假定默认路径：kvcomm 目录和 wxid 都动态发现。
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Iterable


def normalize_wxid(leaf: str) -> str:
    """把数据目录叶子名归一化，如 leokingleo_6d7d -> leokingleo。"""
    leaf = str(leaf or "").strip()
    if "_" in leaf:
        head, _, suffix = leaf.rpartition("_")
        if len(suffix) == 4 and all(c in "0123456789abcdefABCDEF" for c in suffix):
            return head
    return leaf


def find_kvcomm_dirs() -> list[Path]:
    """找微信 kvcomm 目录（含非默认安装位置）。"""
    roots: list[Path] = []
    appdata = os.environ.get("APPDATA", "")
    # APPDATA 本身已是 ...\AppData\Roaming
    base = Path(appdata) / "Tencent" / "xwechat"
    if base.is_dir():
        for sub in ("net", "ilink"):
            p = base / sub / "kvcomm"
            if p.is_dir():
                roots.append(p)
        radium = base / "radium" / "ilink"
        if radium.is_dir():
            try:
                for child in radium.iterdir():
                    p = child / "kvcomm"
                    if p.is_dir():
                        roots.append(p)
            except OSError:
                pass
    return roots


def collect_codes(dirs: Iterable[Path]) -> list[int]:
    """从 kvcomm 的 key_<code>_*.statistic 文件名提取 code。"""
    codes: set[int] = set()
    for d in dirs:
        try:
            for entry in d.iterdir():
                name = entry.name
                if not name.startswith("key_"):
                    continue
                code_text = name[4:].split("_", 1)[0]
                if code_text.isdigit():
                    codes.add(int(code_text))
        except OSError:
            continue
    return sorted(codes)


def derive_image_keys(db_root: str) -> list[str]:
    """从 db_root 推导候选 image key（md5(code+wxid) 前 16 个 hex 字符）。"""
    wxid = normalize_wxid(Path(db_root).name)
    codes = collect_codes(find_kvcomm_dirs())
    return [
        hashlib.md5(f"{code}{wxid}".encode()).hexdigest()[:16]
        for code in codes
    ]


def read_db_root(config_path: str) -> str | None:
    """从 wx-cli 配置文件里只读 db_root（不读 key 值）。"""
    try:
        cfg = json.loads(Path(config_path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    root = cfg.get("db_root")
    return root if isinstance(root, str) and root else None


def derive_image_key_from_config(config_path: str) -> str | None:
    """读 config 的 db_root → 推导 image key，返回第一个候选。"""
    root = read_db_root(config_path)
    if not root:
        return None
    keys = derive_image_keys(root)
    return keys[0] if keys else None
