import csv
import hashlib
import json
import time
from pathlib import Path
from statistics import mean

from celery.utils.log import get_task_logger

from app.celery_app import celery_app
from app.metrics import TASK_PROCESSING_DURATION, TASKS_COMPLETED, TASKS_FAILED
from app.models import TaskState
from app.storage import TaskStorage, utc_now

logger = get_task_logger(__name__)


def _analyze_csv(path: Path) -> dict:
    rows = 0
    columns: set[str] = set()
    numeric_values: list[float] = []

    with path.open("r", encoding="utf-8", errors="ignore", newline="") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames:
            columns.update(reader.fieldnames)
        for row in reader:
            rows += 1
            for value in row.values():
                try:
                    numeric_values.append(float(value))
                except (TypeError, ValueError):
                    continue

    return {
        "kind": "csv_analysis",
        "rows": rows,
        "columns": sorted(columns),
        "numeric_values": len(numeric_values),
        "numeric_average": round(mean(numeric_values), 4) if numeric_values else None,
    }


def _analyze_text(path: Path) -> dict:
    content = path.read_text(encoding="utf-8", errors="ignore")
    words = [word for word in content.replace("\n", " ").split(" ") if word.strip()]
    return {
        "kind": "text_analysis",
        "characters": len(content),
        "lines": content.count("\n") + 1 if content else 0,
        "words": len(words),
    }


def _file_fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def process_file(path: Path, original_filename: str) -> dict:
    extension = path.suffix.lower()
    base_result = {
        "original_filename": original_filename,
        "stored_filename": path.name,
        "size_bytes": path.stat().st_size,
        "sha256": _file_fingerprint(path),
    }

    if extension == ".csv":
        analysis = _analyze_csv(path)
    elif extension in {".txt", ".log", ".md", ".json"}:
        analysis = _analyze_text(path)
        if extension == ".json":
            try:
                json.loads(path.read_text(encoding="utf-8"))
                analysis["valid_json"] = True
            except json.JSONDecodeError:
                analysis["valid_json"] = False
    else:
        analysis = {"kind": "binary_metadata"}

    return {**base_result, **analysis}


@celery_app.task(
    name="process_uploaded_file",
    bind=True,
    autoretry_for=(OSError,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def process_uploaded_file(self, task_id: str, file_path: str, original_filename: str) -> dict:
    storage = TaskStorage()
    started_at = utc_now()
    storage.update(task_id, status=TaskState.running, started_at=started_at)
    start = time.perf_counter()

    try:
        result = process_file(Path(file_path), original_filename)
        elapsed = time.perf_counter() - start
        TASK_PROCESSING_DURATION.observe(elapsed)
        TASKS_COMPLETED.inc()
        storage.update(
            task_id,
            status=TaskState.completed,
            finished_at=utc_now(),
            duration_seconds=round(elapsed, 4),
            result=result,
        )
        logger.info("Task %s completed in %.2fs", task_id, elapsed)
        return result
    except Exception as exc:
        TASKS_FAILED.inc()
        elapsed = time.perf_counter() - start
        storage.update(
            task_id,
            status=TaskState.failed,
            finished_at=utc_now(),
            duration_seconds=round(elapsed, 4),
            error=str(exc),
        )
        logger.exception("Task %s failed", task_id)
        raise
