"""Celery 应用实例。

最小落地原则：
- 仅把 Celery 当作执行层与 broker 客户端；
- 任务状态/结果真相仍然回写 GenerationTask；
- 第一阶段不依赖 Celery result backend。

部署形态：
- 本地 / Docker：Redis broker（`redis://...`），由 `celery worker` 进程消费；
- Vercel：`vercel://` broker（Vercel Queues，经 `vercel-celery` 集成），
  由 `backend/worker.py` 声明的 queue subscriber 函数消费（见 pyproject.toml 的 tool.vercel.subscribers）。
"""

from celery import Celery
from celery.signals import worker_process_init
from kombu import Queue

from app.config import settings
from app.core.db import reset_db_runtime

_BROKER_URL = settings.celery_broker_url or ""
_USE_VERCEL_QUEUES = _BROKER_URL.startswith("vercel")

if _USE_VERCEL_QUEUES:
    # 注册 vercel:// / vercel-push:// / vercel-poll:// kombu transport 与 Runtime Cache result backend。
    from vercel.integrations.celery import install_vercel_celery_integration

    install_vercel_celery_integration()


celery_app = Celery(
    "jellyfish",
    broker=_BROKER_URL,
    include=["app.tasks.execute_task"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_ignore_result=True,
    timezone="Asia/Shanghai",
    enable_utc=False,
    # 显式声明队列，Vercel 构建期据此生成 queue-triggered 函数（topic: celery-jellyfish-celery）。
    task_default_queue="celery",
    task_queues=[Queue("celery")],
)

if _USE_VERCEL_QUEUES:
    celery_app.conf.broker_transport_options = {
        # 视频生成会轮询供应商数分钟；租约需覆盖单个任务执行时长。
        "lease_duration": 300,
    }


@worker_process_init.connect
def _reset_async_db_runtime(**_: object) -> None:
    """Celery prefork 子进程启动后，重建 async DB 运行时。"""

    reset_db_runtime()
