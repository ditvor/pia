# PIA — Product Intelligence Agent

## What this project IS
An ACP-compatible Python agent that runs inside JetBrains IDEs.
It enriches YouTrack tickets with codebase context and customer intelligence.
It is NOT a coding agent — it never writes or modifies code. It only reads.

## Tech stack
- Python 3.11+, async throughout (httpx, not requests)
- ACP Python SDK (agentclientprotocol/python-sdk)
- SQLite for storage, SQLAlchemy for models
- Anthropic Claude API for LLM calls
- Click for CLI, Pydantic for config/validation
- pytest for testing

## Project structure
src/pia/agent/     — ACP server and message routing
src/pia/sources/   — Data connectors (youtrack.py, codebase.py)
src/pia/graph/     — Product Context Graph (SQLite models, storage)
src/pia/llm/       — LLM client and prompt templates
src/pia/config/    — Pydantic settings
tests/             — pytest tests with fixtures/ for mock data

## Code conventions
- All API clients are async classes using httpx.AsyncClient
- Type hints on all functions and return types
- Docstrings on all public functions (Google style)
- Errors: raise typed exceptions, never return None for errors
- Prompts: all LLM prompts are string constants in llm/prompts.py
- Config: all settings via Pydantic BaseSettings with env var support
- Never use print() — use logging module

## Testing
- pytest with pytest-asyncio for async tests
- Mock HTTP responses with httpx mock, never call real APIs in tests
- Test fixtures in fixtures/ directory (JSON responses, sample data)
- Run: pytest -xvs

## Current phase: Phase 1 (YouTrack ticket enricher)
- Focus ONLY on: ACP server + YouTrack client + basic code scanner + LLM synthesis
- Do NOT build: graph database, external integrations, intelligence layer
- Keep it simple: keyword matching for code areas, not embeddings