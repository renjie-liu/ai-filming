"""方舟（BytePlus ModelArk / 火山方舟）HTTP 错误解析。

为什么存在：`httpx.Response.raise_for_status()` 只给出 “Client error '403 Forbidden'”，
丢失了方舟响应体里的错误码与说明（如 AccountOverdueError、ModelNotOpen、敏感内容拦截），
任务失败时用户无法得知真实原因。这里把错误码与说明保留在异常信息中，
前端据此映射为中文提示（见 front/src/utils/errorMessage.ts）。
"""

from __future__ import annotations

from typing import Any


class ArkApiError(RuntimeError):
    """方舟接口返回非 2xx 时抛出，消息格式：`Ark API <status> <code>: <message>`。"""

    def __init__(self, *, status_code: int, code: str, message: str) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(f"Ark API {status_code} {code or 'Error'}: {message}".strip())


def raise_for_ark_status(resp: Any) -> None:
    """响应为 4xx/5xx 时抛出 ArkApiError（保留方舟错误码与说明）；否则直接返回。"""
    if resp.status_code < 400:
        return
    code, message = "", ""
    try:
        err = (resp.json() or {}).get("error") or {}
        code = str(err.get("code") or "")
        message = str(err.get("message") or "")
    except Exception:  # noqa: BLE001 - 非 JSON 响应
        message = (getattr(resp, "text", "") or "")[:300]
    raise ArkApiError(status_code=resp.status_code, code=code, message=message[:500])
