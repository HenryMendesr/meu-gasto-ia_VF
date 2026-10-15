import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api import index  # noqa: E402

fastapi_app = index.fastapi_app


class WebSecurityTests(unittest.TestCase):
    def setUp(self):
        index._AUTH_ATTEMPTS.clear()
        self.client = TestClient(fastapi_app)

    def test_cross_site_write_is_rejected(self):
        response = self.client.post(
            "/login",
            data={"password": "senha-forte-de-teste"},
            headers={"Origin": "https://site-malicioso.example"},
            follow_redirects=False,
        )
        self.assertEqual(403, response.status_code)

    def test_same_origin_login_uses_protected_cookie(self):
        with patch("api.index.auth.verify_password", return_value=True), patch.dict(
            "os.environ", {"SESSION_SECRET": "segredo-de-teste-com-mais-de-trinta-e-dois-caracteres"}
        ):
            response = self.client.post(
                "/login",
                data={"password": "senha-forte-de-teste", "remember": "1"},
                headers={"Origin": "http://testserver"},
                follow_redirects=False,
            )
        cookie = response.headers["set-cookie"]
        self.assertEqual(303, response.status_code)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("Secure", cookie)
        self.assertIn("SameSite=strict", cookie)
        self.assertIn("Max-Age=2592000", cookie)

    def test_vercel_public_host_is_accepted(self):
        with patch("api.index.auth.verify_password", return_value=True), patch.dict(
            "os.environ", {"SESSION_SECRET": "segredo-de-teste-com-mais-de-trinta-e-dois-caracteres"}
        ):
            response = self.client.post(
                "/login",
                data={"password": "senha-forte-de-teste"},
                headers={
                    "Host": "funcao-interna.vercel.app",
                    "X-Forwarded-Host": "minha-carteira.example",
                    "Origin": "https://minha-carteira.example",
                },
                follow_redirects=False,
            )
        self.assertEqual(303, response.status_code)

    def test_oversized_write_is_rejected_before_parsing(self):
        response = self.client.post(
            "/api/statements/preview",
            content=b"x",
            headers={"Content-Length": "9000001", "Origin": "http://testserver"},
        )
        self.assertEqual(413, response.status_code)

    def test_repeated_login_attempts_are_limited(self):
        with patch("api.index.auth.verify_password", return_value=False):
            for _ in range(8):
                response = self.client.post("/login", data={"password": "incorreta"})
                self.assertIn("Senha incorreta", response.text)
            blocked = self.client.post("/login", data={"password": "incorreta"})
        self.assertIn("Muitas tentativas", blocked.text)


if __name__ == "__main__":
    unittest.main()
