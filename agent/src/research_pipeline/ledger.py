# -*- coding: utf-8 -*-
"""取数账本（Core）：内存权威、磁盘审计副本。

编排器进程内的 Ledger 是唯一裁判（那几条不是模型改得了的）；
磁盘 ``_ledger.json`` 只是审计痕迹，守卫与校验器读磁盘副本时不拿它拦模型。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .fsutil import now_iso, write_json


@dataclass
class LedgerEntry:
    dataset: str
    params: dict
    status: str            # ok | empty | error
    file: str              # 相对 run 目录：fetch/<dataset>.json
    sha256: str
    rows: int
    stage: str
    started_at: str = field(default_factory=now_iso)
    error: str = ""


class Ledger:
    """dataset → 取数信封。同 dataset 只记一次（重试由编排器决定，账本不重复记）。"""

    def __init__(self) -> None:
        self._entries: "dict[str, LedgerEntry]" = {}

    def record(self, entry: LedgerEntry) -> bool:
        """记录一条；dataset 已有记录则跳过并返回 False。"""
        if entry.dataset in self._entries:
            return False
        self._entries[entry.dataset] = entry
        return True

    def get(self, dataset: str) -> "LedgerEntry | None":
        return self._entries.get(dataset)

    def has(self, dataset: str) -> bool:
        return dataset in self._entries

    def status_map(self) -> "dict[str, str]":
        return {d: e.status for d, e in self._entries.items()}

    def snapshot(self) -> "list[dict]":
        return [vars(e).copy() for e in self._entries.values()]

    def save_audit(self, run_dir: "str | Path") -> None:
        write_json(Path(run_dir) / "_ledger.json", {"entries": self.snapshot()})
