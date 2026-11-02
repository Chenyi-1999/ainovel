"""Small internal auth service. Nginx must overwrite X-Forwarded-Proto and Host.

Only the reverse proxy may reach this service. Configuration and signing keys must
be injected through /run/auth.json; upstream application configuration is untouched.
"""

import hashlib
import hmac
import html
import json
import re
import secrets
import time
from dataclasses import dataclass
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlsplit


SESSION_SECONDS = 8 * 60 * 60
COOKIE_NAME = "lab_access_v1"
MAX_BODY = 8192
MAX_TARGET = 2048
TOKEN_RE = re.compile(r"v1\.([0-9]{1,12})\.([0-9a-f]{32})\.([0-9a-f]{64})\Z")
HOST_RE = re.compile(r"(?:[A-Za-z0-9.-]+|\[[0-9A-Fa-f:]+\])(?::[0-9]{1,5})?\Z")
BAD_ESCAPE = re.compile(r"%(?![0-9A-Fa-f]{2})")


@dataclass(frozen=True)
class AuthConfig:
    username: str
    password_salt: bytes
    password_hash: bytes
    session_secret: bytes

    @classmethod
    def load(cls, path="/run/auth.json"):
        # Fail closed before opening the socket. No default credentials or keys.
        raw = Path(path).read_bytes()
        if len(raw) > 4096:
            raise ValueError("Authentication configuration is too large")
        data = json.loads(raw)
        if not isinstance(data, dict) or set(data) != {
            "username", "password_salt", "password_hash", "session_secret"
        }:
            raise ValueError("Invalid authentication configuration fields")
        username = data["username"]
        if not isinstance(username, str) or not 1 <= len(username.encode("utf-8")) <= 128:
            raise ValueError("Invalid authentication username")
        if any(ord(c) < 32 or ord(c) == 127 for c in username):
            raise ValueError("Invalid authentication username")

        def hex_bytes(name, minimum, maximum):
            value = data[name]
            if not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]+", value):
                raise ValueError("Invalid authentication key format")
            if len(value) % 2 or not minimum <= len(value) // 2 <= maximum:
                raise ValueError("Invalid authentication key length")
            return bytes.fromhex(value)

        return cls(username, hex_bytes("password_salt", 16, 64),
                   hex_bytes("password_hash", 32, 32), hex_bytes("session_secret", 32, 32))

    def credentials_valid(self, username, password):
        candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                                        self.password_salt, 200000)
        user_valid = hmac.compare_digest(username.encode("utf-8"), self.username.encode("utf-8"))
        password_valid = hmac.compare_digest(candidate, self.password_hash)
        return user_valid & password_valid

    def issue_token(self, now=None):
        expiry = int(time.time() if now is None else now) + SESSION_SECONDS
        payload = f"v1.{expiry}.{secrets.token_hex(16)}"
        signature = hmac.new(self.session_secret, payload.encode("ascii"), hashlib.sha256).hexdigest()
        return f"{payload}.{signature}"

    def token_valid(self, token, now=None):
        if not isinstance(token, str) or len(token) > 128:
            return False
        match = TOKEN_RE.fullmatch(token)
        if not match:
            return False
        payload, signature = token.rsplit(".", 1)
        expected = hmac.new(self.session_secret, payload.encode("ascii"), hashlib.sha256).hexdigest()
        signature_valid = hmac.compare_digest(signature, expected)
        current = int(time.time() if now is None else now)
        return signature_valid & (current < int(match[1]) <= current + SESSION_SECONDS)


def safe_target(value):
    """Return a local redirect, checking nested encoding before reflecting a URL."""
    if not isinstance(value, str) or not value or len(value) > MAX_TARGET:
        return "/"
    decoded = value
    for _ in range(6):
        if (not decoded.startswith("/") or decoded.startswith("//")
                or "\\" in decoded or any(ord(c) <= 32 or ord(c) == 127 for c in decoded)
                or BAD_ESCAPE.search(decoded)):
            return "/"
        try:
            parts = urlsplit(decoded)
            if parts.scheme or parts.netloc:
                return "/"
            further = unquote(decoded, encoding="utf-8", errors="strict")
        except (ValueError, UnicodeError):
            return "/"
        if further == decoded:
            # HTTP headers are Latin-1; require browser-encoded non-ASCII paths.
            return value if value.isascii() else "/"
        decoded = further
    return "/"


