# PIA — Product Intelligence Agent

PIA is an ACP-compatible Python agent that runs inside JetBrains IDEs. It connects your YouTrack project management to your local codebase, using Claude to turn a raw ticket ID into a rich, actionable summary — without you having to leave the IDE.

**Website:** [pia-alpha.netlify.app](https://pia-alpha.netlify.app)

## Why PIA exists

Engineering teams already have Claude Code, Copilot, and a dozen other coding agents. None of them answer the questions that actually slow teams down:

- *Why are we building this?* — An engineer picks up a ticket and has no idea which customers asked for it, what they actually said, or how much revenue is at risk if it slips.
- *How hard is this?* — A PM writes a spec without knowing whether it's a two-day fix or a three-month rewrite.
- *Did it even work?* — A feature ships and nobody checks whether helpdesk volume dropped, error rates changed, or the customers who asked for it actually started using it.

PIA is not a coding agent. It does not write, review, or explain code. It connects the product decisions being made in YouTrack to the codebase where those decisions get executed — and surfaces the context that would otherwise require three Slack threads and a meeting.

**Who it's for:**
- Engineers who want the business context behind a ticket without pinging the PM
- PMs who want to make prioritization decisions grounded in technical complexity
- Tech leads who want sprint plans based on customer data, not whoever argued loudest in the planning call

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

## Roadmap

Each phase ships as a working, installable ACP agent. The plan is to grow the product incrementally rather than wait for a complete build.

| Phase | Status | What it delivers |
|-------|--------|-----------------|
| 1 — YouTrack enricher | **Current** | Type a ticket ID, get a rich summary with codebase context and linked issues |
| 2 — Codebase awareness | Planned | LLM-powered ticket-to-code linking; understands module boundaries and change history |
| 3 — Customer feedback | Planned | Connects YouTrack Helpdesk and Intercom to tickets; every ticket shows which customers asked for it and their ARR |
| 4 — Product Context Graph | Planned | Persistent SQLite graph linking customers, feedback, features, code areas, and metrics |
| 5 — Intelligence layer | Planned | "What should we build next?" — data-driven prioritization, post-ship impact tracking, sprint planning with revenue context |

## FAQ

### Why can't I just use Claude Code (or any other coding agent) for this?

Claude Code and similar agents are excellent at answering questions about code — what a function does, how to fix a bug, where a feature is implemented. But they have no durable awareness of the product decisions being made around that code.

When you ask Claude Code "why is this feature important?", it has no way to know unless that context happens to be in a comment or doc you paste in. It can't look up which customers filed helpdesk tickets requesting it, what those customers are worth, whether a competitor just shipped the same thing, or what the PM said when they triaged the bug six months ago. It also has no memory between sessions — every conversation starts cold.

PIA maintains persistent, structured product context. It actively connects YouTrack, Intercom, Sentry, and Amplitude into a single graph that survives across conversations. The value is not the LLM — it's the wiring.

### What's the customer value? How does this save money or time?

The two biggest costs PIA targets are meeting overhead and mis-prioritization.

**Meeting overhead**: A typical engineer spends 30–60 minutes per sprint chasing context for ambiguous tickets — Slack threads with PMs, quick syncs, re-reading old discussions. PIA collapses that to a single in-IDE query with a structured answer.

**Mis-prioritization**: The more expensive problem. Teams regularly spend weeks building features that were loud on Slack but only requested by a handful of low-value accounts, while high-ARR customers wait months for critical fixes. In Phase 5, PIA scores every open ticket against the ARR of customers who requested it, the volume of feedback, and the complexity of the implementation — giving PMs a defensible, data-backed rationale for what goes into each sprint.

### Why is this a dedicated agent and not a YouTrack plugin or a custom MCP server?

Three reasons:

1. **It lives where engineers work.** A YouTrack plugin lives in YouTrack. Engineers live in their IDE. PIA puts product context next to the code, not next to the project management tool.
2. **It synthesizes across sources.** YouTrack, Intercom, Sentry, and Amplitude are four separate systems. A plugin in any one of them can only see that system's data. PIA pulls across all of them and synthesizes a single answer.
3. **ACP is the right protocol.** The Agent Communication Protocol is how JetBrains IDEs connect to external intelligence. Building on ACP means one-click install for any JetBrains user without custom tooling or API keys scattered across team machines.

### Is this production-ready?

Phase 1 is functional and tested. Phases 2–5 are planned and have skeleton code in the repository. If you're evaluating PIA for production use today, the Phase 1 capability — ticket enrichment with codebase context — is solid. The broader intelligence features are under active development.

## License

Apache-2.0
