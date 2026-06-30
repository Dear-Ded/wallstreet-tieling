#!/usr/bin/env python3
"""Config-driven authentication handlers for multi-datasource connectors."""
from __future__ import annotations

import base64
import hashlib
import hmac
import time
from dataclasses import dataclass, field
from typing import Any, Protocol


class AuthChallengeRequired(Exception):
    """Raised when a source presents a human-verification challenge."""

    def __init__(
        self,
        challenge_type: str,
        *,
        source: str = "",
        details: dict[str, Any] | None = None,
    ):
        self.challenge_type = challenge_type
        self.source = source
        self.details = details or {}
        super().__init__(f"authentication challenge required: {challenge_type}")


@dataclass
class AuthRequestContext:
    """Mutable request context passed through auth handlers."""

    source_name: str
    method: str
    url: str
    params: dict[str, Any] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    body: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AuthResponseContext:
    """Response summary used by handlers to detect refresh/challenge states."""

    status: int
    headers: dict[str, str] = field(default_factory=dict)
    content_type: str = ""
    body_preview: str = ""


@dataclass
class ChallengeDescriptor:
    """Normalized description of an access challenge detected by a source."""

    challenge_type: str
    source: str
    status: int
    content_type: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    body_hint: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.challenge_type,
            "source": self.source,
            "status": self.status,
            "content_type": self.content_type,
            "headers": self.headers,
            "body_hint": self.body_hint,
        }


@dataclass
class ChallengeHandoff:
    """Provider result returned to product/UI layers for compliant handling."""

    provider: str
    status: str
    next_action: str
    message: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "status": self.status,
            "next_action": self.next_action,
            "message": self.message,
            "metadata": self.metadata,
        }


class AuthHandler(Protocol):
    """Authentication plugin contract."""

    async def prepare(self, context: AuthRequestContext) -> AuthRequestContext:
        ...

    async def handle_response(self, context: AuthRequestContext, response: AuthResponseContext) -> None:
        ...


class ChallengeProvider(Protocol):
    """Human-verification provider slot contract."""

    name: str

    async def handle_challenge(
        self,
        descriptor: ChallengeDescriptor,
        context: AuthRequestContext,
    ) -> ChallengeHandoff:
        ...


class NoAuthHandler:
    async def prepare(self, context: AuthRequestContext) -> AuthRequestContext:
        return context

    async def handle_response(self, context: AuthRequestContext, response: AuthResponseContext) -> None:
        return None


class BasicAuthHandler(NoAuthHandler):
    def __init__(self, username: str = "", password: str = ""):
        self.username = username
        self.password = password

    async def prepare(self, context: AuthRequestContext) -> AuthRequestContext:
        raw = f"{self.username}:{self.password}".encode("utf-8")
        context.headers["Authorization"] = "Basic " + base64.b64encode(raw).decode("ascii")
        return context


class ApiKeyAuthHandler(NoAuthHandler):
    def __init__(self, api_key: str = "", *, header_name: str = "X-API-Key", param_name: str = ""):
        self.api_key = api_key
        self.header_name = header_name
        self.param_name = param_name

    async def prepare(self, context: AuthRequestContext) -> AuthRequestContext:
        if self.param_name:
            context.params[self.param_name] = self.api_key
        else:
            context.headers[self.header_name] = self.api_key
        return context


class BearerTokenAuthHandler(NoAuthHandler):
    def __init__(self, token: str = ""):
        self.token = token

    async def prepare(self, context: AuthRequestContext) -> AuthRequestContext:
        if self.token:
            context.headers["Authorization"] = f"Bearer {self.token}"
        return context


class SessionAuthHandler(NoAuthHandler):
    def __init__(self, cookies: dict[str, str] | None = None, headers: dict[str, str] | None = None):
        self.cookies = cookies or {}
        self.headers = headers or {}

    async def prepare(self, context: AuthRequestContext) -> AuthRequestContext:
        context.headers.update(self.headers)
        if self.cookies:
            context.headers["Cookie"] = "; ".join(f"{key}={value}" for key, value in self.cookies.items())
        return context


class HmacSignatureAuthHandler(NoAuthHandler):
    def __init__(
        self,
        secret: str = "",
        *,
        header_name: str = "X-Signature",
        timestamp_header: str = "X-Timestamp",
        algorithm: str = "sha256",
    ):
        self.secret = secret
        self.header_name = header_name
        self.timestamp_header = timestamp_header
        self.algorithm = algorithm

    async def prepare(self, context: AuthRequestContext) -> AuthRequestContext:
        timestamp = str(int(time.time()))
        canonical = _canonical_payload(context, timestamp)
        digestmod = getattr(hashlib, self.algorithm, hashlib.sha256)
        signature = hmac.new(
            self.secret.encode("utf-8"),
            canonical.encode("utf-8"),
            digestmod,
        ).hexdigest()
        context.headers[self.timestamp_header] = timestamp
        context.headers[self.header_name] = signature
        return context


