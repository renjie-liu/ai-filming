"""Vercel Queues subscriber 入口（Celery worker）。

Vercel 构建时会读取 pyproject.toml 中的 `[[tool.vercel.subscribers]] entrypoint = "worker:app"`，
内省 Celery app 声明的队列，并把它编译成由 Vercel Queues 推送触发的私有函数。
"""

from app.core.celery_app import celery_app
import app.tasks.execute_task  # noqa: F401  # 注册 task.execute
import app.tasks.deploy_selftest  # noqa: F401  # 注册 deploy.selftest

app = celery_app

__all__ = ["app"]
