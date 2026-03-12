# PIA — Product Intelligence Agent

PIA is an ACP-compatible Python agent that runs inside JetBrains IDEs. It connects your YouTrack project management to your local codebase, using Claude to turn a raw ticket ID into a rich, actionable summary — without you having to leave the IDE.

## What it does

Type a YouTrack ticket ID anywhere in the IDE chat (e.g. `PROJ-4521`) and PIA will:

1. Fetch the full ticket from YouTrack — summary, description, comments, linked issues, tags
2. Scan your local codebase for files most relevant to the ticket using keyword matching
3. Assemble all context into a structured prompt and call the configured LLM
4. Return a markdown response covering business context, technical context, linked issues, and suggested code entry points

Any other message returns a capability overview.

## Requirements

- Python 3.10+
- A YouTrack instance with a permanent API token
- An Anthropic API key (or OpenAI as an alternative)
- JetBrains IDE with ACP plugin support

## Installation

```bash
git clone <repo>
cd pia
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

For development (includes pytest):

```bash
pip install -e ".[dev]"
```

## Configuration

PIA resolves configuration from three sources in priority order:

1. Environment variables (highest priority)
2. YAML file at `~/.pia/config.yaml`
3. Built-in defaults

### Minimal environment variable setup

```bash
export YOUTRACK_URL=https://yourcompany.youtrack.cloud
export YOUTRACK_TOKEN=perm:...
export ANTHROPIC_API_KEY=sk-ant-...
```

### YAML config file

```yaml
# ~/.pia/config.yaml

youtrack:
  url: https://yourcompany.youtrack.cloud
  token: perm:...
  projects:
    - PROJ
    - HD

llm:
  provider: anthropic          # or "openai"
  api_key: sk-ant-...
  model: claude-sonnet-4-6    # default
  temperature: 0.1
  max_tokens: 4096

codebase:
  root: /path/to/your/project  # defaults to current working directory
  exclude_patterns:
    - node_modules/
    - .venv/
    - dist/
  git_history_days: 90

database:
  path: ~/.pia/graph.db
```

YAML values may reference environment variables using `${VARNAME}` syntax.

### Full list of environment variables

| Variable | Purpose |
|---|---|
| `YOUTRACK_URL` | YouTrack base URL |
| `YOUTRACK_TOKEN` | Permanent API token |
| `YOUTRACK_PROJECTS` | Comma-separated project keys |
| `YOUTRACK_SYNC_INTERVAL` | Sync interval in seconds (0 = manual) |
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `OPENAI_API_KEY` | OpenAI API key (when provider is openai) |
| `LLM_API_KEY` | Generic key override (takes precedence over provider-specific) |
| `LLM_PROVIDER` | `anthropic` or `openai` |
| `LLM_MODEL` | Model name |
| `LLM_MAX_TOKENS` | Maximum tokens in LLM response |
| `LLM_TEMPERATURE` | Sampling temperature (0.0–1.0) |
| `CODEBASE_ROOT` | Absolute path to your project root |
| `CODEBASE_GIT_HISTORY_DAYS` | How many days of git history to consider |
| `PIA_DATABASE_PATH` | Path to the SQLite database |

## CLI

```bash
# Verify YouTrack and LLM connections
pia test-connection

# Show the current resolved configuration (secrets masked)
pia config

# Start the ACP agent server on stdio (used by the JetBrains plugin)
pia serve

# Use a custom config file
pia config --config-file /path/to/config.yaml
pia serve --config-file /path/to/config.yaml   # via env: FASTMCP_CONFIG
```

## Project structure

```
src/pia/
  agent/
    router.py       — Detects ticket IDs, dispatches to handlers, returns markdown
    server.py       — ACP server factory; registers the PIA agent over stdio
  sources/
    youtrack.py     — Async YouTrack REST client (get_issue, search_issues, get_sprint)
    codebase.py     — Local file tree scanner and keyword-based relevance ranker
  llm/
    client.py       — Thin async wrapper for Anthropic and OpenAI APIs
    prompts.py      — All LLM prompt templates as string constants
    context.py      — Assembles YTIssue + CodeMatch data into a filled prompt
  graph/
    models.py       — Shared dataclasses (YTIssue, CodeMatch, YTIssueLink, …)
    store.py        — SQLite persistence layer (future phases)
  config/
    settings.py     — Pydantic settings with YAML + env var layering
    defaults.py     — All default values as documented constants
  cli.py            — Click entry point: serve / config / test-connection

tests/
  test_agent/       — Router and server unit tests
  test_sources/     — YouTrack client and codebase scanner tests
  test_llm/         — LLM client tests (httpx-mocked, no real API calls)
  test_config/      — Settings loader and validator tests
  test_integration.py — End-to-end pipeline test (mock HTTP + real scanner + real assembler)
  fixtures/
    youtrack_responses/  — Realistic YouTrack API JSON fixtures
    sample_codebase/     — Small Python project used by scanner and integration tests
```

## Running tests

```bash
pytest          # full suite
pytest -xvs     # stop on first failure, verbose
```

All tests run offline. No real API calls are made — YouTrack responses are served by `httpx.MockTransport` and LLM calls use a deterministic stub.

## How the pipeline works

```
User message
     │
     ▼
MessageRouter.route()
     │
     ├─ No ticket ID → return capability overview
     │
     └─ Ticket ID found (e.g. PROJ-4521)
          │
          ├─ YouTrackClient.get_issue()    ← YouTrack REST API
          │
          ├─ scan_project() + find_relevant_files()  ← local filesystem
          │
          ├─ ContextAssembler.assemble_ticket_enrichment()
          │    Serialises issue + code matches into a structured prompt,
          │    respecting per-section token budgets (40% ticket / 20% links / 30% code)
          │
          └─ LLMClient.complete()          ← Anthropic / OpenAI
               │
               ▼
          Markdown response
```

## License

Apache-2.0