class RefreshableBearerAuthHandler(BearerTokenAuthHandler):
    """Bearer handler with refresh metadata; token exchange is provider-owned."""

    def __init__(self, token: str = "", *, refresh_url: str = "", expires_at: float = 0):
        super().__init__(token)
        self.refresh_url = refresh_url
        self.expires_at = expires_at
        self.refresh_required = False

    async def prepare(self, context: AuthRequestContext) -> AuthRequestContext:
        if self.expires_at and time.time() >= self.expires_at:
            self.refresh_required = True
            context.metadata["auth_refresh_required"] = True
        return await super().prepare(context)

    async def handle_response(self, context: AuthRequestContext, response: AuthResponseContext) -> None:
        if response.status in {401, 419}:
            self.refresh_required = True
            context.metadata["auth_refresh_required"] = True


class DisabledChallengeProvider:
    """Default-safe provider: report the challenge without automating it."""

    name = "disabled"

    async def handle_challenge(
        self,
        descriptor: ChallengeDescriptor,
        context: AuthRequestContext,
    ) -> ChallengeHandoff:
        return ChallengeHandoff(
            provider=self.name,
            status="provider_not_configured",
            next_action="configure_provider_or_user_authorization",
            message="requires configured compliant challenge provider or user authorization flow",
            metadata={
                "default_safe": True,
                "automation_enabled": False,
                "descriptor": descriptor.to_dict(),
            },
        )


class BrowserHandoffChallengeProvider:
    """Provider slot for UI/browser-assisted user authorization flows."""

    name = "browser_handoff"

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}

    async def handle_challenge(
        self,
        descriptor: ChallengeDescriptor,
        context: AuthRequestContext,
    ) -> ChallengeHandoff:
        return ChallengeHandoff(
            provider=self.name,
            status="handoff_required",
            next_action="open_authorized_browser_session",
            message="open a user-authorized browser session or enterprise provider to complete the challenge",
            metadata={
                "handoff_url": self.config.get("handoff_url", context.url),
                "callback_url": self.config.get("callback_url", ""),
                "session_scope": self.config.get("session_scope", "source"),
                "automation_enabled": False,
                "descriptor": descriptor.to_dict(),
            },
        )


class ChallengeProviderRegistry:
    """Factory registry for compliant challenge handoff providers."""

    def __init__(self):
        self._factories = {
            "disabled": lambda config: DisabledChallengeProvider(),
            "browser_handoff": lambda config: BrowserHandoffChallengeProvider(dict(config or {})),
        }

    def build(self, provider_name: str = "disabled", config: dict[str, Any] | None = None) -> ChallengeProvider:
        provider = str(provider_name or "disabled").lower()
        factory = self._factories.get(provider, self._factories["disabled"])
        return factory(config or {})

    def register(self, provider_name: str, factory: Any) -> None:
        self._factories[str(provider_name).lower()] = factory

    def supported_providers(self) -> list[str]:
        return sorted(self._factories)


class ChallengeAwareAuthHandler(NoAuthHandler):
    """Detects human-verification challenges without bypassing them."""

    CHALLENGE_HINTS = (
        "captcha",
        "recaptcha",
        "hcaptcha",
        "verify you are human",
        "human verification",
        "人机验证",
        "验证码",
        "滑块",
    )

    def __init__(self, provider: ChallengeProvider | None = None):
        self.provider = provider or DisabledChallengeProvider()

    async def handle_response(self, context: AuthRequestContext, response: AuthResponseContext) -> None:
        haystack = " ".join(
            [
                str(response.status),
                response.content_type,
                " ".join(f"{key}:{value}" for key, value in response.headers.items()),
                response.body_preview,
            ]
        ).lower()
        if response.status in {403, 429} and any(hint in haystack for hint in self.CHALLENGE_HINTS):
            descriptor = ChallengeDescriptor(
                challenge_type="human_verification",
                source=context.source_name,
                status=response.status,
                content_type=response.content_type,
                headers=_safe_challenge_headers(response.headers),
                body_hint=response.body_preview[:240],
            )
            handoff = await self.provider.handle_challenge(descriptor, context)
            raise AuthChallengeRequired(
                descriptor.challenge_type,
                source=context.source_name,
                details={
                    "status": response.status,
                    "content_type": response.content_type,
                    "handling": handoff.message,
                    "provider": handoff.to_dict(),
                },
            )


