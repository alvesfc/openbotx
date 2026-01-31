# Gateway Providers

Gateways are the entry and exit points for messages in OpenBotX.

## Available Gateways

### CLI Gateway

Interactive terminal interface.

**Configuration:**
```yaml
gateways:
  cli:
    enabled: true
```

**Usage:**
```bash
python openbotx.py start --cli-mode
```

**Features:**
- Interactive REPL
- Text input/output
- Immediate responses

### WebSocket Gateway

Real-time bidirectional communication.

**Configuration:**
```yaml
gateways:
  websocket:
    enabled: true
    host: "0.0.0.0"
    port: 8765
```

**Message Format (Inbound):**
```json
{
  "type": "text",
  "text": "Hello!",
  "user_id": "optional-user-id"
}
```

**Message Format (Outbound):**
```json
{
  "type": "message",
  "id": "msg-uuid",
  "text": "Response text",
  "timestamp": "2024-01-01T00:00:00Z"
}
```

**Features:**
- Real-time communication
- Multiple clients
- Text and image responses

### Telegram Gateway

Telegram bot integration.

**Configuration:**
```yaml
gateways:
  telegram:
    enabled: true
    token: "${TELEGRAM_BOT_TOKEN}"
    allowed_users:
      - "${TELEGRAM_ALLOWED_USER_ID}"
```

**Features:**
- Text messages
- Voice messages (transcribed)
- Photo messages
- User allowlist
- Reply support

**Setup:**
1. Create bot with @BotFather
2. Get the bot token
3. Get your user ID (use @userinfobot)
4. Configure in `.env`

### HTTP Gateway

Messages via REST API.

**Endpoint:**
```http
POST /api/messages
Content-Type: application/json

{
  "channel_id": "my-channel",
  "text": "Hello!",
  "gateway": "http"
}
```

**Features:**
- Programmatic access
- Integration with other systems
- Async processing

## Response Capabilities

Each gateway supports different response types:

| Gateway | Text | Audio | Image | Video |
|---------|------|-------|-------|-------|
| CLI | ✓ | - | - | - |
| WebSocket | ✓ | - | ✓ | - |
| Telegram | ✓ | ✓ | ✓ | - |
| HTTP | ✓ | ✓ | ✓ | ✓ |

## Creating Custom Gateways

Extend `GatewayProvider`:

```python
from openbotx.providers.gateway.base import GatewayProvider
from openbotx.models.enums import GatewayType, ResponseCapability

class MyGateway(GatewayProvider):
    gateway_type = GatewayType.HTTP  # Or add new type

    def __init__(self, name: str, config: dict):
        super().__init__(name, config)
        self._response_capabilities = {
            ResponseCapability.TEXT,
            ResponseCapability.IMAGE,
        }

    async def initialize(self) -> None:
        # Setup
        pass

    async def start(self) -> None:
        # Start listening
        pass

    async def stop(self) -> None:
        # Cleanup
        pass

    async def send(self, message: OutboundMessage) -> bool:
        # Send response
        return True
```

Register your gateway:

```python
from openbotx.providers.base import get_provider_registry

registry = get_provider_registry()
registry.register(MyGateway("my-gateway", config))
```
