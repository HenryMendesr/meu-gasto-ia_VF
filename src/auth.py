"""Autenticação local com senha derivada e sessões assinadas."""

from __future__ import annotations

from base64 import urlsafe_b64decode, urlsafe_b64encode
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]
AUTH_FILE = ROOT / "data/auth.json"
COOKIE_NAME = "meu_gasto_session"
SESSION_SECONDS = 30 * 24 * 60 * 60
PBKDF2_ITERATIONS = 600_000


def configured() -> bool:
    return bool(os.environ.get("APP_PASSWORD") and os.environ.get("SESSION_SECRET")) or AUTH_FILE.is_file()


def _encode(raw: bytes) -> str:
    return urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode(value: str) -> bytes:
    return urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _read() -> dict:
    try:
        data = json.loads(AUTH_FILE.read_text(encoding="utf-8"))
        if not all(data.get(key) for key in ("salt", "password_hash", "session_secret")):
            raise ValueError
        return data
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError("Configuração de acesso inválida") from exc


def setup(password: str, confirmation: str) -> None:
    if configured():
        raise ValueError("O acesso já foi configurado")
    if password != confirmation:
        raise ValueError("As senhas não coincidem")
    if len(password) < 10 or len(password) > 200:
        raise ValueError("Use uma senha com pelo menos 10 caracteres")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    data = {
        "version": 1,
        "salt": _encode(salt),
        "password_hash": _encode(digest),
        "session_secret": _encode(secrets.token_bytes(32)),
    }
    AUTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(prefix="auth-", suffix=".json", dir=AUTH_FILE.parent)
    try:
        with open(handle, "w", encoding="utf-8") as stream:
            json.dump(data, stream, indent=2)
            stream.write("\n")
        try:
            os.chmod(name, 0o600)
        except OSError:
            pass
        Path(name).replace(AUTH_FILE)
    finally:
        Path(name).unlink(missing_ok=True)


def verify_password(password: str) -> bool:
    configured_password = os.environ.get("APP_PASSWORD")
    if configured_password:
        return hmac.compare_digest(password, configured_password)
    if not configured() or len(password) > 200:
        return False
    data = _read()
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), _decode(data["salt"]), PBKDF2_ITERATIONS
    )
    return hmac.compare_digest(_encode(digest), data["password_hash"])


def create_session(now: int | None = None) -> str:
    secret = os.environ.get("SESSION_SECRET")
    data = _read() if not secret else None
    payload = json.dumps(
        {"exp": (now or int(time.time())) + SESSION_SECONDS, "nonce": secrets.token_hex(8)},
        separators=(",", ":"),
    ).encode("utf-8")
    encoded = _encode(payload)
    key = secret.encode("utf-8") if secret else _decode(data["session_secret"])
    signature = hmac.new(key, encoded.encode("ascii"), hashlib.sha256).digest()
    return f"{encoded}.{_encode(signature)}"


def verify_session(token: str | None, now: int | None = None) -> bool:
    if not token or not configured():
        return False
    try:
        encoded, supplied = token.split(".", 1)
        secret = os.environ.get("SESSION_SECRET")
        key = secret.encode("utf-8") if secret else _decode(_read()["session_secret"])
        expected = hmac.new(key, encoded.encode("ascii"), hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _decode(supplied)):
            return False
        payload = json.loads(_decode(encoded))
        return int(payload["exp"]) >= (now or int(time.time()))
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return False
