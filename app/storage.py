import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.models import TaskState, TaskStatus


def utc_now() -> datetime:
    return datetime.now(UTC)


class TaskStorage:
    def __init__(self, base_path: Path | None = None) -> None:
        settings = get_settings()
        self.base_path = base_path or settings.task_storage_path
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _path_for(self, task_id: str) -> Path:
        return self.base_path / f"{task_id}.json"

    def create(self, task_id: str, filename: str) -> TaskStatus:
        now = utc_now()
        status = TaskStatus(
            task_id=task_id,
            status=TaskState.queued,
            filename=filename,
            created_at=now,
            updated_at=now,
        )
        self.save(status)
        return status

    def get(self, task_id: str) -> TaskStatus | None:
        path = self._path_for(task_id)
        if not path.exists():
            return None
        return TaskStatus.model_validate_json(path.read_text(encoding="utf-8"))

    def update(self, task_id: str, **changes: Any) -> TaskStatus:
        current = self.get(task_id)
        if current is None:
            raise FileNotFoundError(f"Task {task_id} not found")
        next_status = current.model_copy(update={**changes, "updated_at": utc_now()})
        self.save(next_status)
        return next_status

    def save(self, status: TaskStatus) -> None:
        path = self._path_for(status.task_id)
        payload = json.dumps(status.model_dump(mode="json"), indent=2, sort_keys=True)
        path.write_text(payload, encoding="utf-8")

    def list(self) -> list[TaskStatus]:
        tasks = [self.get(path.stem) for path in self.base_path.glob("*.json")]
        return sorted((task for task in tasks if task), key=lambda item: item.created_at, reverse=True)
