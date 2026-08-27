from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


_TASK_ID = re.compile(r"^[A-Za-z0-9_-]{1,100}$")
_ALLOWED = {".pdf", ".csv", ".xlsx", ".json", ".txt", ".md"}


@dataclass(frozen=True)
class ResearchFile:
    id: str
    task_id: str
    name: str
    size: int
    created_at: str


class ResearchFileStore:
    def __init__(self, root: str | Path, *, max_bytes: int = 20 * 1024 * 1024) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.max_bytes = max_bytes

    def _task_dir(self, task_id: str) -> Path:
        if not _TASK_ID.fullmatch(task_id):
            raise ValueError("invalid task id")
        path = (self.root / task_id).resolve()
        path.relative_to(self.root.resolve())
        return path

    def save(self, task_id: str, name: str, content: bytes) -> ResearchFile:
        suffix = Path(name).suffix.casefold()
        if suffix not in _ALLOWED:
            raise ValueError("unsupported research file type")
        if len(content) > self.max_bytes:
            raise ValueError("research file exceeds size limit")
        task_dir = self._task_dir(task_id)
        task_dir.mkdir(parents=True, exist_ok=True)
        file_id = uuid.uuid4().hex
        safe_name = Path(name).name
        record = ResearchFile(file_id, task_id, safe_name, len(content), datetime.now(timezone.utc).isoformat())
        (task_dir / f"{file_id}{suffix}").write_bytes(content)
        (task_dir / f"{file_id}.json").write_text(json.dumps(asdict(record), ensure_ascii=False), encoding="utf-8")
        return record

    def read(self, task_id: str, file_id: str) -> bytes:
        task_dir = self._task_dir(task_id)
        meta_path = task_dir / f"{file_id}.json"
        if not meta_path.exists():
            raise KeyError(file_id)
        record = json.loads(meta_path.read_text(encoding="utf-8"))
        suffix = Path(record["name"]).suffix.casefold()
        path = task_dir / f"{file_id}{suffix}"
        if not path.exists():
            raise KeyError(file_id)
        return path.read_bytes()

    def list(self, task_id: str) -> list[ResearchFile]:
        task_dir = self._task_dir(task_id)
        if not task_dir.exists():
            return []
        return [ResearchFile(**json.loads(path.read_text(encoding="utf-8"))) for path in sorted(task_dir.glob("*.json"))]
