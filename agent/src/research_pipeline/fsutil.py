# -*- coding: utf-8 -*-
"""研究管线运行目录的小件：原子写与内容寻址（Core，无行业词）。"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def atomic_write_text(path: "str | Path", text: str) -> None:
    """同目录临时文件 + os.replace，读方永远不会看到半个文件。"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp-" + str(os.getpid()))
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, p)


def write_json(path: "str | Path", obj) -> str:
    """JSON 落盘（UTF-8、ensure_ascii=False、尾换行），返回文件内容文本。"""
    text = json.dumps(obj, ensure_ascii=False, indent=2) + "\n"
    atomic_write_text(path, text)
    return text


def read_json_if_exists(path: "str | Path"):
    p = Path(path)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None


def now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="seconds")
