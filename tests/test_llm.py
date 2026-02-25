"""Tests for LLM module."""

import os
from unittest.mock import MagicMock, patch

import pytest

from obs_summarizer.llm import LLMResponse, _create_claude_client, _create_local_client


def test_llm_response():
    """LLMResponse dataclass."""
    response = LLMResponse(content="Test content")
    assert response.content == "Test content"


def test_create_claude_client_success():
    """Claude client calls API successfully."""
    config = {
        "llm_backend": "claude",
        "claude_model": "claude-sonnet-4-6",
        "llm_timeout": 60,
    }

    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test"}):
        with patch("anthropic.Anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.return_value = mock_client

            mock_response = MagicMock()
            mock_response.content = [MagicMock(text="Test response")]
            mock_client.messages.create.return_value = mock_response

            client = _create_claude_client(config)
            response = client(system="test system", user="test user")

            assert isinstance(response, LLMResponse)
            assert response.content == "Test response"


def test_create_local_client_success():
    """Local client calls LM Studio/Ollama successfully."""
    config = {
        "llm_backend": "local",
        "local_base_url": "http://localhost:1234/v1",
        "local_model": "llama-3.2-3b-instruct",
        "llm_timeout": 60,
    }

    with patch("openai.OpenAI") as mock_openai:
        mock_client = MagicMock()
        mock_openai.return_value = mock_client

        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Local response"))]
        mock_client.chat.completions.create.return_value = mock_response

        client = _create_local_client(config)
        response = client(system="test system", user="test user")

        assert isinstance(response, LLMResponse)
        assert response.content == "Local response"


def test_claude_client_retry_on_rate_limit():
    """Claude client retries on rate limit."""
    config = {
        "llm_backend": "claude",
        "claude_model": "claude-sonnet-4-6",
    }

    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test"}):
        with patch("anthropic.Anthropic") as mock_anthropic:
            with patch("obs_summarizer.llm.time.sleep"):  # Don't actually sleep
                mock_client = MagicMock()
                mock_anthropic.return_value = mock_client

                # Fail twice, succeed on third try
                import anthropic

                mock_client.messages.create.side_effect = [
                    anthropic.RateLimitError("Rate limit", response=MagicMock(), body={}),
                    anthropic.RateLimitError("Rate limit", response=MagicMock(), body={}),
                    MagicMock(content=[MagicMock(text="Success")]),
                ]

                client = _create_claude_client(config)
                response = client(system="test", user="test")

                assert response.content == "Success"
                assert mock_client.messages.create.call_count == 3


def test_local_client_retry_on_error():
    """Local client retries on transient errors."""
    config = {
        "llm_backend": "local",
        "local_base_url": "http://localhost:1234/v1",
        "local_model": "llama-3.2-3b-instruct",
    }

    with patch("openai.OpenAI") as mock_openai:
        with patch("obs_summarizer.llm.time.sleep"):
            mock_client = MagicMock()
            mock_openai.return_value = mock_client

            import openai

            # Fail with 503 (transient), then succeed
            mock_client.chat.completions.create.side_effect = [
                openai.APIStatusError(
                    "Service unavailable", response=MagicMock(status_code=503), body={}
                ),
                MagicMock(
                    choices=[MagicMock(message=MagicMock(content="Success"))]
                ),
            ]

            client = _create_local_client(config)
            response = client(system="test", user="test")

            assert response.content == "Success"
