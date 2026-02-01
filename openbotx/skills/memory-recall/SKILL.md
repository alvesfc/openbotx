---
id: memory-recall
name: Memory Recall
description: Skill for searching and retrieving information from the agent's memory system
version: 1.0.0
triggers:
  keywords:
    - remember
    - recall
    - memory
    - what do you know
    - search memory
    - past conversations
    - history
  patterns:
    - "do you remember"
    - "what did we talk about"
    - "search for"
    - "find information about"
  intents:
    - memory_search
    - recall_information
    - context_retrieval
tools:
  - memory_search
  - memory_get
  - memory_stats
required_providers: []
security:
  approval_required: false
  admin_only: false
eligibility:
  os: []
  binaries: []
  config_flags: []
  required_providers: []
metadata:
  author: system
  category: utility
  priority: high
---

# Memory Recall Skill

This skill enables the agent to search and retrieve information from its memory system.
Use this when the user asks about past conversations, stored information, or wants to
find specific knowledge from the agent's memory.

## Overview

The memory system uses hybrid search combining:
- **Vector search**: Semantic similarity using embeddings
- **Text search**: Keyword matching using BM25

This allows finding relevant information even when the exact words don't match.

## When to Use

Use this skill when:
- User asks "do you remember..."
- User wants information from past conversations
- User asks to search for specific topics
- User needs context from previous interactions

## Steps

1. **Identify the search intent**: Understand what information the user is looking for
2. **Formulate search query**: Extract key terms and concepts from the user's request
3. **Search memory**: Use `memory_search` with appropriate query
4. **Present results**: Show relevant snippets with source information
5. **Offer to retrieve full content**: If user wants more detail, use `memory_get`

## Tools

### memory_search
Search the memory for relevant information.
```
memory_search(query="search terms", max_results=5, source="memory")
```

### memory_get
Get the complete content of a specific memory file.
```
memory_get(path="memory/topic.md")
```

### memory_stats
Get statistics about the memory index.
```
memory_stats()
```

## Guidelines

- Start with broad searches, then narrow down if needed
- Present results clearly with source attribution
- Offer to show more context if the snippet is not enough
- Be transparent when no relevant information is found
- Consider multiple search strategies for complex queries

## Examples

### Example 1: Simple recall
User: "Do you remember what we discussed about Python?"
Agent: *Uses memory_search with query "Python discussion"*

### Example 2: Specific topic
User: "What do you know about the project architecture?"
Agent: *Uses memory_search with query "project architecture"*

### Example 3: Full content retrieval
User: "Show me the full document about API design"
Agent: *Uses memory_get with the path from search results*

## Notes

- Memory is automatically indexed from configured paths
- Search results include relevance scores
- Both semantic and keyword matching are used
- Session history can also be searched if configured
