# OpenBotX Architecture

## Overview

OpenBotX follows a provider-based architecture where everything is a provider. Messages flow through gateways, get processed by the orchestrator with the help of the AI agent, and responses are sent back through the appropriate gateway.

## Core Components

### Message Flow

```
Gateway → MessageBus → Orchestrator → Agent → Response → Gateway
              ↓              ↓           ↓
           Queue         Directives   Context
                         ToolPolicy   Skills
                         Compaction   Tools
                         Security
```

### Processing Pipeline

1. **Directive Parsing**: Extract control directives from message
2. **Attachment Processing**: Transcribe audio, process images
3. **Security Check**: Validate input for injection attempts
4. **Context Loading**: Load conversation history and summary
5. **Tool Filtering**: Apply tool profile policy
6. **Skill Matching**: Find relevant skills for the request
7. **Prompt Building**: Construct system prompt with context
8. **Agent Processing**: Execute PydanticAI agent
9. **Memory Update**: Save conversation turn
10. **Response Routing**: Send response via gateway

### Components

#### 1. Gateways (providers/gateway/)

Entry and exit points for messages:
- **CLI**: Interactive terminal mode
- **WebSocket**: Real-time bidirectional communication
- **Telegram**: Telegram bot integration
- **HTTP**: REST API endpoint

#### 2. Message Bus (core/message_bus.py)

Async queue system for message processing:
- In-memory queue with configurable size
- Retry mechanism with dead-letter queue
- Message acknowledgment

#### 3. Orchestrator (core/orchestrator.py)

Main processing loop:
1. Receive message from queue
2. Process attachments (transcribe audio)
3. Run security checks
4. Load context from memory
5. Select relevant skills/tools
6. Invoke AI agent
7. Save to memory
8. Send response

#### 4. Agent Brain (agent/brain.py)

PydanticAI-based agent:
- Dynamic tool registration
- Skill-aware prompting
- Context injection
- Learning mode

#### 5. Context Store (core/context_store.py)

Conversation memory using Markdown files:
- History per channel
- Automatic summarization
- Token budget management

#### 6. Skills Registry (core/skills_registry.py)

Skills from Markdown files:
- YAML frontmatter for metadata
- Trigger matching
- Dynamic skill creation (learn mode)

#### 7. Tools Registry (core/tools_registry.py)

Python functions as tools:
- Decorator-based registration
- Schema generation for LLM
- Async support

#### 8. Security Manager (core/security.py)

Security layers:
- Prompt injection detection
- Tool allowlist/denylist
- Tool approval mechanism

#### 9. Directive Parser (helpers/directives.py)

Message directives control AI behavior:
- `/think` - Enable extended thinking mode
- `/verbose` - Provide detailed explanations
- `/reasoning` - Show reasoning process
- `/elevated` - Request elevated permissions
- `/minimal`, `/coding`, `/messaging`, `/full` - Set tool profile
- `/quiet`, `/silent` - Control prompt verbosity

#### 10. Tool Policy (core/tool_policy.py)

Tool access control system:
- **Profiles**: MINIMAL, CODING, MESSAGING, FULL
- **Groups**: FS, WEB, MEMORY, SESSIONS, UI, AUTOMATION, MESSAGING, DATABASE, STORAGE, SCHEDULER, SYSTEM
- Allowlists and denylists
- Elevation requirements

#### 11. Message Compaction (core/compaction.py)

Context management strategies:
- **ADAPTIVE**: Dynamic adjustment based on context budget
- **PROGRESSIVE**: Incremental summarization of older messages
- **TRUNCATE**: Simple truncation of old messages

#### 12. Prompt Builder (agent/prompt_builder.py)

Modular system prompt construction:
- Sections: CONTEXT, IDENTITY, SECURITY, FORMATTING, TOOLS, SKILLS, MEMORY, REASONING, LANGUAGE
- Prompt modes: FULL, MINIMAL, NONE
- Directive-aware generation

#### 9. Telemetry (core/telemetry.py)

Comprehensive logging:
- Token usage tracking
- Tool call auditing
- Operation metrics

## Provider Types

| Type | Description | Implementations |
|------|-------------|-----------------|
| Gateway | Message I/O | CLI, WebSocket, Telegram |
| LLM | AI models | Anthropic, OpenAI |
| Storage | File storage | Local, S3 |
| Filesystem | File operations | Local |
| Database | Data persistence | SQLite |
| Scheduler | Job scheduling | Cron |
| Transcription | Audio to text | Whisper |
| TTS | Text to speech | OpenAI |
| MCP | Model Context Protocol | Client |

## Data Flow

### Inbound Message

```python
InboundMessage:
  id: str
  channel_id: str
  user_id: str | None
  gateway: GatewayType
  message_type: MessageType
  text: str | None
  attachments: list[Attachment]
  status: MessageStatus
  correlation_id: str
  timestamp: datetime
```

### Outbound Message

```python
OutboundMessage:
  id: str
  channel_id: str
  reply_to: str | None
  gateway: GatewayType
  response_type: ResponseCapability
  text: str | None
  attachments: list[Attachment]
  correlation_id: str
```

## API Structure

```
/api
├── /messages      # Message operations
├── /skills        # Skill management
├── /tools         # Tool listing
├── /providers     # Provider health
├── /scheduler     # Job management
│   ├── /cron      # Cron jobs
│   └── /schedule  # One-time jobs
├── /memory        # Context management
├── /media         # File storage
├── /logs          # Telemetry
└── /system        # System info
```

## Configuration

Configuration is loaded from:
1. `config.yml` - Main configuration
2. `.env` - Environment variables (secrets)

Environment variables in config.yml use `${VAR_NAME}` syntax and are expanded at load time.
