# PIA — Product Context Graph for Engineering Teams

PIA builds a persistent **Product Context Graph** inside your JetBrains IDE — connecting customer feedback, YouTrack tickets, your codebase, and shipped outcomes into a single queryable intelligence layer. Engineers understand *why* before they write a line of code. PMs prioritize with data, not gut feel. The graph compounds with every sprint.

**Website:** [pia-alpha.netlify.app](https://pia-alpha.netlify.app)

---

## The problem: context failures are the real bottleneck

Engineering teams have solved the code understanding problem. Claude Code, Copilot, and Cursor can explain any function, trace any call stack, and suggest any refactor. That layer is rich and getting richer.

The layer below it — *product* context — remains broken.

- *Why are we building this?* — An engineer picks up a ticket with no idea which customers asked for it, what they actually said, or how much revenue is at risk if it slips.
- *How hard is this?* — A PM writes a spec without knowing whether it's a two-day fix or a three-month rewrite, because that knowledge lives in the engineers' heads.
- *Did it even work?* — A feature ships. Nobody checks whether helpdesk volume dropped, whether the customers who asked for it started using it, or whether the error rate changed.

These are not process failures. They are context failures — structural gaps between the systems where product decisions are made (YouTrack, Intercom, Slack) and the place where those decisions get executed (the IDE).

Coding agents cannot solve context failures. They have no durable awareness of the product decisions being made around the code. Every session starts cold. They cannot tell you which customers filed helpdesk tickets about a feature, what those customers are worth, or what the PM said when they triaged the bug six months ago. They were not built to hold that kind of memory.

PIA was.

---

## What the Product Context Graph is

The Product Context Graph is a persistent, structured store of everything that matters about the product — not as prose in a wiki, but as a queryable graph of typed relationships:

```
Customer ──requested──▶ Ticket ──touches──▶ Code Area
    │                      │                     │
    │                      ▼                     ▼
    └──paid──▶ ARR    Linked Issues         Change History
                           │
                           ▼
                    Helpdesk Threads
```

Each node is enriched from a real data source: YouTrack for tickets and sprints, Intercom and YouTrack Helpdesk for customer feedback, Sentry and Amplitude for post-ship outcomes, your local codebase for technical context. The graph persists across sessions. It grows more useful the longer a team uses it.

The LLM is not the product. The graph is. The LLM is the interface that makes the graph queryable in plain language.

**Who it's for:**
- Engineers who want the business context behind a ticket without pinging the PM
- PMs who want to make prioritization decisions grounded in technical complexity and customer data
- Tech leads who want sprint plans scored by ARR impact and implementation risk, not whoever argued loudest in the planning call

---

## What's available today — Phase 1

PIA is being built incrementally. Phase 1 is live, tested, and in the ACP Registry.

Type a YouTrack ticket ID anywhere in the IDE chat (e.g. `PROJ-4521`) and PIA will:

1. Fetch the full ticket from YouTrack — summary, description, comments, linked issues, tags
2. Scan your local codebase for files most relevant to the ticket using keyword matching
3. Assemble all context into a structured prompt and call the configured LLM
4. Return a markdown response covering business context, technical context, linked issues, and suggested code entry points

Every enrichment writes structured data to a local SQLite store. The graph starts forming from day one.

---

## Requirements

- Python 3.10+
- A YouTrack instance with a permanent API token
- An Anthropic API key (or OpenAI as an alternative)
- JetBrains IDE with ACP plugin support

---

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

---

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

---

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

---

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
    store.py        — SQLite persistence layer; the foundation of the graph
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

---

## Running tests

```bash
pytest          # full suite
pytest -xvs     # stop on first failure, verbose
```

All tests run offline. No real API calls are made — YouTrack responses are served by `httpx.MockTransport` and LLM calls use a deterministic stub.

---

## How the Phase 1 pipeline works

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
          ├─ LLMClient.complete()          ← Anthropic / OpenAI
          │    │
          │    ▼
          │  Markdown response
          │
          └─ graph/store.py               ← persisted to local SQLite
               Ticket node, code area links, and issue relationships
               written to graph.db for use in future phases
```

---

## Roadmap

Each phase adds a new layer to the graph. The agent ships and works after every phase — the intelligence grows incrementally.

| Phase | Status | What it adds to the graph |
|-------|--------|--------------------------|
| 1 — YouTrack enricher | **Live** | Ticket nodes, codebase links, issue relationships |
| 2 — Codebase awareness | Planned | LLM-powered ticket-to-code linking; module boundaries, change history, ownership |
| 3 — Customer feedback | Planned | Customer nodes from YouTrack Helpdesk and Intercom; ARR linked to every ticket |
| 4 — Full graph assembly | Planned | Persistent cross-source graph: customers → feedback → tickets → code → outcomes |
| 5 — Intelligence layer | Planned | "What should we build next?" — sprint prioritization scored by ARR impact, feedback volume, and implementation risk |

---

## FAQ

### How is this different from Claude Code or any other coding agent?

Coding agents are excellent at explaining code — what a function does, how to fix a bug, where a feature is implemented. But they have no durable awareness of the product decisions being made around that code.

Ask Claude Code "why is this ticket important?" and it has no way to answer unless you paste the context in. It cannot look up which customers filed helpdesk requests for this feature, what those customers are worth, or what the PM said when they triaged the bug six months ago. It also has no memory between sessions — every conversation starts cold.

PIA's moat is not the LLM. It's the graph. A persistent, structured store of product context that survives across sessions, grows more complete over time, and connects decisions to outcomes. Coding agents explain the code. PIA explains the product decisions living around the code.

### What does this save — concretely?

**Meeting overhead:** A typical engineer spends 30–60 minutes per sprint chasing context for ambiguous tickets — Slack threads, quick syncs, re-reading old discussions. PIA collapses that to a single in-IDE query.

**Mis-prioritization:** The more expensive problem. Teams routinely spend weeks building features that were loud in Slack but only requested by a handful of low-value accounts, while high-ARR customers wait for critical fixes. In Phase 5, PIA scores every open ticket against the ARR of customers who requested it, the volume of feedback, and the complexity of the implementation — giving PMs a defensible, data-backed rationale for each sprint.

### Why is this a dedicated agent and not a YouTrack plugin or a custom MCP server?

Three reasons:

1. **It lives where engineers work.** A YouTrack plugin lives in YouTrack. Engineers live in their IDE. PIA puts product context next to the code, not next to the project management tool.
2. **It synthesizes across sources.** YouTrack, Intercom, Sentry, and Amplitude are four separate systems. A plugin in any one of them can only see that system's data. PIA pulls across all of them and synthesizes a single answer via the graph.
3. **ACP is the right protocol.** The Agent Communication Protocol is how JetBrains IDEs connect to external intelligence. Building on ACP means one-click install for any JetBrains user without custom tooling or API keys scattered across team machines.

### Is this production-ready?

Phase 1 is functional and tested. The ticket enrichment pipeline — YouTrack fetch, codebase scan, LLM synthesis — is solid. The graph persistence layer is live and writing data that future phases will build on.

Phases 2–5 are planned with skeleton code in the repository. If you are evaluating PIA today, Phase 1 delivers immediate value while the broader intelligence layer is under active development.

---

## License

Apache-2.0
