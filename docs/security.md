# Security Documentation

OpenBotX implements multiple security layers to protect against misuse.

## Prompt Injection Detection

The security system detects and blocks common prompt injection patterns:

### Detected Patterns

- **Instruction Override**: "ignore previous instructions", "disregard all prompts"
- **Role Playing**: "you are now", "pretend to be", "act as if"
- **System Prompt Extraction**: "reveal your system prompt", "show initial instructions"
- **Jailbreak Attempts**: "DAN mode", "do anything now", "bypass safety"
- **Delimiter Injection**: "[system]", "<|im_start|>", "```system"
- **Encoding Attacks**: "base64 decode", "rot13"

### Configuration

In `config.yml`:

```yaml
security:
  prompt_injection_detection: true
  tool_approval_required: false
  max_tokens_per_request: 100000
  allowed_tools: []  # Empty = all allowed
  denied_tools: []
```

## Tool Security

### Tool Allowlist/Denylist

Restrict which tools can be used:

```yaml
security:
  allowed_tools:
    - get_current_time
    - calculate
  denied_tools:
    - dangerous_tool
```

### Tool Approval

Mark tools that require user approval:

```python
@tool(
    name="sensitive_operation",
    security={"approval_required": True},
)
def tool_sensitive(param: str) -> str:
    ...
```

### Tool Categories

- **Safe**: No restrictions
- **Approval Required**: User must approve each call
- **Admin Only**: Only admin users can use
- **Dangerous**: Marked for extra caution

## Gateway Security

### Telegram Allowlist

Restrict which users can interact with the Telegram bot:

```yaml
gateways:
  telegram:
    enabled: true
    token: "${TELEGRAM_BOT_TOKEN}"
    allowed_users:
      - "123456789"  # Telegram user IDs
```

### WebSocket Security

WebSocket connections are identified by unique client IDs. Consider adding authentication for production use.

## API Security

For production deployment, consider:

1. **Authentication**: Add JWT or API key authentication
2. **Rate Limiting**: Prevent abuse
3. **HTTPS**: Use TLS encryption
4. **CORS**: Restrict allowed origins

## Input Sanitization

All user inputs are sanitized:

- Remove potential role markers
- Escape special characters
- Limit input length

## Audit Logging

All operations are logged:

```python
# Every tool call is audited
{
  "correlation_id": "xxx",
  "tool_name": "calculate",
  "arguments": {"expression": "2+2"},
  "result": "4",
  "success": true,
  "duration_ms": 5
}
```

## Security Violation Handling

When a security violation is detected:

1. Request is rejected
2. Violation is logged
3. Standard rejection message is returned
4. No internal details are exposed

## Best Practices

### For Operators

1. **API Keys**: Never commit API keys to version control
2. **Environment Variables**: Use `.env` for secrets
3. **Telegram**: Always set `allowed_users` in production
4. **Logging**: Enable JSON logging for security analysis
5. **Updates**: Keep OpenBotX and dependencies updated

### For Skill Authors

1. **No Secrets**: Never include secrets in skill definitions
2. **Input Validation**: Validate all inputs in tools
3. **Least Privilege**: Request only needed permissions
4. **Error Messages**: Don't expose internal details in errors

### For Tool Authors

1. **Validate Inputs**: Check all parameters
2. **Limit Scope**: Don't expose more than needed
3. **Mark Dangerous**: Use security flags appropriately
4. **Handle Errors**: Catch exceptions gracefully

## Incident Response

If you suspect a security issue:

1. Check logs for unusual patterns
2. Review recent tool calls
3. Check for prompt injection attempts
4. Consider rotating API keys
5. Report issues to the security team
