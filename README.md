# OpenBotX — Personal AI Assistant

<p align="center">
    <a href="https://github.com/openbotx/openbotx" target="_blank" rel="noopener noreferrer">
        <img width="280" src="extras/images/logo.png" alt="OpenBotX Logo">
    </a>
</p>

<p align="center">
    <a href="https://badge.fury.io/py/openbotx" target="_blank" rel="noopener noreferrer">
        <img src="https://badge.fury.io/py/openbotx.svg" alt="PyPI version">
    </a>
    <a href="https://www.python.org/downloads/" target="_blank" rel="noopener noreferrer">
        <img src="https://img.shields.io/badge/python-3.11--3.13-blue.svg" alt="Python 3.11-3.13">
    </a>
    <a href="https://opensource.org/licenses/MIT" target="_blank" rel="noopener noreferrer">
        <img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT">
    </a>
</p>

<p align="center">
OpenBotX is a Python-based personal AI assistant powered by artificial intelligence.
It uses skills to define behavior, tools to execute actions, gateways for communication, and providers to connect external services and AI models.
</p>

## Features

- **Multiple Gateways**: CLI, WebSocket, Telegram, HTTP API
- **Skills System**: Define AI capabilities in Markdown files
- **Unlimited Tools**: Register Python functions as tools for the AI
- **MCP Support**: Model Context Protocol integration
- **Scheduling**: Cron jobs and one-time scheduled tasks
- **Memory**: Persistent conversation history per channel
- **Security**: Built-in prompt injection detection
- **API**: Full REST API for all operations
- **Providers**: Modular architecture - LLM, storage, database, transcription, TTS

## Installation

### Prerequisites

**Python Version:** This project requires Python 3.11 to 3.13 (3.14 is not yet supported due to dependencies).

