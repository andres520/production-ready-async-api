from prometheus_client import Counter, Gauge, Histogram

API_REQUESTS = Counter(
    "api_requests_total",
    "Total HTTP requests handled by the API.",
    ["method", "path", "status_code"],
)

API_REQUEST_DURATION = Histogram(
    "api_request_duration_seconds",
    "API request duration in seconds.",
    ["method", "path"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)

TASKS_CREATED = Counter("tasks_created_total", "Total background tasks accepted by the API.")
TASKS_COMPLETED = Counter("tasks_completed_total", "Total background tasks completed by workers.")
TASKS_FAILED = Counter("tasks_failed_total", "Total background tasks failed by workers.")

TASK_PROCESSING_DURATION = Histogram(
    "task_processing_duration_seconds",
    "Background task processing duration in seconds.",
    buckets=(0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120, 300),
)

REDIS_QUEUE_SIZE = Gauge("redis_queue_size", "Approximate Celery queue size in Redis.", ["queue"])
