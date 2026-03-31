from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "tender_ai_worker",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.tasks.tender_analysis"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Almaty",
    enable_utc=True,
    imports=("app.tasks.tender_analysis",),
    broker_connection_retry_on_startup=True,
)