"""LLM backend abstraction and client factory."""

import logging
import time
from dataclasses import dataclass
from typing import Callable, Dict

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    """Unified response from any LLM backend."""

    content: str


def create_llm_client(config: Dict) -> Callable[[str, str], LLMResponse]:
    """Factory to create LLM client based on configuration.

    Args:
        config: Configuration dict with llm_backend, and backend-specific settings

    Returns:
        A callable that takes (system: str, user: str) and returns LLMResponse
    """
    backend = config["llm_backend"]

    if backend == "claude":
        return _create_claude_client(config)
    elif backend == "local":
        return _create_local_client(config)
    else:
        raise ValueError(f"Unknown llm_backend: {backend}")


def _create_claude_client(config: Dict) -> Callable[[str, str], LLMResponse]:
    """Create Claude API client with retry logic."""
    import anthropic
    import os

    # SECURITY: API key must come from environment variable ONLY
    # Never allow storing secrets in config.yaml
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError(
            "ANTHROPIC_API_KEY environment variable not set.\n"
            "Set it with: export ANTHROPIC_API_KEY=sk-ant-..."
        )

    model = config.get("claude_model", "claude-sonnet-4-6")
    timeout = config.get("llm_timeout", 60)

    client = anthropic.Anthropic(api_key=api_key, timeout=timeout)

    def call_claude(system: str, user: str) -> LLMResponse:
        """Call Claude API with exponential backoff retry."""
        for attempt in range(3):
            try:
                response = client.messages.create(
                    model=model,
                    max_tokens=1024,
                    system=system,
                    messages=[{"role": "user", "content": user}],
                )
                return LLMResponse(content=response.content[0].text)
            except anthropic.RateLimitError as e:
                if attempt < 2:
                    wait_time = 2 ** (attempt + 1)
                    logger.warning(
                        f"Rate limited. Retrying in {wait_time}s (attempt {attempt + 1}/3)"
                    )
                    time.sleep(wait_time)
                else:
                    raise
            except (anthropic.APIConnectionError, anthropic.APITimeoutError) as e:
                if attempt < 2:
                    wait_time = 2 ** (attempt + 1)
                    logger.warning(
                        f"API error: {e}. Retrying in {wait_time}s (attempt {attempt + 1}/3)"
                    )
                    time.sleep(wait_time)
                else:
                    raise
        raise RuntimeError("call_claude: exhausted 3 attempts without returning or raising")

    return call_claude


def _create_local_client(config: Dict) -> Callable[[str, str], LLMResponse]:
    """Create local LLM client (LM Studio / Ollama) with retry logic."""
    import openai

    base_url = config["local_base_url"]
    model = config.get("local_model", "llama-3.2-3b-instruct")
    timeout = config.get("llm_timeout", 60)

    client = openai.OpenAI(base_url=base_url, api_key="not-needed", timeout=timeout)

    def call_local(system: str, user: str) -> LLMResponse:
        """Call local LLM with exponential backoff retry."""
        for attempt in range(3):
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    temperature=0.7,
                )
                return LLMResponse(content=response.choices[0].message.content)
            except (openai.RateLimitError, openai.APIStatusError) as e:
                if attempt < 2 and getattr(e, "status_code", None) in (429, 500, 503):
                    wait_time = 2 ** (attempt + 1)
                    logger.warning(
                        f"LLM error ({e}). Retrying in {wait_time}s (attempt {attempt + 1}/3)"
                    )
                    time.sleep(wait_time)
                else:
                    raise
            except (openai.APIConnectionError, openai.APITimeoutError) as e:
                if attempt < 2:
                    wait_time = 2 ** (attempt + 1)
                    logger.warning(
                        f"Connection error: {e}. Retrying in {wait_time}s (attempt {attempt + 1}/3)"
                    )
                    time.sleep(wait_time)
                else:
                    raise
        raise RuntimeError("call_local: exhausted 3 attempts without returning or raising")

    return call_local