class AuthHandler(BaseHTTPRequestHandler):
    server_version = "LabAuth"

    @property
    def config(self):
        return self.server.auth_config

    def log_message(self, format, *args):
        # Base logging includes request targets, which may contain private values.
        pass

    def send_error(self, code, message=None, explain=None):
        # Include no-store for parser errors and unsupported HTTP methods as well.
        self.close_connection = True
        self.reply(code, headers=[("Connection", "close")])

    def reply(self, status, body=b"", headers=()):
        self.send_response(status)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        for name, value in headers:
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def single_header(self, name):
        values = self.headers.get_all(name, [])
        return values[0] if len(values) == 1 else None

    def origin(self):
        proto = self.single_header("X-Forwarded-Proto")
        host = self.single_header("Host")
        if proto not in ("http", "https") or not host or not HOST_RE.fullmatch(host):
            return None
        try:
            parsed = urlsplit(f"{proto}://{host}")
            if parsed.port is not None and not 1 <= parsed.port <= 65535:
                return None
        except ValueError:
            return None
        return f"{proto}://{host}"

    def has_session(self):
        raw = self.single_header("Cookie")
        if not raw or len(raw) > 8192:
            return False
        # Reject duplicate auth cookies rather than depending on parser order.
        if sum(part.strip().split("=", 1)[0] == COOKIE_NAME for part in raw.split(";")) != 1:
            return False
        try:
            cookie = SimpleCookie()
            cookie.load(raw)
            return COOKIE_NAME in cookie and self.config.token_valid(cookie[COOKIE_NAME].value)
        except CookieError:
            return False

    def cookie(self, token, clear=False):
        secure = "; Secure" if self.single_header("X-Forwarded-Proto") == "https" else ""
        return (f"{COOKIE_NAME}={token}; Path=/; HttpOnly; SameSite=Lax; "
                f"Max-Age={0 if clear else SESSION_SECONDS}{secure}")

    def login_page(self, target="/", failed=False):
        message = "用户名或密码错误，请重试。" if failed else "请输入试用账号和密码。"
        nonce = secrets.token_urlsafe(18)
        script = """const form=document.querySelector('form'),button=form.querySelector('button');
let pending=false;
async function login(event){
  event.preventDefault();if(pending)return;
  if(!form.checkValidity()){form.reportValidity();return;}
  pending=true;button.disabled=true;
  try{
    const response=await fetch('/_lab/login',{method:'POST',credentials:'same-origin',
      headers:{'Content-Type':'application/x-www-form-urlencoded','Accept':'application/json'},
      body:new URLSearchParams(new FormData(form))});
    if(!response.ok){document.querySelector('#message').textContent='登录未成功，请检查账号和密码后重试。';return;}
    const result=await response.json();window.location.assign(result.next);
  }catch{document.querySelector('#message').textContent='连接失败，请稍后重试。';}
  finally{pending=false;button.disabled=false;}
}
form.addEventListener('submit',login);button.addEventListener('click',login);"""
        body = f"""<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>参考项目试用登录</title>
<style>body{{font:16px system-ui;background:#f4f6fa;color:#18253a;margin:0;padding:8vh 24px}}
main{{max-width:360px;margin:auto;background:white;padding:32px;border-radius:12px}}
label,input,button{{display:block;width:100%;box-sizing:border-box}}input,button{{padding:12px;margin:8px 0 20px}}
button{{background:#244e99;color:white;border:0;border-radius:6px}}h1{{font-size:24px}}</style>
<main><h1>参考项目试用</h1><p id="message">{message}</p><form method="post" action="/_lab/login">
<input type="hidden" name="next" value="{html.escape(safe_target(target), quote=True)}">
<label for="username">用户名</label><input id="username" name="username" autocomplete="username" required maxlength="128">
<label for="password">密码</label><input id="password" name="password" type="password" autocomplete="current-password" required>
<button type="submit">登录</button></form></main><script nonce="{nonce}">{script}</script></html>""".encode("utf-8")
        self.reply(401 if failed else 200, body, [
            ("Content-Type", "text/html; charset=utf-8"),
            ("Content-Security-Policy", f"default-src 'none'; style-src 'unsafe-inline'; script-src 'nonce-{nonce}'; connect-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'"),
            ("Referrer-Policy", "same-origin"),
        ])

    def do_GET(self):
        try:
            parsed = urlsplit(self.path)
        except ValueError:
            self.reply(400)
            return
        if parsed.path == "/_lab/verify":
            self.reply(204 if self.has_session() else 401)
        elif parsed.path == "/_lab/login":
            try:
                if len(parsed.query) > 8192:
                    raise ValueError()
                query = parse_qsl(parsed.query, keep_blank_values=True, max_num_fields=16,
                                  encoding="utf-8", errors="strict")
                targets = [value for key, value in query if key == "next"]
                target = targets[0] if len(targets) == 1 else "/"
            except (ValueError, UnicodeError):
                target = "/"
            self.login_page(target)
        elif parsed.path == "/_lab/logout":
            self.reply(303, headers=[("Location", "/_lab/login"),
                                     ("Set-Cookie", self.cookie("", clear=True))])
        else:
            self.reply(404)

    def reject_post(self, status):
        # Never leave an unread or oversized body on a reusable connection.
        self.close_connection = True
        self.reply(status, headers=[("Connection", "close")])

    def do_POST(self):
        if self.path != "/_lab/login":
            self.reject_post(404)
            return
        expected_origin = self.origin()
        if not expected_origin or self.single_header("Origin") != expected_origin:
            self.reject_post(403)
            return
        content_type = self.single_header("Content-Type")
        if not content_type or content_type.lower() not in (
                "application/x-www-form-urlencoded",
                "application/x-www-form-urlencoded; charset=utf-8"):
            self.reject_post(415)
            return
        length = self.single_header("Content-Length")
        if self.headers.get_all("Transfer-Encoding") or not length or not re.fullmatch(r"[0-9]{1,10}", length):
            self.reject_post(400)
            return
        size = int(length)
        if size > MAX_BODY:
            self.reject_post(413)
            return
        try:
            body = self.rfile.read(size)
            if len(body) != size:
                raise ValueError()
            form = body.decode("utf-8", errors="strict")
            if BAD_ESCAPE.search(form):
                raise ValueError()
            pairs = parse_qsl(form, keep_blank_values=True, strict_parsing=True,
                             max_num_fields=3, encoding="utf-8", errors="strict")
            fields = dict(pairs)
            if len(pairs) != len(fields) or set(fields) != {"username", "password", "next"}:
                raise ValueError()
        except (ValueError, UnicodeError):
            self.reject_post(400)
            return
        target = safe_target(fields["next"])
        wants_json = self.single_header("Accept") == "application/json"
        if not self.config.credentials_valid(fields["username"], fields["password"]):
            if wants_json:
                self.reply(401, b'{"error":"invalid_credentials"}', [("Content-Type", "application/json")])
            else:
                self.login_page(target, failed=True)
            return
        if wants_json:
            self.reply(200, json.dumps({"next": target}).encode("utf-8"), [
                ("Content-Type", "application/json; charset=utf-8"),
                ("Set-Cookie", self.cookie(self.config.issue_token()))])
            return
        self.reply(303, headers=[("Location", target),
                                 ("Set-Cookie", self.cookie(self.config.issue_token()))])

    def setup(self):
        super().setup()
        self.connection.settimeout(10)


def create_server(address, config):
    server = ThreadingHTTPServer(address, AuthHandler)
    server.daemon_threads = True
    server.auth_config = config
    return server


if __name__ == "__main__":
    configuration = AuthConfig.load()
    with create_server(("0.0.0.0", 8080), configuration) as server:
        server.serve_forever()
