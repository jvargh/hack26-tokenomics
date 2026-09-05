"""Model routing.

The browser never calls a model. TokenOS decides whether an operation needs one
at all, and only then invokes the configured Foundry deployment. When no
deployment is configured the API says so instead of inventing model output.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass, field

from .config import settings
from .pricing import calculate_cost_usd


class ModelUnavailable(Exception):
    """Raised when a model route is required but no deployment is configured."""


@dataclass
class ModelResult:
    route: str
    deployment: str
    content: str
    input_tokens: int
    output_tokens: int
    duration_ms: int
    calculated_cost_usd: float
    price_configured: bool
    request_id: str | None = None
    model_version: str | None = None
    parsed: dict | None = field(default=None)
    # Normalized usage detail, present when the provider reports it. Never estimated:
    # zero when the response did not include the field.
    cached_input_tokens: int = 0
    reasoning_tokens: int = 0


class FoundryModelAdapter:
    """Thin adapter over the Foundry OpenAI v1 endpoint using deployment aliases."""

    def __init__(self) -> None:
        self._client = None
        self._credential = None

    def _ensure_client(self):
        if self._client is not None:
            return self._client
        try:
            from openai import AsyncOpenAI
        except ImportError as error:  # pragma: no cover - depends on optional extra
            raise ModelUnavailable(
                "The openai package is not installed. Install the foundry extra to enable model routes."
            ) from error

        base_url = settings.foundry_base_url
        if settings.foundry_auth_mode == "api_key":
            key = os.getenv("AZURE_INFERENCE_CREDENTIAL")
            if not key:
                raise ModelUnavailable("AZURE_INFERENCE_CREDENTIAL is not set.")
            self._client = AsyncOpenAI(base_url=base_url, api_key=key)
        else:
            try:
                # AsyncOpenAI awaits the key provider, so the async credential is
                # required. The sync provider returns a plain string and fails.
                from azure.identity.aio import (
                    DefaultAzureCredential,
                    get_bearer_token_provider,
                )
            except ImportError as error:  # pragma: no cover - optional extra
                raise ModelUnavailable(
                    "azure-identity is not installed. Install the foundry extra or use api_key auth."
                ) from error
            # Held on the adapter so the credential is not collected while the client
            # is still refreshing tokens.
            self._credential = DefaultAzureCredential()
            token_provider = get_bearer_token_provider(
                self._credential, settings.foundry_token_scope
            )
            self._client = AsyncOpenAI(base_url=base_url, api_key=token_provider)
        return self._client

    async def generate(
        self,
        *,
        route: str,
        system: str,
        input_text: str,
        deployment: str | None = None,
        max_output_tokens: int | None = None,
        json_response: bool = False,
        strict_usage: bool = False,
        single_attempt: bool = False,
    ) -> ModelResult:
        client = self._ensure_client()
        if single_attempt and hasattr(client, "with_options"):
            client = client.with_options(max_retries=0)
        target_deployment = deployment or settings.deployment_for(route)
        trimmed = input_text[: settings.max_model_input_characters]
        started = time.perf_counter()
        attempts = 1 if single_attempt else settings.model_max_retries + 1
        last_error: Exception | None = None

        for attempt in range(attempts):
            try:
                response = await asyncio.wait_for(
                    client.chat.completions.create(
                        model=target_deployment,
                        messages=[
                            {"role": "system", "content": system},
                            {"role": "user", "content": trimmed},
                        ],
                        temperature=0,
                        max_tokens=max_output_tokens or settings.max_output_tokens,
                        **({"response_format": {"type": "json_object"}} if json_response else {}),
                    ),
                    timeout=settings.model_timeout_seconds,
                )
                break
            except asyncio.TimeoutError as error:
                last_error = error
                if attempt == attempts - 1:
                    raise ModelUnavailable(
                        f"The {route} deployment timed out after {settings.model_timeout_seconds:.0f}s."
                    ) from error
            except Exception as error:  # noqa: BLE001 - surfaced to the run as a failure
                last_error = error
                if attempt == attempts - 1:
                    raise ModelUnavailable(f"The {route} deployment failed: {error}") from error
        else:  # pragma: no cover - loop always breaks or raises
            raise ModelUnavailable(str(last_error))

        duration_ms = int((time.perf_counter() - started) * 1000)
        usage = getattr(response, "usage", None)
        if strict_usage and (
            usage is None
            or getattr(usage, "prompt_tokens", None) is None
            or getattr(usage, "completion_tokens", None) is None
        ):
            raise ModelUnavailable("The provider returned no complete usage evidence; cost is unavailable.")
        if strict_usage:
            prompt_details = getattr(usage, "prompt_tokens_details", None)
            completion_details = getattr(usage, "completion_tokens_details", None)
            raw_usage = [
                getattr(usage, "prompt_tokens", None),
                getattr(usage, "completion_tokens", None),
                getattr(prompt_details, "cached_tokens", None),
                getattr(completion_details, "reasoning_tokens", None),
            ]
            if any(value is not None and (type(value) is not int or value < 0) for value in raw_usage):
                raise ModelUnavailable("The provider returned invalid token usage; measured cost is unavailable.")
        input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
        # Present on some provider responses (prompt caching, reasoning models). Read
        # directly from the response rather than estimated, so it stays 0 when absent.
        prompt_details = getattr(usage, "prompt_tokens_details", None)
        cached_input_tokens = int(getattr(prompt_details, "cached_tokens", 0) or 0)
        completion_details = getattr(usage, "completion_tokens_details", None)
        reasoning_tokens = int(getattr(completion_details, "reasoning_tokens", 0) or 0)
        content = response.choices[0].message.content or ""
        cost, price_configured = calculate_cost_usd(target_deployment, input_tokens, output_tokens)

        parsed = None
        if json_response:
            try:
                parsed = json.loads(content)
            except json.JSONDecodeError:
                parsed = None

        return ModelResult(
            route=route,
            deployment=target_deployment,
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            duration_ms=duration_ms,
            calculated_cost_usd=cost,
            price_configured=price_configured,
            request_id=getattr(response, "id", None),
            model_version=getattr(response, "model", None),
            parsed=parsed,
            cached_input_tokens=cached_input_tokens,
            reasoning_tokens=reasoning_tokens,
        )


class UnavailableModelAdapter:
    """Used when no deployment is configured. Never fabricates model output."""

    async def generate(self, **_: object) -> ModelResult:
        raise ModelUnavailable(
            "No Foundry deployment is configured. Set TOKENOS_MODEL_MODE=foundry and the "
            "deployment variables to enable AI routes."
        )


_active_adapter = None


def reset_model_adapter() -> None:
    global _active_adapter
    _active_adapter = None


def get_model_adapter():
    global _active_adapter
    if _active_adapter is not None:
        return _active_adapter
    if settings.foundry_configured:
        _active_adapter = FoundryModelAdapter()
    else:
        _active_adapter = UnavailableModelAdapter()
    return _active_adapter


class ModelAdapterProxy:
    """Delegates to the currently active model adapter so runtime updates take effect."""

    async def generate(self, **kwargs) -> ModelResult:
        return await get_model_adapter().generate(**kwargs)


model_adapter = ModelAdapterProxy()


def model_available() -> bool:
    return settings.foundry_configured