class CompositeAuthHandler(NoAuthHandler):
    def __init__(self, handlers: list[AuthHandler]):
        self.handlers = handlers

    async def prepare(self, context: AuthRequestContext) -> AuthRequestContext:
        for handler in self.handlers:
            context = await handler.prepare(context)
        return context

    async def handle_response(self, context: AuthRequestContext, response: AuthResponseContext) -> None:
        for handler in self.handlers:
            await handler.handle_response(context, response)


class AuthHandlerRegistry:
    """Factory registry for config-driven authentication handlers."""

    def __init__(self):
        self._factories = {
            "none": self._none,
            "basic": self._basic,
            "api_key": self._api_key,
            "bearer": self._bearer,
            "session": self._session,
            "request_signature": self._signature,
            "hmac": self._signature,
            "oauth2": self._refreshable_bearer,
            "challenge_aware": self._challenge_aware,
        }

    def build(self, config: Any) -> AuthHandler:
        auth_type = str(getattr(config, "type", "none") or "none").lower()
        factory = self._factories.get(auth_type)
        if factory is None:
            return NoAuthHandler()
        return factory(config)

    def register(self, auth_type: str, factory: Any) -> None:
        self._factories[str(auth_type).lower()] = factory

    def supported_types(self) -> list[str]:
        return sorted(self._factories)

    @staticmethod
    def _none(config: Any) -> AuthHandler:
        return NoAuthHandler()

    @staticmethod
    def _basic(config: Any) -> AuthHandler:
        return BasicAuthHandler(
            username=str(getattr(config, "username", "") or ""),
            password=str(getattr(config, "password", "") or ""),
        )

    @staticmethod
    def _api_key(config: Any) -> AuthHandler:
        return ApiKeyAuthHandler(
            api_key=str(getattr(config, "api_key", "") or ""),
            header_name=str(getattr(config, "header_name", "") or "X-API-Key"),
            param_name=str(getattr(config, "param_name", "") or ""),
        )

    @staticmethod
    def _bearer(config: Any) -> AuthHandler:
        token = str(getattr(config, "token", "") or getattr(config, "api_key", "") or "")
        return BearerTokenAuthHandler(token=token)

    @staticmethod
    def _session(config: Any) -> AuthHandler:
        return SessionAuthHandler(
            cookies=dict(getattr(config, "cookies", {}) or {}),
            headers=dict(getattr(config, "session_headers", {}) or {}),
        )

    @staticmethod
    def _signature(config: Any) -> AuthHandler:
        secret = str(getattr(config, "signature_secret", "") or getattr(config, "api_key", "") or "")
        return HmacSignatureAuthHandler(
            secret=secret,
            header_name=str(getattr(config, "signature_header", "") or "X-Signature"),
            timestamp_header=str(getattr(config, "timestamp_header", "") or "X-Timestamp"),
            algorithm=str(getattr(config, "signature_algorithm", "") or "sha256"),
        )

    @staticmethod
    def _refreshable_bearer(config: Any) -> AuthHandler:
        token = str(getattr(config, "token", "") or getattr(config, "api_key", "") or "")
        return RefreshableBearerAuthHandler(
            token=token,
            refresh_url=str(getattr(config, "token_url", "") or ""),
            expires_at=float(getattr(config, "expires_at", 0) or 0),
        )

    @staticmethod
    def _challenge_aware(config: Any) -> AuthHandler:
        provider = ChallengeProviderRegistry().build(
            str(getattr(config, "challenge_provider", "") or "disabled"),
            dict(getattr(config, "challenge_provider_config", {}) or {}),
        )
        return CompositeAuthHandler(
            [
                BearerTokenAuthHandler(str(getattr(config, "token", "") or getattr(config, "api_key", "") or "")),
                SessionAuthHandler(cookies=dict(getattr(config, "cookies", {}) or {})),
                ChallengeAwareAuthHandler(provider=provider),
            ]
        )


def build_auth_handler(config: Any) -> AuthHandler:
    return AuthHandlerRegistry().build(config)


def _canonical_payload(context: AuthRequestContext, timestamp: str) -> str:
    params = "&".join(f"{key}={context.params[key]}" for key in sorted(context.params))
    return "\n".join([context.method.upper(), context.url, params, timestamp])


def _safe_challenge_headers(headers: dict[str, str]) -> dict[str, str]:
    allowed_prefixes = ("x-challenge", "x-captcha", "cf-", "content-type")
    safe: dict[str, str] = {}
    for key, value in headers.items():
        lowered = str(key).lower()
        if lowered == "content-type" or lowered.startswith(allowed_prefixes):
            safe[str(key)] = str(value)[:240]
    return safe
