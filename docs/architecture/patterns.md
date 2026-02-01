# OpenBotX Architectural Patterns

This document explains the patterns implemented, where they come from, and why they were chosen.

---

## 1. Tool Profiles and Groups System

### Origin

Common pattern in agent systems that need to control tool access based on context or permissions.

### Problem Solved

- Agents with unrestricted access to all tools can perform unwanted actions
- Simple tasks do not need complex tools
- Security: some tools are sensitive (fs, database)

### Solution Implemented

```
ToolProfile (MINIMAL, CODING, MESSAGING, FULL)
    |
    v
ToolGroup (FS, WEB, MEMORY, DATABASE, etc)
    |
    v
Individual tools
```

Each profile maps to a set of groups, and each tool belongs to a group.

### Benefits

- User can restrict tools per message
- Fewer tools in the prompt = fewer tokens
- Security by default (minimal has no fs/database)

---

## 2. Directives System (Slash Commands)

### Origin

Pattern inspired by chat interfaces (Slack, Discord) where commands start with `/`.

### Problem Solved

- User needs to control agent behavior
- Different messages need different treatment
- Some actions require confirmation/elevation

### Solution Implemented

```
Message: "/reasoning /minimal why does this happen?"
           |          |
           v          v
     MessageDirective  PromptMode
     (REASONING)      (MINIMAL)
```

Regex extracts directives from the start of the message; cleaned text goes to the agent.

### Benefits

- Granular control per message
- Familiar syntax for users
- Does not pollute the message text

---

## 3. Modular Prompt with Sections

### Origin

Prompt composition pattern where each "section" can be enabled/disabled.

### Problem Solved

- Large prompts consume many tokens
- Not every task needs all instructions
- Maintenance: change one part without affecting others

### Solution Implemented

```
PromptBuilder
    |-- CONTEXT (priority 100)
    |-- IDENTITY (priority 90)
    |-- SECURITY (priority 85)
    |-- FORMATTING (priority 80)
    |-- LANGUAGE (priority 75)
    |-- TOOLS (priority 60)
    |-- SKILLS (priority 50)
    |-- MEMORY (priority 40)
    |-- REASONING (priority 30)
    `-- CUSTOM (priority 20)
```

Each section has:
- `priority`: Order in the final prompt
- `enabled`: Whether it appears or not
- `min_mode`: Minimum mode to appear (FULL/MINIMAL)

### Benefits

- Token economy for simple tasks
- Easy to add/remove sections
- Priorities ensure consistent order

---

## 4. Dual Summary (User + Conversation)

### Origin

Memory pattern that separates "who the user is" from "what we are talking about".

### Problem Solved

- Single summary mixes everything
- User information gets lost in the middle
- Conversation context is not personalized

### Solution Implemented

```
ChannelContext
    |-- user_summary: "User is a Python dev, likes simple solutions"
    `-- conversation_summary: "Discussing microservices architecture"
```

Two separate summaries, each with a clear purpose.

### Benefits

- Personalization: agent "remembers" user preferences
- Context: knows what is being discussed even after compaction
- Economy: summaries are smaller than full history

---

## 5. Adaptive Context Compaction

### Origin

Pattern to manage LLM context limits.

### Problem Solved

- Long conversations exceed token limit
- Simple truncation loses information
- Summarizing everything is expensive and slow

### Solution Implemented

Three strategies:

```
ADAPTIVE (default)
- Calculates how many messages fit
- Prioritizes most recent
- Guarantees minimum message count

PROGRESSIVE
- Keeps recent messages intact
- Summarizes older ones incrementally
- Updates existing summary

TRUNCATE
- Removes oldest until it fits
- Simple and fast
- Loses context
```

### Benefits

- Choice based on use case
- ADAPTIVE works well for most cases
- PROGRESSIVE for important conversations

---

## 6. Skills with Source Precedence

### Origin

Override/customization pattern where the user can override defaults.

### Problem Solved

- Bundled skills need to be customizable
- User wants to change behavior without editing the package
- Multiple skill sources (local, cloud, bundled)

### Solution Implemented

```
Load order by priority:
EXTRA (0) < BUNDLED (1) < MANAGED (2) < WORKSPACE (3)

If same ID:
bundled/greeting/SKILL.md  (priority 1)
workspace/greeting/SKILL.md (priority 3) <- WINS
```

### Benefits

- User can customize any skill
- Bundled is the base; project skills override when present
- No need to modify package code

---

## 7. Skill Eligibility Verification

### Origin

Requirement validation pattern before exposing functionality.

### Problem Solved

- Skill that requires ffmpeg should not appear if ffmpeg is missing
- macOS skill should not appear on Linux
- Avoid runtime errors

### Solution Implemented

```yaml
# SKILL.md
requires:
  os: [darwin, linux]
  binaries: [ffmpeg, whisper]
  providers: [transcription]
```

Checks:
1. OS compatible? If not: OS_INCOMPATIBLE
2. Binaries on PATH? If not: MISSING_BINARY
3. Config enabled? If not: CONFIG_DISABLED
4. Providers available? If not: MISSING_PROVIDER

### Benefits

- Only functional skills appear
- Clear feedback on what is missing
- Avoids runtime errors

---

