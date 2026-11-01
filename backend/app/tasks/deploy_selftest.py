"""部署自检 Celery 任务（不调用模型供应商，无费用）。"""

from __future__ import annotations

from app.core.celery_app import celery_app


@celery_app.task(name="deploy.selftest")
def run_deploy_selftest(token: str, enqueued_at: str) -> None:
    """worker 执行入口：记录执行时间与运行环境，供 `/api/v1/_deploy/selftest/{token}` 查询。"""
    from app.services.deploy_selftest import record_selftest_sync

    record_selftest_sync(token, enqueued_at)
