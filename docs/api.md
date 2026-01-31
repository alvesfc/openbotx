# API Documentation

OpenBotX provides a REST API for all operations.

## Base URL

```
http://localhost:8000/api
```

## Endpoints

### Messages

#### Enqueue Message

```http
POST /api/messages
Content-Type: application/json

{
  "channel_id": "my-channel",
  "text": "Hello, OpenBotX!",
  "user_id": "user123",
  "gateway": "http"
}
```

Response:
```json
{
  "id": "msg-uuid",
  "channel_id": "my-channel",
  "status": "pending",
  "correlation_id": "corr-uuid"
}
```

#### Get Message History

```http
GET /api/messages/{channel_id}/history?limit=50
```

#### Clear Message History

```http
DELETE /api/messages/{channel_id}/history
```

### Skills

#### List Skills

```http
GET /api/skills
```

Response:
```json
{
  "skills": [
    {
      "id": "example-greeting",
      "name": "example-greeting",
      "description": "A simple greeting skill",
      "version": "1.0.0",
      "triggers": ["hello", "hi"]
    }
  ],
  "total": 1
}
```

#### Get Skill

```http
GET /api/skills/{skill_id}
```

#### Create Skill

```http
POST /api/skills
Content-Type: application/json

{
  "name": "My Skill",
  "description": "Does something",
  "triggers": ["keyword1", "keyword2"],
  "steps": ["Step 1", "Step 2"]
}
```

#### Reload Skills

```http
POST /api/skills/reload
```

### Tools

#### List Tools

```http
GET /api/tools
```

Response:
```json
{
  "tools": [
    {
      "name": "get_current_time",
      "description": "Get the current date and time",
      "parameters": [],
      "enabled": true
    }
  ],
  "total": 1
}
```

#### Get Tool

```http
GET /api/tools/{tool_name}
```

### Providers

#### List Providers

```http
GET /api/providers
```

Response:
```json
{
  "providers": [
    {
      "name": "sqlite",
      "type": "database",
      "status": "running",
      "healthy": true
    }
  ],
  "total": 1
}
```

#### Provider Health

```http
GET /api/providers/health
```

### Scheduler

#### List Cron Jobs

```http
GET /api/scheduler/cron
```

#### Create Cron Job

```http
POST /api/scheduler/cron
Content-Type: application/json

{
  "name": "Daily Report",
  "cron_expression": "0 9 * * *",
  "message": "Generate daily report",
  "channel_id": "reports",
  "timezone": "UTC"
}
```

#### List Scheduled Jobs

```http
GET /api/scheduler/schedule
```

#### Create Scheduled Job

```http
POST /api/scheduler/schedule
Content-Type: application/json

{
  "name": "Reminder",
  "scheduled_at": "2024-12-31T23:59:00Z",
  "message": "Happy New Year!",
  "channel_id": "general"
}
```

#### Get Job

```http
GET /api/scheduler/{job_id}
```

#### Delete Job

```http
DELETE /api/scheduler/{job_id}
```

#### Pause Job

```http
POST /api/scheduler/{job_id}/pause
```

#### Resume Job

```http
POST /api/scheduler/{job_id}/resume
```

#### Run Job Now

```http
POST /api/scheduler/{job_id}/run
```

### Memory

#### Get Channel Memory

```http
GET /api/memory/{channel_id}
```

Response:
```json
{
  "channel_id": "my-channel",
  "history_count": 10,
  "summary": "Previous conversation about...",
  "total_tokens": 1500
}
```

#### Write to Memory

```http
POST /api/memory/{channel_id}
Content-Type: application/json

{
  "role": "user",
  "content": "Message content"
}
```

#### Clear Memory

```http
DELETE /api/memory/{channel_id}
```

#### List Channels

```http
GET /api/memory
```

### Media

#### List Media Files

```http
GET /api/media?prefix=&limit=100
```

#### Get Media File

```http
GET /api/media/{path}
```

#### Upload Media File

```http
POST /api/media
Content-Type: multipart/form-data

file: <binary>
```

#### Delete Media File

```http
DELETE /api/media/{path}
```

### Logs

#### Get Telemetry

```http
GET /api/logs?limit=100&correlation_id=xxx
```

#### Get Statistics

```http
GET /api/logs/stats
```

#### Get Token Usage

```http
GET /api/logs/tokens?channel_id=xxx&limit=100
```

#### Get Tool Calls

```http
GET /api/logs/tools?correlation_id=xxx&limit=100
```

#### Clear Old Logs

```http
DELETE /api/logs?older_than_hours=24
```

### System

#### Health Check

```http
GET /api/system/health
```

Response:
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "uptime_seconds": 3600,
  "providers": {"database:sqlite": true},
  "stats": {}
}
```

#### Version

```http
GET /api/system/version
```

#### Configuration

```http
GET /api/system/config
```

#### System Info

```http
GET /api/system/info
```

## Error Responses

All errors follow this format:

```json
{
  "success": false,
  "error": "Error message"
}
```

HTTP status codes:
- `400`: Bad request
- `404`: Not found
- `500`: Internal server error
- `503`: Service unavailable (provider not ready)
