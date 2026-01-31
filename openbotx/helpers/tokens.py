"""Token counting utilities for OpenBotX."""

from functools import lru_cache
from typing import Any

import tiktoken


@lru_cache(maxsize=10)
def _get_encoding(model: str) -> tiktoken.Encoding:
    """Get tiktoken encoding for a model.

    Args:
        model: Model name

    Returns:
        Tiktoken encoding
    """
    try:
        return tiktoken.encoding_for_model(model)
    except KeyError:
        # Default to cl100k_base for unknown models
        return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str, model: str = "gpt-4") -> int:
    """Count tokens in text.

    Args:
        text: Text to count tokens for
        model: Model name for tokenizer

    Returns:
        Number of tokens
    """
    encoding = _get_encoding(model)
    return len(encoding.encode(text))


def estimate_tokens(text: str) -> int:
    """Estimate tokens without model-specific tokenizer.

    Uses a simple heuristic: ~4 characters per token on average.

    Args:
        text: Text to estimate tokens for

    Returns:
        Estimated number of tokens
    """
    return len(text) // 4 + 1


def count_message_tokens(
    messages: list[dict[str, Any]],
    model: str = "gpt-4",
) -> int:
    """Count tokens in a list of messages.

    Args:
        messages: List of message dicts with 'role' and 'content'
        model: Model name for tokenizer

    Returns:
        Total number of tokens
    """
    encoding = _get_encoding(model)
    total = 0

    for message in messages:
        # Every message follows <|start|>{role/name}\n{content}<|end|>\n
        total += 4

        for key, value in message.items():
            if isinstance(value, str):
                total += len(encoding.encode(value))
            if key == "name":  # If there's a name, the role is omitted
                total -= 1  # Role is always required and always 1 token

    total += 2  # Every reply is primed with <|start|>assistant

    return total


def truncate_to_token_limit(
    text: str,
    max_tokens: int,
    model: str = "gpt-4",
    suffix: str = "...",
) -> str:
    """Truncate text to fit within token limit.

    Args:
        text: Text to truncate
        max_tokens: Maximum number of tokens
        model: Model name for tokenizer
        suffix: Suffix to add when truncating

    Returns:
        Truncated text
    """
    encoding = _get_encoding(model)
    tokens = encoding.encode(text)

    if len(tokens) <= max_tokens:
        return text

    # Account for suffix tokens
    suffix_tokens = len(encoding.encode(suffix))
    truncated_tokens = tokens[: max_tokens - suffix_tokens]

    return encoding.decode(truncated_tokens) + suffix


def split_into_chunks(
    text: str,
    chunk_size: int = 2000,
    model: str = "gpt-4",
    overlap: int = 100,
) -> list[str]:
    """Split text into chunks of specified token size.

    Args:
        text: Text to split
        chunk_size: Maximum tokens per chunk
        model: Model name for tokenizer
        overlap: Number of tokens to overlap between chunks

    Returns:
        List of text chunks
    """
    encoding = _get_encoding(model)
    tokens = encoding.encode(text)

    if len(tokens) <= chunk_size:
        return [text]

    chunks = []
    start = 0

    while start < len(tokens):
        end = start + chunk_size
        chunk_tokens = tokens[start:end]
        chunks.append(encoding.decode(chunk_tokens))
        start = end - overlap

    return chunks


class TokenBudget:
    """Manage token budget for a conversation."""

    def __init__(
        self,
        max_tokens: int = 100000,
        model: str = "gpt-4",
        reserve_for_response: int = 4096,
    ) -> None:
        """Initialize token budget.

        Args:
            max_tokens: Maximum total tokens
            model: Model name for tokenizer
            reserve_for_response: Tokens to reserve for response
        """
        self.max_tokens = max_tokens
        self.model = model
        self.reserve_for_response = reserve_for_response
        self.used_tokens = 0

    @property
    def available_tokens(self) -> int:
        """Get available tokens for context."""
        return self.max_tokens - self.used_tokens - self.reserve_for_response

    def add(self, text: str) -> bool:
        """Add text to budget.

        Args:
            text: Text to add

        Returns:
            True if added successfully, False if would exceed budget
        """
        tokens = count_tokens(text, self.model)
        if tokens > self.available_tokens:
            return False
        self.used_tokens += tokens
        return True

    def fits(self, text: str) -> bool:
        """Check if text fits in budget.

        Args:
            text: Text to check

        Returns:
            True if fits, False otherwise
        """
        tokens = count_tokens(text, self.model)
        return tokens <= self.available_tokens

    def reset(self) -> None:
        """Reset the token budget."""
        self.used_tokens = 0
