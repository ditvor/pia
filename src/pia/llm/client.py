"""LLM client — thin async wrapper supporting Anthropic and OpenAI.

The client is intentionally minimal: one method (complete), one config
surface (constructor), and an injected SDK client so tests never hit
the network.

Provider selection is controlled by the ``provider`` argument:
  - ``"anthropic"``  — uses the official ``anthropic`` Python SDK (bundled dep)
  - ``"openai"``     — uses the ``openai`` Python SDK (optional dep; raises
                       ImportError with a helpful message if not installed)
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Supported provider identifiers.
_PROVIDER_ANTHROPIC = "anthropic"
_PROVIDER_OPENAI = "openai"
_SUPPORTED_PROVIDERS = (_PROVIDER_ANTHROPIC, _PROVIDER_OPENAI)


class LLMError(Exception):
    """Raised when the LLM API returns an unexpected response."""


class LLMClient:
    """Async LLM client supporting Anthropic and OpenAI.

    Args:
        provider: ``"anthropic"`` or ``"openai"``.
        model: Model identifier (e.g. ``"claude-sonnet-4-6"``).
        api_key: API key for the chosen provider.
        max_tokens: Maximum tokens in the completion.
        temperature: Sampling temperature. Use 0.1 for factual responses.
        _client: Optional pre-built SDK client injected for testing.
            When omitted the real SDK client is constructed.
    """

    def __init__(
        self,
        provider: str,
        model: str,
        api_key: str,
        max_tokens: int = 4096,
        temperature: float = 0.1,
        _client: Any = None,
    ) -> None:
        if provider not in _SUPPORTED_PROVIDERS:
            raise ValueError(
                f"Unsupported LLM provider {provider!r}. "
                f"Choose one of: {', '.join(_SUPPORTED_PROVIDERS)}"
            )

        self._provider = provider
        self._model = model
        self._max_tokens = max_tokens
        self._temperature = temperature

        if _client is not None:
            self._client = _client
        elif provider == _PROVIDER_ANTHROPIC:
            import anthropic
            self._client = anthropic.AsyncAnthropic(api_key=api_key)
        else:
            try:
                import openai
            except ImportError as exc:
                raise ImportError(
                    "The 'openai' package is required to use the OpenAI provider. "
                    "Install it with: pip install openai"
                ) from exc
            self._client = openai.AsyncOpenAI(api_key=api_key)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def complete(self, prompt: str) -> str:
        """Send *prompt* to the LLM and return the response text.

        Args:
            prompt: The fully-assembled prompt string.

        Returns:
            The model's text response.

        Raises:
            LLMError: If the API call fails or returns an unexpected shape.
        """
        logger.debug(
            "LLM request — provider=%s model=%s prompt_chars=%d",
            self._provider,
            self._model,
            len(prompt),
        )

        try:
            if self._provider == _PROVIDER_ANTHROPIC:
                return await self._complete_anthropic(prompt)
            return await self._complete_openai(prompt)
        except LLMError:
            raise
        except Exception as exc:
            raise LLMError(f"LLM call failed: {exc}") from exc

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Close the underlying SDK client if it exposes a close method."""
        close = getattr(self._client, "close", None)
        if close is not None:
            await close()

    async def __aenter__(self) -> LLMClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    # ------------------------------------------------------------------
    # Provider implementations
    # ------------------------------------------------------------------

    async def _complete_anthropic(self, prompt: str) -> str:
        """Call the Anthropic Messages API."""
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            temperature=self._temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        try:
            return response.content[0].text
        except (IndexError, AttributeError) as exc:
            raise LLMError(f"Unexpected Anthropic response shape: {response}") from exc

    async def _complete_openai(self, prompt: str) -> str:
        """Call the OpenAI Chat Completions API."""
        response = await self._client.chat.completions.create(
            model=self._model,
            max_tokens=self._max_tokens,
            temperature=self._temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        try:
            return response.choices[0].message.content
        except (IndexError, AttributeError) as exc:
            raise LLMError(f"Unexpected OpenAI response shape: {response}") from exc