Install [uv](https://github.com/astral-sh/uv) - a fast Python package installer and resolver:

```bash
# macOS/Linux (recommended)
curl -LsSf https://astral.sh/uv/install.sh | sh

# macOS with Homebrew
brew install uv

# Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# Or with pipx (if you have it)
pipx install uv
```

### From PyPI (Users)

```bash
# Install globally as a tool (recommended)
uv tool install openbotx

# Or install in current environment
uv pip install openbotx
```

**All features included**: Telegram, Audio (Whisper), S3, MCP, Screenshot, and more.

### From Source (Developers)

```bash
# Clone and setup
git clone https://github.com/openbotx/openbotx.git
cd openbotx
make setup

# Activate virtual environment
source .venv/bin/activate
```

## Quick Start

### For Users (after installation)

```bash
# Create a new project from starter template
mkdir my-bot
cd my-bot
openbotx init

# Edit .env file in your project directory
nano .env

# Start the bot in CLI mode
openbotx start --cli-mode

# Or start the API server
openbotx start
```

The starter template includes:
- Pre-configured `config.yml` with basic data
- Example skills in the `skills/` directory
- Environment template (`.env.example`)
- Ready-to-use folder structure

### For Developers (from source)

```bash
# First time setup
make setup

# Activate virtual environment
source .venv/bin/activate

# Create a project with the starter template
mkdir my-project
cd my-project
openbotx init

# Edit .env file in your project directory
nano .env

# Start the bot in CLI mode
openbotx start --cli-mode

# Or start the API server
openbotx start
```

## Project Structure

### Package Structure

```
openbotx/
├── openbotx/               # Main package (library code)
│   ├── core/               # Core components (orchestrator, message bus, etc.)
│   ├── providers/          # Provider implementations (LLM, gateway, storage)
│   ├── api/                # FastAPI REST API
│   ├── cli/                # CLI commands
│   ├── models/             # Pydantic data models
│   ├── agent/              # PydanticAI agent
│   └── tools/              # Built-in tools
├── docs/                   # Documentation
├── tests/                  # Test suite
├── pyproject.toml          # Package configuration
├── Makefile                # Development commands
└── README.md
```

## Configuration

When you run `openbotx init`, it creates a `config.yml`:

```yaml
version: "1.0.0"

bot:
  name: "My Assistant"
  description: "AI Assistant powered by OpenBotX"

llm:
  provider: "anthropic"  # Any PydanticAI supported provider
  model: "claude-sonnet-4-20250514"
  # Optional: max_tokens, temperature, top_p, timeout, etc

gateways:
  cli:
    enabled: true
  websocket:
    enabled: true
    port: 8765
  telegram:
    enabled: false
    token: "${TELEGRAM_BOT_TOKEN}"
    allowed_users: []

api:
  host: "0.0.0.0"
  port: 8000
```

## Creating Skills

OpenBotX includes **native skills** (like `screenshot`) built into the package. You can also create custom skills in your project's `skills/` directory, and these can override native skills.

Skills are Markdown files with YAML frontmatter:

```markdown
---
name: code-review
description: Review code for quality and best practices
version: "1.0.0"
triggers:
  - review code
  - code review
  - check my code
tools:
  - read_file
---

# Code Review Skill

## Steps
1. Read the code file(s) provided
2. Analyze for common issues
3. Check coding standards
4. Suggest improvements

## Guidelines
- Be constructive, not critical
- Explain why changes are suggested
- Prioritize security issues
```

## Creating Tools

Tools are Python functions that the AI can call:

```python
from openbotx.core.tools_registry import tool

@tool(
    name="calculate",
    description="Perform mathematical calculations",
)
def tool_calculate(expression: str) -> str:
    """Calculate a math expression."""
    return str(eval(expression))
```

## CLI Commands

```bash
openbotx init               # Initialize from starter template
openbotx init --force       # Overwrite existing files
openbotx start              # Start the API server
openbotx start --cli-mode   # Start in interactive CLI mode
openbotx status             # Show server status
openbotx skills list        # List all skills
openbotx providers list     # List all providers
openbotx send "Hello!"      # Send a message
openbotx config             # Show configuration
openbotx version            # Show version
```

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `POST /api/messages` | Send a message |
| `GET /api/skills` | List all skills |
| `GET /api/tools` | List all tools |
| `GET /api/providers` | List providers |
| `POST /api/scheduler/cron` | Create cron job |
| `GET /api/memory/{channel}` | Get conversation history |
| `GET /api/system/health` | Health check |

## Development Commands (Makefile)

```bash
# Setup & Installation
make setup          # First time setup with uv (venv + deps)
make dev-install    # Install in editable mode with dev dependencies
make install        # Install in production mode

# Testing & Quality
make test           # Run tests
make test-cov       # Run tests with coverage
make lint           # Run linter
make format         # Format code
make check          # Run all checks (lint + type check)

# Building & Publishing
make build          # Build package
make publish-test   # Publish to TestPyPI
make publish        # Publish to PyPI

# Versioning
make version        # Show current version
make bump-patch     # Bump patch version (0.0.X)
make bump-minor     # Bump minor version (0.X.0)
make bump-major     # Bump major version (X.0.0)

# Cleanup
make clean          # Clean build artifacts
make clean-venv     # Remove virtual environment
make reset          # Reset environment (clean venv + setup)
```

## Architecture

```
Gateway → MessageBus → Orchestrator → Agent → Response → Gateway
              ↓              ↓
           Security      Skills/Tools
              ↓              ↓
           Context        Memory
```

**Providers:**
- **LLM**: Multiple providers supported (see [Configuration](docs/configuration.md))
- **Gateway**: CLI, WebSocket, Telegram, HTTP
- **Storage**: Local filesystem, S3
- **Database**: SQLite
- **Scheduler**: Cron, one-time schedules
- **Transcription**: Multiple providers supported
- **TTS**: Multiple providers supported

## Documentation

For detailed documentation, see:

- [Configuration](docs/configuration.md) - Complete configuration reference
- [Architecture](docs/architecture.md) - System design and components
- [API Reference](docs/api.md) - Complete REST API documentation
- [Skills](docs/skills.md) - Creating and managing skills
- [Tools](docs/tools.md) - Creating custom tools
- [Security](docs/security.md) - Security features and best practices
- [Providers](docs/providers/) - Gateway and provider implementations

## License

MIT License - see [LICENSE](LICENSE) for details.

## Links

- [Documentation](https://github.com/openbotx/openbotx)
- [GitHub](https://github.com/openbotx/openbotx)
- [PyPI](https://pypi.org/project/openbotx/)
