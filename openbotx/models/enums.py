"""Enumerations for OpenBotX - all types defined as enums for type safety."""

from enum import Enum


class MessageType(str, Enum):
    """Type of message content."""

    TEXT = "text"
    AUDIO = "audio"
    IMAGE = "image"
    VIDEO = "video"
    FILE = "file"


class ResponseContentType(str, Enum):
    """Type of response content from agent."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    SUCCESS = "success"
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"


class MessageStatus(str, Enum):
    """Status of message processing."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    REJECTED = "rejected"


class GatewayType(str, Enum):
    """Type of gateway provider."""

    CLI = "cli"
    WEBSOCKET = "websocket"
    TELEGRAM = "telegram"
    HTTP = "http"
    SCHEDULER = "scheduler"


class ProviderType(str, Enum):
    """Type of provider."""

    GATEWAY = "gateway"
    LLM = "llm"
    STORAGE = "storage"
    FILESYSTEM = "filesystem"
    DATABASE = "database"
    SCHEDULER = "scheduler"
    TRANSCRIPTION = "transcription"
    TTS = "tts"
    MCP = "mcp"


class ProviderStatus(str, Enum):
    """Status of a provider."""

    INITIALIZED = "initialized"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


class ResponseCapability(str, Enum):
    """Response capabilities supported by a gateway."""

    TEXT = "text"
    AUDIO = "audio"
    IMAGE = "image"
    VIDEO = "video"


class JobType(str, Enum):
    """Type of scheduled job."""

    CRON = "cron"
    SCHEDULED = "scheduled"


class JobStatus(str, Enum):
    """Status of a scheduled job."""

    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class SecurityViolationType(str, Enum):
    """Type of security violation detected."""

    PROMPT_INJECTION = "prompt_injection"
    FORBIDDEN_ACTION = "forbidden_action"
    UNAUTHORIZED = "unauthorized"
    RATE_LIMIT = "rate_limit"


class StorageType(str, Enum):
    """Type of storage provider."""

    LOCAL = "local"
    S3 = "s3"


class DatabaseType(str, Enum):
    """Type of database provider."""

    SQLITE = "sqlite"
    POSTGRES = "postgres"


class TranscriptionProviderType(str, Enum):
    """Type of transcription provider."""

    WHISPER = "whisper"


class TTSProviderType(str, Enum):
    """Type of TTS provider."""

    OPENAI = "openai"


class LogLevel(str, Enum):
    """Log level."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class LogFormat(str, Enum):
    """Log format."""

    JSON = "json"
    TEXT = "text"
