from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.storage import TaskStorage


class FakeCeleryTask:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    def delay(self, task_id: str, file_path: str, filename: str) -> None:
        self.calls.append((task_id, file_path, filename))


def test_create_task_returns_202_and_queues_work(monkeypatch, tmp_path: Path):
    import app.main as main

    fake_task = FakeCeleryTask()
    monkeypatch.setattr(main, "storage", TaskStorage(tmp_path / "tasks"))
    monkeypatch.setattr(main.settings, "upload_dir", tmp_path / "uploads")
    monkeypatch.setattr(main, "process_uploaded_file", fake_task)

    client = TestClient(app)
    response = client.post("/tasks", files={"file": ("report.csv", b"name,value\nalpha,10\n", "text/csv")})

    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "QUEUED"
    assert payload["task_id"]
    assert payload["status_url"].endswith(f"/tasks/{payload['task_id']}")
    assert len(fake_task.calls) == 1

    status_response = client.get(f"/tasks/{payload['task_id']}")
    assert status_response.status_code == 200
    assert status_response.json()["filename"] == "report.csv"
