import os
from celery import Celery
from dotenv import load_dotenv

load_dotenv()

# Настройки Celery
celery_app = Celery(
    'ocr_worker',
    broker=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    backend=os.getenv("REDIS_URL", "redis://localhost:6379/0")
)

# Конфигурация
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='Europe/Moscow',
    enable_utc=True,
    worker_max_tasks_per_child=100,
    task_acks_late=True,
    broker_connection_retry_on_startup=True,
)