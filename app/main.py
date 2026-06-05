import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, Request, UploadFile, status
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, generate_latest, multiprocess
from redis import Redis
from redis.exceptions import RedisError

from app.config import get_settings
from app.metrics import API_REQUEST_DURATION, API_REQUESTS, REDIS_QUEUE_SIZE, TASKS_CREATED
from app.models import ErrorResponse, HealthResponse, TaskAccepted, TaskStatus
from app.storage import TaskStorage
from app.tasks import process_uploaded_file

settings = get_settings()
storage = TaskStorage()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    settings.task_storage_path.mkdir(parents=True, exist_ok=True)
    multiproc_path = settings.prometheus_multiproc_dir
    if multiproc_path:
        Path(multiproc_path).mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(
    title=settings.app_name,
    description="REST API that accepts heavy jobs, delegates them to Celery, and exposes Prometheus metrics.",
    version="1.0.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def collect_http_metrics(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    route = request.scope.get("route")
    path = route.path if route else request.url.path
    elapsed = time.perf_counter() - start
    API_REQUEST_DURATION.labels(request.method, path).observe(elapsed)
    API_REQUESTS.labels(request.method, path, response.status_code).inc()
    return response


@app.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    return HealthResponse(service=settings.app_name)


@app.post(
    "/tasks",
    response_model=TaskAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    responses={413: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    tags=["tasks"],
)
async def create_task(request: Request, file: UploadFile = File(...)) -> TaskAccepted:
    if not file.filename:
        raise HTTPException(status_code=422, detail="A filename is required.")

    task_id = str(uuid4())
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    extension = Path(file.filename).suffix.lower()
    destination = settings.upload_dir / f"{task_id}{extension}"

    bytes_written = 0
    with destination.open("wb") as output:
        while chunk := await file.read(1024 * 1024):
            bytes_written += len(chunk)
            if bytes_written > settings.max_upload_bytes:
                destination.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"File exceeds the {settings.max_upload_mb} MB upload limit.",
                )
            output.write(chunk)

    if bytes_written == 0:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail="Uploaded file is empty.")

    storage.create(task_id=task_id, filename=file.filename)
    TASKS_CREATED.inc()
    process_uploaded_file.delay(task_id, str(destination), file.filename)

    return TaskAccepted(task_id=task_id, status_url=str(request.url_for("get_task_status", task_id=task_id)))


@app.get("/tasks/{task_id}", response_model=TaskStatus, responses={404: {"model": ErrorResponse}}, tags=["tasks"])
def get_task_status(task_id: str) -> TaskStatus:
    task = storage.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@app.get("/tasks", response_model=list[TaskStatus], tags=["tasks"])
def list_tasks(limit: int = 25) -> list[TaskStatus]:
    return storage.list()[: max(1, min(limit, 100))]


@app.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    try:
        redis = Redis.from_url(settings.redis_url, socket_connect_timeout=1, socket_timeout=1)
        REDIS_QUEUE_SIZE.labels("celery").set(redis.llen("celery"))
    except RedisError:
        REDIS_QUEUE_SIZE.labels("celery").set(-1)

    if settings.prometheus_multiproc_dir:
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
        payload = generate_latest(registry)
    else:
        payload = generate_latest()
    return Response(content=payload, media_type=CONTENT_TYPE_LATEST)
