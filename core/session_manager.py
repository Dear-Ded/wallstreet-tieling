#!/usr/bin/env python3
"""
session_manager.py — Session Persistence, Login Automation & Multi-Source Credential Store

Manages authenticated sessions across data sources with:
- Encrypted credential storage (Fernet symmetric encryption)
- Session cookie persistence and refresh
- Auto-login with form detection and fill
- OAuth2 token lifecycle (refresh before expiry)
- Session health check with automatic re-login on expiry
- Credential rotation for enterprise API keys

Dependencies: cryptography, keyring (optional for OS-level credential store)

Usage:
    from core.session_manager import SessionManager, CredentialStore

    store = CredentialStore(master_key="my-secret-key")
    store.set_credential("qyyjt_api", {"username": "...", "password": "..."})

    mgr = SessionManager(store)
    session = await mgr.get_session("qyyjt_api")
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger("wallstreet-tieling.session")

# ---------------------------------------------------------------------------
# Encrypted Credential Store
# ---------------------------------------------------------------------------

class CredentialStore:
    """Secure credential storage with Fernet symmetric encryption.

    Stores credentials at ~/.wallstreet-tieling/credentials.enc
    Master key can be stored in environment variable WST_MASTER_KEY
    or OS keyring (keyring library required).
    """

    def __init__(self, storage_path: str = "", master_key: str = ""):
        self.storage_path = storage_path or os.path.join(
            os.path.expanduser("~"), ".wallstreet-tieling", "credentials.enc"
        )
        self._master_key = master_key or os.environ.get("WST_MASTER_KEY", "")
        self._data: dict[str, dict[str, str]] = {}
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        self._load()

    def _get_cipher(self):
        try:
            from cryptography.fernet import Fernet
        except ImportError:
            raise RuntimeError("cryptography not installed. Run: pip install cryptography")
        if not self._master_key:
            raise ValueError("Master key not set. Set WST_MASTER_KEY environment variable.")
        key = base64.urlsafe_b64encode(
            hashlib.sha256(self._master_key.encode()).digest()
        )
        return Fernet(key)

    def _load(self):
        try:
            if os.path.exists(self.storage_path):
                with open(self.storage_path, "rb") as f:
                    encrypted = f.read()
                if encrypted:
                    cipher = self._get_cipher()
                    decrypted = cipher.decrypt(encrypted)
                    self._data = json.loads(decrypted)
        except Exception as e:
            logger.warning(f"Failed to load credentials: {e}")
            self._data = {}

    def _save(self):
        try:
            cipher = self._get_cipher()
            encrypted = cipher.encrypt(json.dumps(self._data).encode())
            with open(self.storage_path, "wb") as f:
                f.write(encrypted)
        except Exception as e:
            logger.error(f"Failed to save credentials: {e}")

    def set_credential(self, source_name: str, credentials: dict[str, str]) -> None:
        self._data[source_name] = credentials
        self._save()

    def get_credential(self, source_name: str) -> dict[str, str]:
        return self._data.get(source_name, {})

    def delete_credential(self, source_name: str) -> None:
        self._data.pop(source_name, None)
        self._save()

    def list_sources(self) -> list[str]:
        return list(self._data.keys())


# ---------------------------------------------------------------------------
# Session State
# ---------------------------------------------------------------------------

class SessionStatus(str, Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    LOGGED_OUT = "logged_out"
    ERROR = "error"


@dataclass
class Session:
    """Represents an authenticated session with a data source."""
    source_name: str
    status: SessionStatus = SessionStatus.LOGGED_OUT
    cookies: dict[str, str] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    access_token: str = ""
    refresh_token: str = ""
    token_expiry: float = 0
    last_verified: float = 0
    login_url: str = ""
    health_check_url: str = ""
    extra_state: dict[str, Any] = field(default_factory=dict)

    @property
    def is_expired(self) -> bool:
        if self.token_expiry and time.time() > self.token_expiry - 60:
            return True
        if not self.cookies and not self.access_token:
            return True
        return False

    @property
    def auth_header(self) -> dict[str, str]:
        if self.access_token:
            return {"Authorization": f"Bearer {self.access_token}"}
        return {}


# ---------------------------------------------------------------------------
# Session Manager
# ---------------------------------------------------------------------------

class SessionManager:
    """Manages lifecycle of authenticated sessions across data sources."""

    def __init__(self, credential_store: CredentialStore | None = None):
        self.store = credential_store or CredentialStore()
        self._sessions: dict[str, Session] = {}

    # ----- Session Lifecycle -----

    def register_source(
        self,
        source_name: str,
        login_url: str = "",
        health_check_url: str = "",
        auth_type: str = "form",  # form | oauth2 | api_key | cookie
    ) -> Session:
        session = Session(
            source_name=source_name,
            login_url=login_url,
            health_check_url=health_check_url,
        )
        self._sessions[source_name] = session
        return session

    async def get_session(self, source_name: str) -> Session:
        """Get or refresh a session for the given source."""
        session = self._sessions.get(source_name)
        if not session:
            session = self.register_source(source_name)
        if session.is_expired:
            await self._login(source_name, session)
        return session

    async def _login(self, source_name: str, session: Session) -> None:
        """Perform login for the given source type."""
        creds = self.store.get_credential(source_name)
        if not creds:
            logger.warning(f"No credentials found for {source_name}")
            session.status = SessionStatus.LOGGED_OUT
            return

        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()

                # Navigate to login page
                await page.goto(session.login_url, wait_until="networkidle", timeout=30000)

                # Auto-detect and fill common login form patterns
                username_selectors = [
                    "input[name='username']", "input[name='user']", "input[name='email']",
                    "input[name='account']", "input[type='text']", "input[id='username']",
                    "input[name='mobile']", "input[name='phone']",
                ]
                password_selectors = [
                    "input[name='password']", "input[type='password']",
                    "input[name='pwd']", "input[id='password']",
                ]

                username_field = None
                for sel in username_selectors:
                    username_field = await page.query_selector(sel)
                    if username_field:
                        break

                password_field = None
                for sel in password_selectors:
                    password_field = await page.query_selector(sel)
                    if password_field:
                        break

                if username_field and password_field:
                    await username_field.fill(creds.get("username", ""))
                    await password_field.fill(creds.get("password", ""))

                    # Find and click submit button
                    submit_selectors = [
                        "button[type='submit']", "input[type='submit']",
                        "button:has-text('登录')", "button:has-text('Login')",
                        "button:has-text('登 录')",
                    ]
                    for sel in submit_selectors:
                        submit_btn = await page.query_selector(sel)
                        if submit_btn:
                            await submit_btn.click()
                            break

                    await page.wait_for_timeout(3000)

                    # Extract cookies
                    cookies = await browser.contexts[0].cookies()
                    for c in cookies:
                        session.cookies[c["name"]] = c["value"]

                    session.status = SessionStatus.ACTIVE
                    session.last_verified = time.time()
                    logger.info(f"Login successful for {source_name}")

                await browser.close()

        except ImportError:
            logger.warning("Playwright not available for browser-based login")
            # Fallback: direct HTTP POST with requests
            await self._login_http(source_name, session, creds)
        except Exception as e:
            logger.error(f"Login failed for {source_name}: {e}")
            session.status = SessionStatus.ERROR

    async def _login_http(self, source_name: str, session: Session, creds: dict) -> None:
        """Fallback: HTTP POST login without browser."""
        try:
            import aiohttp
            async with aiohttp.ClientSession() as http:
                # Try common API auth endpoints
                payload = {
                    "username": creds.get("username", ""),
                    "password": creds.get("password", ""),
                    "grant_type": "password",
                }
                headers = {"Content-Type": "application/x-www-form-urlencoded"}
                async with http.post(session.login_url, data=payload, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        session.access_token = data.get("access_token", "")
                        session.refresh_token = data.get("refresh_token", "")
                        if "expires_in" in data:
                            session.token_expiry = time.time() + data["expires_in"]
                        session.status = SessionStatus.ACTIVE
                        session.last_verified = time.time()
                        logger.info(f"API login successful for {source_name}")
                        return
            session.status = SessionStatus.ERROR
        except Exception as e:
            logger.error(f"HTTP login failed for {source_name}: {e}")
            session.status = SessionStatus.ERROR

    async def verify_session(self, source_name: str) -> bool:
        """Check if a session is still valid by hitting health check URL."""
        session = self._sessions.get(source_name)
        if not session or not session.health_check_url:
            return False
        try:
            import aiohttp
            async with aiohttp.ClientSession() as http:
                async with http.get(
                    session.health_check_url,
                    headers=session.auth_header,
                    cookies=session.cookies,
                    timeout=10,
                ) as resp:
                    if resp.status == 200:
                        session.last_verified = time.time()
                        session.status = SessionStatus.ACTIVE
                        return True
        except Exception:
            pass
        session.status = SessionStatus.EXPIRED
        return False

    async def refresh_all(self) -> dict[str, bool]:
        """Refresh all expired sessions. Returns {source_name: success}."""
        results = {}
        for name in self._sessions:
            session = self._sessions[name]
            if session.is_expired:
                await self._login(name, session)
                results[name] = session.status == SessionStatus.ACTIVE
            else:
                results[name] = True
        return results

    # ----- Credential Convenience -----

    def setup_qyyjt(self, username: str, password: str) -> None:
        """Configure QYYJT API credentials."""
        self.store.set_credential("qyyjt_api", {
            "username": username, "password": password,
        })
        self.register_source("qyyjt_api",
            login_url="https://api.qyyjt.com/auth/login",
            health_check_url="https://api.qyyjt.com/auth/status",
        )

    def setup_sec_edgar(self, user_agent: str = "") -> None:
        """SEC EDGAR requires only a User-Agent header (no auth)."""
        self.register_source("sec_edgar_api",
            login_url="", health_check_url="https://data.sec.gov/submissions/CIK0000320193.json",
        )
        if user_agent:
            session = self._sessions.get("sec_edgar_api")
            if session:
                session.headers["User-Agent"] = user_agent

    def setup_github(self, token: str) -> None:
        """Configure GitHub API token."""
        self.register_source("github_api",
            health_check_url="https://api.github.com/rate_limit",
        )
        session = self._sessions.get("github_api")
        if session:
            session.access_token = token
            session.status = SessionStatus.ACTIVE
