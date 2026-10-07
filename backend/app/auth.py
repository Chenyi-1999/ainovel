import base64
import hashlib
import hmac
import os
import secrets
import time

from fastapi import HTTPException, Request

COOKIE = "ainovel_session"


def password_hash(password, salt=None, iterations=600_000):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), iterations).hex()
    return f"pbkdf2_sha256${iterations}${salt}${digest}"


def verify_password(password):
    stored = os.getenv("ADMIN_PASSWORD_HASH", "")
    try:
        algorithm, iterations, salt, digest = stored.split("$")
        if algorithm != "pbkdf2_sha256" or not 100_000 <= int(iterations) <= 2_000_000:
            return False
        return hmac.compare_digest(password_hash(password, salt, int(iterations)), stored)
    except (ValueError, TypeError):
        return False


def secret():
    value = os.getenv("SESSION_SECRET", "")
    if len(value) < 32:
        raise HTTPException(503, "登录配置尚未完成")
    return value.encode()


def issue_session():
    value = f"{int(time.time()) + 86400}.{secrets.token_hex(16)}"
    return value + "." + hmac.new(secret(), value.encode(), hashlib.sha256).hexdigest()


def require_auth(request: Request):
    token = request.cookies.get(COOKIE, "")
    try:
        expires, nonce, signature = token.split(".")
        expected = hmac.new(secret(), f"{expires}.{nonce}".encode(), hashlib.sha256).hexdigest()
        if int(expires) <= time.time() or not hmac.compare_digest(signature, expected):
            raise ValueError()
    except (ValueError, TypeError):
        raise HTTPException(401, "请先登录")


def check_origin(request: Request):
    # Same-site cookie plus origin enforcement protects all browser mutations.
    origin = request.headers.get("origin")
    if origin:
        from urllib.parse import urlsplit
        try:
            allowed = urlsplit(origin).netloc.lower() == request.headers.get("host", "").lower()
        except ValueError:
            allowed = False
        if not allowed:
            raise HTTPException(403, "请求来源不允许")
