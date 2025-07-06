import os
from celery import Celery
from dotenv import load_dotenv

load_dotenv()

celery_app = Celery(
    'ocr_worker',
    broker=os.getenv("REDIS_URL"),
    backend=os.getenv("REDIS_URL")
)

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