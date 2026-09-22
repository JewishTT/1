import os
from celery import Celery

broker = os.getenv("REDIS_URL", "redis://localhost:6379/0")
backend = os.getenv("REDIS_BACKEND", broker)

celery_app = Celery("tracematrix", broker=broker, backend=backend)
if os.getenv("CELERY_ALWAYS_EAGER", "1") == "1":
    celery_app.conf.task_always_eager = True
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    result_expires=3600,
)

