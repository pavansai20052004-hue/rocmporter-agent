import base64
import hashlib
import hmac
import json
import os
import time
import unittest
from unittest import mock

from app import auth_service


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def make_hs256_token(secret: str, claims: dict) -> str:
    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _b64url(json.dumps(claims).encode())
    signing_input = f"{header}.{payload}".encode()
    sig = _b64url(hmac.new(secret.encode(), signing_input, hashlib.sha256).digest())
    return f"{header}.{payload}.{sig}"


def make_es256_style_token(claims: dict) -> str:
    """Structurally valid JWT with an ES256 header and a junk signature."""
    header = _b64url(json.dumps({"alg": "ES256", "typ": "JWT", "kid": "test"}).encode())
    payload = _b64url(json.dumps(claims).encode())
    return f"{header}.{payload}.{_b64url(b'not-a-real-signature')}"


class AuthServiceTests(unittest.TestCase):
    def setUp(self):
        auth_service._TOKEN_CACHE.clear()

    def test_no_authorization_returns_none(self):
        self.assertIsNone(auth_service.verify_token(None))
        self.assertIsNone(auth_service.verify_token("Basic abc"))

    def test_hs256_valid_token_verifies_locally(self):
        claims = {"sub": "user-1", "exp": time.time() + 3600}
        token = make_hs256_token("topsecret", claims)
        with mock.patch.dict(os.environ, {"SUPABASE_JWT_SECRET": "topsecret"}):
            result = auth_service.verify_token(f"Bearer {token}")
        self.assertEqual(result["sub"], "user-1")

    def test_hs256_expired_token_rejected(self):
        token = make_hs256_token("topsecret", {"sub": "user-1", "exp": time.time() - 10})
        env = {"SUPABASE_JWT_SECRET": "topsecret", "SUPABASE_URL": "", "SUPABASE_SERVICE_ROLE_KEY": ""}
        with mock.patch.dict(os.environ, env):
            self.assertIsNone(auth_service.verify_token(f"Bearer {token}"))

    def test_es256_token_falls_through_to_auth_api(self):
        token = make_es256_style_token({"sub": "user-2", "exp": time.time() + 3600})
        env = {
            "SUPABASE_JWT_SECRET": "topsecret",
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_SERVICE_ROLE_KEY": "service-key",
        }
        with mock.patch.dict(os.environ, env):
            with mock.patch.object(auth_service, "_verify_via_auth_api", return_value={"sub": "user-2"}) as remote:
                result = auth_service.verify_token(f"Bearer {token}")
        self.assertEqual(result, {"sub": "user-2"})
        remote.assert_called_once()

    def test_auth_api_result_is_cached(self):
        token = make_es256_style_token({"sub": "user-3", "exp": time.time() + 3600})
        env = {"SUPABASE_URL": "https://example.supabase.co", "SUPABASE_SERVICE_ROLE_KEY": "service-key"}

        fake_user = json.dumps({"id": "user-3", "email": "u3@example.com", "role": "authenticated"}).encode()

        class FakeResponse:
            def read(self):
                return fake_user

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        with mock.patch.dict(os.environ, env):
            with mock.patch.object(auth_service.urllib.request, "urlopen", return_value=FakeResponse()) as opened:
                first = auth_service._verify_via_auth_api(token)
                second = auth_service._verify_via_auth_api(token)
        self.assertEqual(first["sub"], "user-3")
        self.assertEqual(second["sub"], "user-3")
        opened.assert_called_once()  # second hit came from cache

    def test_enforcement_enabled_by_service_pair(self):
        env = {"SUPABASE_JWT_SECRET": "", "SUPABASE_URL": "https://x.supabase.co", "SUPABASE_SERVICE_ROLE_KEY": "k"}
        with mock.patch.dict(os.environ, env):
            self.assertTrue(auth_service.enforcement_enabled())
        with mock.patch.dict(os.environ, {"SUPABASE_JWT_SECRET": "", "SUPABASE_URL": "", "SUPABASE_SERVICE_ROLE_KEY": ""}):
            self.assertFalse(auth_service.enforcement_enabled())


if __name__ == "__main__":
    unittest.main()
