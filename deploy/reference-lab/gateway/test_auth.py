"""Run with: python -m unittest discover -s deploy/reference-lab/gateway -v."""

import hashlib
import http.client
import json
import secrets
import tempfile
import threading
import time
import unittest
from pathlib import Path
from urllib.parse import urlencode

from auth import AuthConfig, COOKIE_NAME, MAX_BODY, SESSION_SECONDS, create_server, safe_target


class AuthenticationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.password = secrets.token_urlsafe(24)
        salt = secrets.token_bytes(16)
        cls.config = AuthConfig(
            "viewer", salt,
            hashlib.pbkdf2_hmac("sha256", cls.password.encode(), salt, 200000),
            secrets.token_bytes(32),
        )
        cls.server = create_server(("127.0.0.1", 0), cls.config)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=3)
        connection.request(method, path, body, headers or {})
        response = connection.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        connection.close()
        return result

    def login(self, username="viewer", password=None, target="/", origin="http://lab.test:18020",
              proto="http", headers=None):
        form = urlencode({"username": username, "password": self.password if password is None else password,
                          "next": target})
        request_headers = {"Host": "lab.test:18020", "X-Forwarded-Proto": proto,
                           "Content-Type": "application/x-www-form-urlencoded"}
        if origin is not None:
            request_headers["Origin"] = origin
        request_headers.update(headers or {})
        return self.request("POST", "/_lab/login", form, request_headers)

    def verify(self, token):
        return self.request("GET", "/_lab/verify", headers={"Cookie": f"{COOKIE_NAME}={token}"})

    def test_form_login_and_session_verification(self):
        status, headers, _ = self.login(target="/library?q=novel")
        self.assertEqual(status, 303)
        self.assertEqual(headers["Location"], "/library?q=novel")
        cookie = headers["Set-Cookie"]
        for attribute in ("Path=/", "HttpOnly", "SameSite=Lax", "Max-Age=28800"):
            self.assertIn(attribute, cookie)
        self.assertNotIn("Domain=", cookie)
        self.assertNotIn("Secure", cookie)
        self.assertEqual(self.verify(cookie.split(";", 1)[0].split("=", 1)[1])[0], 204)

    def test_bad_credentials_have_no_session(self):
        for username, password in (("viewer", "wrong"), ("other", self.password), ("", "")):
            with self.subTest(username=username):
                status, headers, body = self.login(username=username, password=password)
                self.assertEqual(status, 401)
                self.assertNotIn("Set-Cookie", headers)
                self.assertNotIn("WWW-Authenticate", headers)
                self.assertIn("用户名或密码错误".encode(), body)

    def test_verify_rejects_absent_invalid_expired_and_tampered_tokens(self):
        valid = self.config.issue_token()
        tampered = valid[:-1] + ("0" if valid[-1] != "0" else "1")
        expired = self.config.issue_token(now=time.time() - SESSION_SECONDS - 1)
        for token in ("", "garbage", "x" * 1000, tampered, expired):
            with self.subTest(token_length=len(token)):
                status, headers, _ = self.verify(token)
                self.assertEqual(status, 401)
                self.assertNotIn("WWW-Authenticate", headers)
        self.assertEqual(self.request("GET", "/_lab/verify")[0], 401)

    def test_expiry_boundary_and_tokens_are_random(self):
        token = self.config.issue_token(now=1000)
        self.assertTrue(self.config.token_valid(token, now=1000 + SESSION_SECONDS - 1))
        self.assertFalse(self.config.token_valid(token, now=1000 + SESSION_SECONDS))
        self.assertFalse(self.config.token_valid(token, now=999))
        self.assertNotEqual(self.config.issue_token(), self.config.issue_token())

    def test_duplicate_cookie_is_rejected(self):
        token = self.config.issue_token()
        self.assertEqual(self.request("GET", "/_lab/verify", headers={
            "Cookie": f"{COOKIE_NAME}={token}; {COOKIE_NAME}={token}"
        })[0], 401)

    def test_cross_origin_and_missing_origin_are_rejected(self):
        for origin in (None, "null", "https://lab.test:18020", "http://evil.test",
                       "http://lab.test:18020.evil.test", "http://lab.test:18020/"):
            with self.subTest(origin=origin):
                self.assertEqual(self.login(origin=origin)[0], 403)

    def test_proxy_protocol_is_required_and_secure_cookie_tracks_https(self):
        self.assertEqual(self.login(proto="https", origin="https://lab.test:18020")[0], 303)
        self.assertIn("; Secure", self.login(proto="https", origin="https://lab.test:18020")[1]["Set-Cookie"])
        for proto in ("", "ftp", "http,https"):
            self.assertEqual(self.login(proto=proto)[0], 403)

    def test_unsafe_redirects_return_root(self):
        unsafe = ("https://evil.test", "//evil.test", "/\\evil.test", "/%2fevil.test",
                  "/%252fevil.test", "/%5cevil.test", "/%255cevil.test", "/%0d%0aInjected:x",
                  "/%250d%250aInjected:x", "/x\r\nInjected:x", "/" + "x" * 2048,
                  "/%ff", "/bad%escape", "/a b", "javascript:alert(1)")
        for target in unsafe:
            with self.subTest(target=target):
                self.assertEqual(safe_target(target), "/")
        status, headers, _ = self.login(target="/%252fevil.test")
        self.assertEqual(status, 303)
        self.assertEqual(headers["Location"], "/")

    def test_safe_redirect_paths_are_preserved(self):
        for target in ("/", "/library?id=1&tab=read", "/%E4%B9%A6", "/page#section"):
            self.assertEqual(safe_target(target), target)

    def test_login_page_escapes_reflected_target_and_has_no_cache(self):
        target = '/page?x="/><script>alert(1)</script>'
        status, headers, body = self.request("GET", "/_lab/login?" + urlencode({"next": target}))
        self.assertEqual(status, 200)
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertIn(b"&quot;/&gt;&lt;script&gt;", body)
        self.assertNotIn(b"<script>", body)
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertEqual(headers['Referrer-Policy'], 'same-origin')
        self.assertIn("connect-src 'self'", headers['Content-Security-Policy'])
        nonce = headers['Content-Security-Policy'].split("script-src 'nonce-", 1)[1].split("'", 1)[0]
        self.assertIn(f'<script nonce="{nonce}">'.encode(), body)

    def test_fetch_login_has_cookie_and_safe_json_navigation(self):
        status, headers, body = self.login(target='//evil.test', headers={'Accept':'application/json'})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {'next':'/'})
        self.assertIn('HttpOnly', headers['Set-Cookie'])
        self.assertIn('application/json', headers['Content-Type'])
        token = headers['Set-Cookie'].split(';',1)[0].split('=',1)[1]
        self.assertEqual(self.verify(token)[0], 204)

    def test_fetch_login_retains_credential_and_origin_checks(self):
        status, headers, body = self.login(password='wrong', headers={'Accept':'application/json'})
        self.assertEqual(status, 401)
        self.assertNotIn('Set-Cookie', headers)
        self.assertEqual(json.loads(body), {'error':'invalid_credentials'})
        self.assertEqual(self.login(origin='null', headers={'Accept':'application/json'})[0], 403)

    def test_logout_clears_host_cookie(self):
        status, headers, _ = self.request("GET", "/_lab/logout", headers={"X-Forwarded-Proto": "https"})
        self.assertEqual(status, 303)
        self.assertEqual(headers["Location"], "/_lab/login")
        self.assertIn("Max-Age=0", headers["Set-Cookie"])
        self.assertIn("; Secure", headers["Set-Cookie"])

    def test_body_size_content_type_and_encoding_boundaries(self):
        headers = {"Host": "lab.test:18020", "X-Forwarded-Proto": "http",
                   "Origin": "http://lab.test:18020", "Content-Type": "application/x-www-form-urlencoded"}
        for body, status in ((b"x" * (MAX_BODY + 1), 413), (b"\xff", 400),
                             (b"username=%FF&password=x&next=/", 400),
                             (b"username=%ZZ&password=x&next=/", 400),
                             (b"username=x&password=x&next=/&next=//evil", 400),
                             (b"username=x&password=x", 400)):
            with self.subTest(body_length=len(body)):
                self.assertEqual(self.request("POST", "/_lab/login", body, headers)[0], status)
        self.assertEqual(self.login(headers={"Content-Type": "application/json"})[0], 415)

    def test_duplicate_length_origin_and_transfer_encoding_are_rejected(self):
        for extra_header, expected in (("Content-Length", 400), ("Origin", 403), ("Host", 403),
                                       ("Transfer-Encoding", 400)):
            connection = http.client.HTTPConnection(*self.server.server_address, timeout=3)
            connection.putrequest("POST", "/_lab/login", skip_host=True)
            for key, value in (("Host", "lab.test:18020"), ("X-Forwarded-Proto", "http"),
                               ("Origin", "http://lab.test:18020"),
                               ("Content-Type", "application/x-www-form-urlencoded"),
                               ("Content-Length", "0"), (extra_header, "0")):
                connection.putheader(key, value)
            connection.endheaders()
            response = connection.getresponse()
            self.assertEqual(response.status, expected, extra_header)
            response.read()
            connection.close()

    def test_unknown_route_does_not_serve_files(self):
        for path in ("/", "/auth.py", "/../auth.json", "/_lab/unknown"):
            status, headers, _ = self.request("GET", path)
            self.assertEqual(status, 404)
            self.assertEqual(headers["Cache-Control"], "no-store")

    def test_unsupported_method_has_no_cache(self):
        status, headers, _ = self.request("PUT", "/_lab/login")
        self.assertEqual(status, 501)
        self.assertEqual(headers["Cache-Control"], "no-store")


class ConfigurationTests(unittest.TestCase):
    def test_mandatory_file_and_strict_secret_format(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test-auth.json"
            with self.assertRaises(FileNotFoundError):
                AuthConfig.load(path)
            data = {"username": "viewer", "password_salt": secrets.token_hex(16),
                    "password_hash": secrets.token_hex(32), "session_secret": secrets.token_hex(32)}
            path.write_text(json.dumps(data), encoding="utf-8")
            self.assertEqual(AuthConfig.load(path).username, "viewer")
            for field, value in (("session_secret", "a" * 63), ("session_secret", "g" * 64),
                                 ("password_salt", "aa"), ("password_hash", "aa"),
                                 ("username", ""), ("username", "x\n")):
                with self.subTest(field=field, length=len(value)):
                    invalid = dict(data, **{field: value})
                    path.write_text(json.dumps(invalid), encoding="utf-8")
                    with self.assertRaises(ValueError):
                        AuthConfig.load(path)


if __name__ == "__main__":
    unittest.main()
