"""FastAPI 应用入口。"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1 import router as api_v1_router
from app.bootstrap import bootstrap_all_registries
from app.config import settings
from app.schemas.common import ApiResponse


def _error_message(detail: object) -> str:
    """将异常 detail 转为前端可读的 message。"""
    if isinstance(detail, str):
        return detail
    if isinstance(detail, list):
        parts = []
        for item in detail:
            if isinstance(item, dict) and "msg" in item:
                loc = item.get("loc", ())
                loc_str = ".".join(str(x) for x in loc if x != "body")
                parts.append(f"{loc_str}: {item['msg']}" if loc_str else item["msg"])
            else:
                parts.append(str(item))
        return "; ".join(parts) if parts else "Validation error"
    return str(detail)


def _database_outage_message(exc: Exception) -> str | None:
    """把数据库连不上的异常翻成前端能读懂的信息；不是连接类异常则返回 None。

    为什么存在：Neon 免费额度用完时 Postgres 会拒绝连接（"exceeded the quota"），
    如果只回 500「Internal server error」，用户以为是程序坏了；这里和 Blob 暂停一样给出原因与出路。
    """
    from sqlalchemy.exc import DBAPIError

    module = type(exc).__module__ or ""
    if not isinstance(exc, DBAPIError) and not module.startswith("psycopg"):
        return None
    text = str(exc).lower()
    if "exceeded the quota" in text:
        return "Database quota exceeded: Neon 数据库已超出免费额度，暂时无法读写；请在 Neon 控制台升级套餐或等待额度重置"
    if "connection" in text and ("failed" in text or "refused" in text or "timed out" in text or "is bad" in text):
        return "Database unavailable: 数据库暂时无法连接，请稍后重试"
    return None


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """HTTP 异常统一为 { code, message, data: null }；数据库连接失败回 503 并说明原因。"""
    from fastapi import HTTPException

    if isinstance(exc, HTTPException):
        code = exc.status_code
        message = _error_message(exc.detail)
    elif (outage := _database_outage_message(exc)) is not None:
        code = 503
        message = outage
    else:
        code = 500
        message = "Internal server error"
    body = ApiResponse[None](code=code, message=message, data=None, meta=None).model_dump()
    return JSONResponse(status_code=code, content=body)


async def validation_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """422 校验异常统一为 { code: 422, message, data: null }。"""
    assert isinstance(exc, RequestValidationError)
    message = _error_message(exc.errors())
    body = ApiResponse[None](code=422, message=message, data=None, meta=None).model_dump()
    return JSONResponse(status_code=422, content=body)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时初始化，关闭时清理。"""
    # 启动时：供应商注册 + 任务执行器注册（幂等）
    bootstrap_all_registries()
    # 无 init 容器的环境（Vercel）：建表 + 系统提示词 + 方舟供应商（幂等，失败不阻断启动）
    from app.deploy_runtime import ensure_bootstrapped

    await ensure_bootstrapped()
    yield
    # 关闭时：清理资源
    pass


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# 统一错误响应格式：{ code, message, data: null }
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(Exception, http_exception_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if settings.auto_init_db:

    @app.middleware("http")
    async def _ensure_bootstrapped_middleware(request: Request, call_next):
        """部分 serverless 运行时不触发 ASGI lifespan，这里在首个请求时兜底执行部署引导。"""
        from app.deploy_runtime import ensure_bootstrapped

        await ensure_bootstrapped()
        return await call_next(request)


app.include_router(api_v1_router, prefix=settings.api_v1_prefix)
# 影视技能路由同时挂到主应用，保证 /api/v1/film 一定可访问


@app.get("/health")
async def health():
    """健康检查。"""
    from app.schemas.common import success_response
    return success_response({"status": "ok"})
