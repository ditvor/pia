# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [0.1.0] — 2026-03-12

### Added
- ACP server with stdio transport for JetBrains IDE integration
- YouTrack REST client: fetch issue, search issues, get sprint
- Local codebase scanner with keyword-based file relevance ranking
- LLM synthesis via Anthropic Claude and OpenAI
- Context assembler with per-section token budgets
- CLI commands: `pia serve`, `pia config`, `pia test-connection`
- Pydantic settings with YAML file + environment variable layering
- Full offline test suite: unit tests + end-to-end integration test
