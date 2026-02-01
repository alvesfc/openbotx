"""Directive parser for message processing."""

import re

from openbotx.models.enums import MessageDirective, PromptMode, ToolProfile
from openbotx.models.message import ParsedDirectives

DIRECTIVE_PATTERNS: dict[str, MessageDirective] = {
    r"/think\b": MessageDirective.THINK,
    r"/verbose\b": MessageDirective.VERBOSE,
    r"/reasoning\b": MessageDirective.REASONING,
    r"/elevated\b": MessageDirective.ELEVATED,
}

TOOL_PROFILE_PATTERNS: dict[str, ToolProfile] = {
    r"/minimal\b": ToolProfile.MINIMAL,
    r"/coding\b": ToolProfile.CODING,
    r"/messaging\b": ToolProfile.MESSAGING,
    r"/full\b": ToolProfile.FULL,
}

PROMPT_MODE_PATTERNS: dict[str, PromptMode] = {
    r"/quiet\b": PromptMode.MINIMAL,
    r"/silent\b": PromptMode.NONE,
}


def parse_directives(text: str) -> ParsedDirectives:
    """Parse directives from message text.

    Directives are commands prefixed with / that control AI behavior:
    - /think: Enable extended thinking mode
    - /verbose: Provide detailed explanations
    - /reasoning: Show reasoning process
    - /elevated: Request elevated permissions for sensitive operations
    - /minimal, /coding, /messaging, /full: Set tool profile
    - /quiet: Use minimal prompts
    - /silent: Use no system prompt

    Args:
        text: Raw message text

    Returns:
        ParsedDirectives with extracted directives and clean text
    """
    if not text:
        return ParsedDirectives()

    directives: list[MessageDirective] = []
    prompt_mode = PromptMode.FULL
    tool_profile = ToolProfile.FULL
    elevated = False
    clean_text = text

    # Extract message directives
    for pattern, directive in DIRECTIVE_PATTERNS.items():
        if re.search(pattern, clean_text, re.IGNORECASE):
            directives.append(directive)
            clean_text = re.sub(pattern, "", clean_text, flags=re.IGNORECASE)
            if directive == MessageDirective.ELEVATED:
                elevated = True

    # Extract tool profile directives
    for pattern, profile in TOOL_PROFILE_PATTERNS.items():
        if re.search(pattern, clean_text, re.IGNORECASE):
            tool_profile = profile
            clean_text = re.sub(pattern, "", clean_text, flags=re.IGNORECASE)

    # Extract prompt mode directives
    for pattern, mode in PROMPT_MODE_PATTERNS.items():
        if re.search(pattern, clean_text, re.IGNORECASE):
            prompt_mode = mode
            clean_text = re.sub(pattern, "", clean_text, flags=re.IGNORECASE)

    # Clean up extra whitespace
    clean_text = re.sub(r"\s+", " ", clean_text).strip()

    return ParsedDirectives(
        directives=directives,
        clean_text=clean_text,
        prompt_mode=prompt_mode,
        tool_profile=tool_profile,
        elevated=elevated,
    )


def has_directive(text: str, directive: MessageDirective) -> bool:
    """Check if text contains a specific directive.

    Args:
        text: Message text
        directive: Directive to check for

    Returns:
        True if directive is present
    """
    for pattern, dir_type in DIRECTIVE_PATTERNS.items():
        if dir_type == directive and re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def extract_directive_value(text: str, directive: str) -> str | None:
    """Extract value for a directive with format /directive:value.

    Args:
        text: Message text
        directive: Directive name (without /)

    Returns:
        Extracted value or None
    """
    pattern = rf"/{directive}:([^\s]+)"
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        return match.group(1)
    return None
