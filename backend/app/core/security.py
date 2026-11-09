"""密码哈希与会话令牌（纯标准库实现）。

为什么存在：登录系统只需要两件事——「密码不可逆地存下来」与「给浏览器一张可校验、会过期的会话凭证」。
`hashlib.scrypt` 与 HMAC-SHA256 足以胜任，避免为此引入 passlib / PyJWT 等依赖。

- 密码：`scrypt$<n>$<r>$<p>$<salt>$<hash>`，参数写进字符串，将来调参后老密码仍可校验。
- 令牌：`<base64url(json 负载)>.<base64url(hmac)>`，负载含用户 ID（`sub`）、签发（`iat`）与过期（`exp`）时间；
  密钥由 `services.auth` 从环境变量或启动元数据表取得。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_DKLEN = 32


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64decode(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def hash_password(password: str) -> str:
    """用随机盐 + scrypt 哈希密码，返回可直接入库的自描述字符串。"""
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=_DKLEN)
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${_b64encode(salt)}${_b64encode(digest)}"


def verify_password(password: str, stored: str) -> bool:
    """按存储串里的参数重算并常量时间比较；格式不对一律视为不匹配。"""
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = _b64decode(digest)
        actual = hashlib.scrypt(password.encode("utf-8"), salt=_b64decode(salt), n=int(n), r=int(r), p=int(p), dklen=len(expected))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def sign_token(payload: dict[str, Any], secret: str) -> str:
    """把负载编码并用 HMAC-SHA256 签名；负载应由调用方放入 `exp`。"""
    body = _b64encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signature = hmac.new(secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest()
    return f"{body}.{_b64encode(signature)}"


def read_token(token: str, secret: str, *, now: float | None = None) -> dict[str, Any] | None:
    """校验签名与过期时间，返回负载；任何不合法（篡改、过期、格式错）都返回 None。"""
    if not token or "." not in token:
        return None
    body, _, signature = token.rpartition(".")
    expected = hmac.new(secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest()
    try:
        if not hmac.compare_digest(_b64decode(signature), expected):
            return None
        payload = json.loads(_b64decode(body).decode("utf-8"))
    except (ValueError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None
    exp = payload.get("exp")
    current = time.time() if now is None else now
    if not isinstance(exp, (int, float)) or exp <= current:
        return None
    return payload


def new_secret() -> str:
    """生成一把新的签名密钥（URL 安全、约 64 个字符）。"""
    return secrets.token_urlsafe(48)


def new_invite_code() -> str:
    """生成易读的邀请码：8 位大写字母数字，去掉易混字符。"""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(8))