## 8. Skill Content Injection into Prompt

### Origin

Pattern where specific instructions are injected dynamically into the prompt.

### Problem Solved

- Agent needs to follow skill-specific instructions
- Complex instructions do not fit in "description"
- Skill needs full context

### Solution Implemented

```
1. Message arrives
2. Skills registry finds skills that "match" (keywords)
3. FULL content of SKILL.md is injected into the prompt
4. Agent follows skill instructions
```

```
## Active Skills

The following skills are relevant to this conversation.
Follow the instructions in each skill carefully.

### SKILL: customer-service

[Full SKILL.md content here]

---
```

### Benefits

- Skills can have detailed instructions
- Agent has full context
- Easy to create complex skills

---

## Pattern Summary

| Pattern | Problem | Solution |
|--------|----------|---------|
| Tool Profiles | Access control | Profiles map to groups |
| Directives | Per-message control | Slash commands parsed |
| Modular Prompt | Token economy | Sections with priority/mode |
| Dual Summary | Structured memory | User + Conversation separate |
| Compaction | Context limit | ADAPTIVE/PROGRESSIVE/TRUNCATE |
| Skill Precedence | Customization | Sources with priority |
| Skill Eligibility | Requirements | Pre-load verification |
| Skill Injection | Complex instructions | Full content in prompt |
| Background Services | Services that start with app | start/stop_background_services, tasks |
| Relay as Service | Relay available with OpenBotX | Relay registered in background_loader |
| CDP vs Browser | Tool choice for site vs browser | Tool descriptions, no prompt rule |

---

## Design Decisions

### Why ToolProfile instead of granular permissions?

Simplicity. User says `/minimal` and does not need to know which tools exist.

### Why dual summary instead of one?

Separation of concerns. User and context are different things.

### Why ADAPTIVE as default compaction?

Works well in most cases without summarization overhead.

### Why inject full skill content?

Skills can have complex instructions that do not fit in metadata.

### Why verify eligibility at load time?

Fail fast. Better not to show a skill than to fail when using it.

---

## 9. Background Services (Start/Stop with Application)

### Origin

Pattern for services that run alongside the main application and share its lifecycle, without blocking the main loop.

### Problem Solved

- Some features (e.g. browser relay for the Chrome extension) need a long-lived server.
- That server must start when the app starts and stop when the app stops.
- It must not block the main thread (API or CLI interactive loop).

### Solution Implemented

```
background_loader.py
  _SERVICES: list of (name, enabled(config), start_fn(config))
  start_background_services(config) -> create_task for each enabled service
  stop_background_services() -> cancel all tasks, await cleanup
```

- Each service is a tuple: name, predicate `enabled(config)`, and a start function that returns a coroutine (runs until cancelled).
- On startup, for each service with `enabled(config)` true, the start coroutine is run as `asyncio.create_task(...)`.
- On shutdown, every task is cancelled and awaited so cleanup (e.g. closing the relay server) runs.

### Benefits

- Same pattern as gateways and providers: one place to start, one place to stop.
- Non-blocking: services run as tasks.
- Easy to add new services by appending to `_SERVICES`.

---

## 10. Relay as a Background Service

### Origin

The browser relay (Chrome extension bridge) is implemented as one of the background services, not as a provider or a separate process.

### Problem Solved

- Relay must be available when the user runs OpenBotX (API or CLI).
- It must not require a separate command (e.g. "run relay in another terminal").
- It must stop cleanly when the application stops.

### Solution Implemented

- In `background_loader`, the relay is registered as a service: enabled when `config.relay.enabled` is true, start coroutine = `run_relay_server(host, port)`.
- API lifespan: after `initialize_gateways`, call `start_background_services(config)`; before `stop_all_gateways`, call `stop_background_services()`.
- CLI: after registering the CLI gateway, call `start_background_services(config)`; in `finally`, call `stop_background_services()` before stopping gateways and providers.

### Benefits

- Relay starts and stops with the app; no extra process or command.
- Same lifecycle pattern as other components.

---

## 11. Tool Selection: CDP vs Browser (Description-Based)

### Origin

The agent must prefer CDP tools when the user asks to "access a site" or "navigate", and use browser tools only when the user explicitly asks to "open" or "launch" a browser.

### Problem Solved

- If the model is not guided, it may use `browser_navigate` (launches a new window) when the user only wanted to open a URL in the existing Chrome tab.
- Requiring the user to say "use CDP" every time is poor UX.

### Solution Implemented

- **No prompt rule**: The prompt builder does not inject a "use CDP for sites, browser only when opening browser" sentence.
- **Tool descriptions only**:  
  - CDP tools (e.g. `cdp_navigate`, `cdp_snapshot`, `cdp_tabs`): descriptions state they are for "site access" and to "prefer over browser_* unless user asks to open a browser".  
  - Browser tools (e.g. `browser_navigate`): descriptions state "use only when the user explicitly asks to open or launch a browser".
- The model chooses tools from these descriptions; no extra directive is needed.

### Benefits

- Behavior is encoded in tool metadata, not in prompt text.
- Single source of truth: change descriptions to adjust behavior.
- Works with any prompt mode (full, minimal, etc.) as long as tool names and descriptions are present.
