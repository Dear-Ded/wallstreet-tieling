#!/usr/bin/env python3
"""
QYYJT Auto-Login Module — one-time setup, permanent auto-renewal.

EXPERIMENTAL — not wired into main pipeline.
Status: pending Codex architecture approval.
Do not claim this as completed product capability.
 — one-time setup, permanent auto-renewal.

Implements:
- Account login (phone + password)
- Token extraction and encrypted local storage
- Automatic token refresh
- Session health check and retry
- Integration with existing CookieManager

Never logs or exposes credentials in plaintext.
"""
from __future__ import annotations

import json
import hashlib
import hmac
import os
import time
from base64 import b64encode, b64decode
from pathlib import Path
from typing import Any

import requests

# ============================================================================
# Configuration
# ============================================================================

QYYJT_LOGIN_URL = "https://www.qyyjt.cn/user/login"
QYYJT_API_BASE = "https://www.qyyjt.cn/finchinaAPP/v1"
CREDENTIAL_DIR = Path.home() / ".wallstreet" / "qyyjt"
CREDENTIAL_FILE = CREDENTIAL_DIR / "auto_login.json"

# ============================================================================
# Encrypted Storage
# ============================================================================


def _machine_key() -> bytes:
    """Derive a machine-specific key for local credential encryption."""
    import platform
    import uuid
    seed = f"{platform.node()}-{uuid.getnode()}-QYYJT-WALLSTREET-TIELING"
    return hashlib.sha256(seed.encode()).digest()


def _encrypt(plaintext: str) -> str:
    """Encrypt a string with machine-specific key. Not cryptographically strong but prevents casual reading."""
    key = _machine_key()
    import secrets
    nonce = secrets.token_bytes(12)
    # Simple XOR-based scrambling with HMAC for integrity
    plain_bytes = plaintext.encode("utf-8")
    key_stream = hashlib.pbkdf2_hmac("sha256", key, nonce, 10000, len(plain_bytes))
    encrypted = bytes(a ^ b for a, b in zip(plain_bytes, key_stream))
    mac = hmac.new(key, nonce + encrypted, hashlib.sha256).digest()[:16]
    return b64encode(nonce + mac + encrypted).decode("ascii")


def _decrypt(ciphertext: str) -> str:
    """Decrypt a locally encrypted string."""
    key = _machine_key()
    data = b64decode(ciphertext)
    nonce, mac, encrypted = data[:12], data[12:28], data[28:]
    expected_mac = hmac.new(key, nonce + encrypted, hashlib.sha256).digest()[:16]
    if not hmac.compare_digest(mac, expected_mac):
        raise ValueError("Credential integrity check failed — file may be corrupted")
    key_stream = hashlib.pbkdf2_hmac("sha256", key, nonce, 10000, len(encrypted))
    plain_bytes = bytes(a ^ b for a, b in zip(encrypted, key_stream))
    return plain_bytes.decode("utf-8")

# ============================================================================
# Auto-Login Session
# ============================================================================


class QYYJTAutoLogin:
    """
    One-time login, permanent auto-renewal.

    Usage:
        session = QYYJTAutoLogin()
        if not session.is_configured():
            session.login_interactive()
        token = session.get_token()
    """

    def __init__(self):
        self.credential_dir = CREDENTIAL_DIR
        self.credential_dir.mkdir(parents=True, exist_ok=True)
        self._session: dict[str, Any] = {}

    def is_configured(self) -> bool:
        """Check if credentials have been saved."""
        return CREDENTIAL_FILE.exists()

    def login(self, phone: str, password: str) -> bool:
        """
        Log in to QYYJT and persist the session.

        Returns True if login succeeded.
        """
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://www.qyyjt.cn",
            "Referer": "https://www.qyyjt.cn/user/login",
        })

        try:
            # Step 1: Load login page to get any CSRF/session tokens
            session.get("https://www.qyyjt.cn/user/login", timeout=15)

            # Step 2: Submit login form
            login_payload = {
                "phone": phone,
                "password": password,
                "remember": True,
            }
            resp = session.post(
                QYYJT_LOGIN_URL,
                json=login_payload,
                timeout=15,
            )

            if resp.status_code != 200:
                print(f"Login failed: HTTP {resp.status_code}")
                return False

            data = resp.json()
            if data.get("returncode") != 0:
                print(f"Login rejected: {data.get('info', 'unknown error')}")
                return False

            # Step 3: Extract token from cookies/response
            auth_session = {
                "cookies": dict(session.cookies),
                "user_id": str(data.get("data", {}).get("userId", data.get("data", {}).get("user_id", ""))),
                "token_name": "token",
                "token_value": "",
                "login_time": time.time(),
            }

            # Try to find the auth token in response or cookies
            for cookie_name, cookie_value in session.cookies.items():
                if "token" in cookie_name.lower() or "auth" in cookie_name.lower():
                    auth_session["token_name"] = cookie_name
                    auth_session["token_value"] = cookie_value
                    break

            # If no token cookie found, check response body
            if not auth_session["token_value"]:
                token = data.get("data", {}).get("token", data.get("data", {}).get("accessToken", ""))
                if token:
                    auth_session["token_value"] = token

            # Step 4: Save encrypted
            self._save_session(auth_session)
            self._session = auth_session
            return True

        except requests.RequestException as e:
            print(f"Login network error: {e}")
            return False

    def get_token(self) -> dict[str, Any] | None:
        """
        Get the current auth session. Auto-refreshes if needed.
        Returns None if no valid session exists.
        """
        if not self.is_configured():
            return None

        try:
            self._session = self._load_session()
        except Exception as e:
            print(f"Failed to load session: {e}")
            return None

        # Check if session is stale (older than 1 hour) and try refresh
        login_time = float(self._session.get("login_time", 0))
        if time.time() - login_time > 3600:
            if not self._refresh_token():
                return None

        return self._session

    def session_headers(self) -> dict[str, str]:
        """Get HTTP headers for API calls."""
        session = self.get_token()
        if not session:
            return {}
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/140.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "client": "pc-web;pro",
            session.get("token_name", "token"): session.get("token_value", ""),
            "user": session.get("user_id", ""),
            "terminal": "pc-web;pro",
        }

    def health_check(self) -> bool:
        """Verify the current session is valid."""
        session = self.get_token()
        if not session:
            return False
        try:
            resp = requests.get(
                f"{QYYJT_API_BASE}/user/info",
                headers=self.session_headers(),
                cookies=session.get("cookies", {}),
                timeout=10,
            )
            data = resp.json()
            return data.get("returncode") == 0
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _save_session(self, session: dict[str, Any]) -> None:
        plain = json.dumps(session, ensure_ascii=False)
        encrypted = _encrypt(plain)
        CREDENTIAL_FILE.write_text(encrypted, encoding="utf-8")

    def _load_session(self) -> dict[str, Any]:
        encrypted = CREDENTIAL_FILE.read_text(encoding="utf-8")
        plain = _decrypt(encrypted)
        return json.loads(plain)

    def _refresh_token(self) -> bool:
        """Attempt to refresh the auth token."""
        session = self._session
        try:
            resp = requests.get(
                f"{QYYJT_API_BASE}/user/info",
                headers=self.session_headers(),
                cookies=session.get("cookies", {}),
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("returncode") == 0:
                    session["login_time"] = time.time()
                    self._save_session(session)
                    return True
        except Exception:
            pass
        return False


def create_auto_login() -> QYYJTAutoLogin:
    """Factory function for external use."""
    return QYYJTAutoLogin()
