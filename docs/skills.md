# Skills Documentation

Skills are capabilities defined in Markdown files that tell OpenBotX how to handle specific types of requests.

## Native vs User Skills

OpenBotX includes **built-in native skills** that come with the package, and you can create **custom user skills** in your project.

### Native Skills

- Located in the OpenBotX package (`openbotx/skills/`)
- Included with installation
- Examples: `screenshot`, `web-search`, `file-system`, etc.
- Always available without configuration

### User Skills

- Located in your project's `skills/` directory
- Created by you for custom functionality
- **Can override native skills** by using the same skill ID
- Loaded after native skills, so they take precedence

### Loading Order

1. **Native skills** are loaded first from `openbotx/skills/`
2. **User skills** are loaded second from your project's `skills/`
3. If a user skill has the same ID as a native skill, the user version replaces it

## Skill Format

Skills are stored as `SKILL.md` files with YAML frontmatter.

### Basic Structure

```markdown
---
name: skill-name
description: What this skill does
version: "1.0.0"
triggers:
  - keyword1
  - keyword2
tools:
  - tool_name
security:
  approval_required: false
---

# Skill Name

## Overview
Detailed description of what the skill does.

## Steps
1. First step
2. Second step
3. Third step

## Guidelines
- Guideline 1
- Guideline 2

## Examples
- Example 1
- Example 2
```

### Frontmatter Fields

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Unique skill name |
| `description` | string | Brief description |
| `version` | string | Semantic version |
| `triggers` | list | Keywords that activate the skill |
| `tools` | list | Tools used by this skill |
| `required_providers` | list | Required providers (e.g., "storage:s3") |
| `security.approval_required` | bool | Require approval before execution |
| `security.admin_only` | bool | Only admins can use |

## Creating Skills

### Via API

```bash
curl -X POST http://localhost:8000/api/skills \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Skill",
    "description": "Does something useful",
    "triggers": ["do something", "help me"],
    "steps": ["Step 1", "Step 2"],
    "guidelines": ["Be helpful"]
  }'
```

### Via CLI

Skills are automatically discovered from the `skills/` directory:

```bash
python openbotx.py skills reload
```

### Via Learning Mode

When OpenBotX encounters a request it doesn't know how to handle, it can create a new skill automatically:

1. Research how to accomplish the task
2. Document the approach
3. Save as a new skill
4. Use it for future requests

## Skill Matching

Skills are matched based on:

1. **Keywords**: Exact word matches in triggers
2. **Patterns**: Substring matches
3. **Intents**: Semantic matching (future)

The agent receives context about matching skills and uses their steps/guidelines to respond.

## Skill Directory Structure

```
skills/
├── greeting/
│   └── SKILL.md
├── search/
│   └── SKILL.md
├── code/
│   ├── python/
│   │   └── SKILL.md
│   └── javascript/
│       └── SKILL.md
└── custom/
    └── SKILL.md
```

## Best Practices

1. **Clear Triggers**: Use specific, unambiguous keywords
2. **Detailed Steps**: Provide clear step-by-step instructions
3. **Examples**: Include real-world usage examples
4. **Version Control**: Update version when modifying skills
5. **Security**: Mark sensitive skills as `approval_required`

## Example Skills

### Code Review Skill

```markdown
---
name: code-review
description: Review code for quality, bugs, and best practices
version: "1.0.0"
triggers:
  - review code
  - code review
  - check my code
tools:
  - read_file
  - analyze_code
---

# Code Review Skill

## Steps
1. Read the code file(s) provided
2. Analyze for common issues
3. Check coding standards
4. Identify potential bugs
5. Suggest improvements
6. Provide summary

## Guidelines
- Be constructive, not critical
- Explain why changes are suggested
- Prioritize security issues
- Consider readability
```

### Web Search Skill

```markdown
---
name: web-search
description: Search the web for information
version: "1.0.0"
triggers:
  - search for
  - look up
  - find information
tools:
  - web_search
---

# Web Search Skill

## Steps
1. Understand what user wants to find
2. Formulate search query
3. Execute search
4. Parse and summarize results
5. Present findings

## Guidelines
- Use specific search terms
- Verify information from multiple sources
- Cite sources when possible
```
