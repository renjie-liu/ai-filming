"""部署状态与自检接口（只读诊断；业务逻辑见 app.services.deploy_diagnostics / deploy_selftest）。"""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.schemas.common import ApiResponse, success_response

router = APIRouter()


@router.get("/_deploy/status", response_model=ApiResponse[dict])
async def deploy_status(
    probe_ark: bool = Query(False, description="是否对方舟 API 做只读连通性探测"),
    probe_models: bool = Query(False, description="是否对候选模型做零成本可用性探测（故意缺参请求，不产生生成）"),
) -> ApiResponse[dict]:
    """返回数据库、存储、任务执行方式与方舟接入状态（不含任何密钥）。"""
    from app.services.deploy_diagnostics import build_deploy_status

    data = await build_deploy_status(probe_ark=probe_ark, probe_model_availability=probe_models)
    return success_response(data=data)


@router.get("/_deploy/selftest", response_model=ApiResponse[dict])
async def deploy_selftest_start(
    llm: bool = Query(False, description="是否在任务中调用默认文本模型（一句极短请求，成本极低）"),
) -> ApiResponse[dict]:
    """按业务任务相同的执行方式分派自检任务，验证「分派 → 执行 → 数据库」链路；返回 token。

    使用 GET 便于在浏览器中直接打开（接口受部署保护；默认不调用任何模型供应商）。
    """
    from app.services.deploy_selftest import enqueue_selftest

    return success_response(data=enqueue_selftest(llm=llm))


@router.get("/_deploy/selftest/{token}", response_model=ApiResponse[dict])
async def deploy_selftest_result(token: str) -> ApiResponse[dict]:
    """查询自检结果：`done=false` 表示任务尚未执行完成。"""
    from app.services.deploy_selftest import read_selftest

    result = await read_selftest(token)
    return success_response(data={"token": token, "done": result is not None, "result": result})

