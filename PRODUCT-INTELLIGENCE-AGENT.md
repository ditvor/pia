# Product Intelligence Agent (PIA)

## ACP-Native Product Intelligence for the JetBrains Ecosystem

> **Document purpose**: This is the master specification for building an ACP-compatible AI agent that brings product management intelligence into JetBrains IDEs. It is designed to be fed directly to Claude Code as the primary reference for implementation. Every section includes explicit technical decisions, file structures, and code patterns to minimize ambiguity.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Problem Statement](#2-problem-statement)
3. [Solution Architecture](#3-solution-architecture)
4. [Core Concepts](#4-core-concepts)
5. [Technical Stack](#5-technical-stack)
6. [Project Structure](#6-project-structure)
7. [Implementation Phases](#7-implementation-phases)
8. [Phase 1: Foundation — YouTrack Ticket Enricher](#8-phase-1-foundation--youtrack-ticket-enricher)
9. [Phase 2: Codebase Awareness](#9-phase-2-codebase-awareness)
10. [Phase 3: Customer Feedback Integration](#10-phase-3-customer-feedback-integration)
11. [Phase 4: Product Context Graph](#11-phase-4-product-context-graph)
12. [Phase 5: Intelligence Layer](#12-phase-5-intelligence-layer)
13. [ACP Agent Implementation Details](#13-acp-agent-implementation-details)
14. [YouTrack MCP Integration](#14-youtrack-mcp-integration)
15. [LLM Integration](#15-llm-integration)
16. [Data Model](#16-data-model)
17. [User Interactions & Commands](#17-user-interactions--commands)
18. [Configuration](#18-configuration)
19. [Testing Strategy](#19-testing-strategy)
20. [Publishing to ACP Registry](#20-publishing-to-acp-registry)
21. [Competitive Landscape](#21-competitive-landscape)
22. [Design Principles](#22-design-principles)
23. [Appendix: Research & References](#23-appendix-research--references)

---

## 1. Project Overview

### What is PIA?

Product Intelligence Agent (PIA) is a Python-based ACP-compatible AI agent that lives inside JetBrains IDEs (IntelliJ IDEA, PyCharm, WebStorm, etc.) and provides product management intelligence to both engineers and PMs. It connects to YouTrack (via MCP), the codebase (via IDE file access), and optionally external tools (Intercom, Sentry, Amplitude) to build a Product Context Graph — a connected knowledge structure that links customers, feedback, features, metrics, code, and technical components.

### What makes it unique?

Every agent in the ACP registry today is a **coding agent** — they write, debug, refactor, and explain code. PIA is the **first non-coding agent** in the ACP ecosystem. Instead of helping engineers write code, it helps teams decide **what code to write and why**.

### Who is it for?

- **Engineers** who want to understand the business context behind a ticket without attending meetings or pinging PMs on Slack
- **PMs** who want to make evidence-backed prioritization decisions grounded in actual codebase complexity
- **Tech leads** who want to understand the impact of what they shipped and plan sprints based on data, not politics

### One-sentence pitch

"PIA gives engineers the 'why' behind every ticket and gives PMs the 'how hard' behind every feature — all inside the IDE."

---

## 2. Problem Statement

### The gap in the JetBrains ecosystem

JetBrains owns both sides of the software building process:

- **The IDE** (IntelliJ, PyCharm, WebStorm) — where engineers write code
- **YouTrack** — where PMs track issues, plan sprints, manage backlogs, run helpdesk
- **ACP/MCP** — open protocols connecting external tools to both

But **no intelligence connects these two worlds**. Today:

- A PM creates a ticket in YouTrack. An engineer opens it in their IDE. They build it. They close it. That's the entire feedback loop.
- No system understands the relationship between what customers need, what PMs prioritize, what engineers build, and what actually happens after shipping.
- Engineers lack customer context. PMs lack technical complexity context. Nobody tracks impact after shipping.

### What JetBrains has built (and what it can't do)

| Tool | What it does | What it CAN'T do |
|------|-------------|------------------|
| YouTrack AI Assistant | Summarizes individual tickets, writing assistance, reply suggestions | Can't connect tickets to revenue, customer value, or codebase complexity |
| YouTrack MCP Server | Exposes project data (tickets, sprints, users) to external tools | Raw data pipe — no intelligence on top |
| JetBrains Console | Tracks AI usage and costs across teams | Tracks tool usage, not product decisions |
| ACP Agent Registry | One-click install of coding agents (Claude Code, Codex, Cursor, etc.) | Every agent is a coding agent — zero product intelligence agents exist |
| YouTrack Helpdesk | Customer support ticket management | Helpdesk tickets are disconnected from engineering tickets and codebase |

### The specific pain points PIA solves

1. **Engineer picks up ticket, has no context**: "Why are we building this? Who wants it? How important is it?" → Currently requires Slack ping to PM or reading scattered docs
2. **PM prioritizes features without knowing complexity**: "Is this a 2-day task or a 6-month rewrite?" → Currently requires meeting with engineering
3. **Nobody tracks impact after shipping**: "Did the feature we shipped actually solve the problem?" → Currently requires manual analysis across multiple tools
4. **Sprint planning is politics, not data**: "What's the highest-impact combination of work for next sprint?" → Currently decided by whoever argues loudest
5. **Evidence is scattered**: Customer quotes in Intercom, metrics in Amplitude, tickets in YouTrack, code in the repo — no single system connects them

---

## 3. Solution Architecture

### High-level architecture diagram

```
┌─────────────────────────────────────────────────────┐
│              Product Intelligence Agent (PIA)         │
│                                                       │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────┐ │
│  │ ACP Server   │  │ Query Engine │  │ LLM Client  │ │
│  │ (speaks ACP  │  │ (processes   │  │ (Anthropic/  │ │
│  │  protocol)   │  │  user asks)  │  │  OpenAI API) │ │
│  └──────┬───────┘  └──────┬───────┘  └──────┬──────┘ │
│         │                 │                  │        │
│  ┌──────▼─────────────────▼──────────────────▼──────┐ │
│  │           Product Context Graph (SQLite)          │ │
│  │                                                    │ │
│  │  tickets ←→ customers ←→ feedback ←→ code_areas   │ │
│  │  metrics ←→ sprints ←→ components ←→ competitors  │ │
│  └──────────────────────┬────────────────────────────┘ │
│                         │                              │
└─────────────────────────┼──────────────────────────────┘
                          │
           ┌──────────────┼──────────────┐
           │              │              │
     ┌─────▼─────┐ ┌─────▼─────┐ ┌─────▼──────┐
     │  YouTrack  │ │ Codebase  │ │  External  │
     │  MCP/REST  │ │  (files)  │ │  Sources   │
     │            │ │           │ │            │
     │ • Tickets  │ │ • Source  │ │ • Intercom │
     │ • Sprints  │ │ • Git log │ │ • Sentry   │
     │ • Helpdesk │ │ • Tests   │ │ • Amplitude│
     │ • KB       │ │ • Deps    │ │ • Slack    │
     └────────────┘ └───────────┘ └────────────┘
```

### How data flows

1. **Ingestion**: PIA periodically syncs data from YouTrack (tickets, sprints, helpdesk), scans the codebase (file structure, git history), and optionally pulls from external sources
2. **Graph construction**: Ingested data is processed into the Product Context Graph — entities are created, relationships are inferred (e.g., a helpdesk ticket mentioning "export" is linked to the YouTrack ticket about CSV export)
3. **Query processing**: When a user asks a question in the IDE's AI Chat, PIA retrieves relevant subgraph from the Product Context Graph
4. **LLM synthesis**: The retrieved context is sent to an LLM (Claude or GPT) with a structured prompt, and the response is returned to the user

---

## 4. Core Concepts

### Product Context Graph

The central data structure of PIA. It's a graph of entities (nodes) and relationships (edges) that represents everything known about the product.

**Node types:**

| Node Type | Description | Data Source |
|-----------|-------------|-------------|
| `customer` | A user, account, or organization | YouTrack Helpdesk, CRM, manual |
| `ticket` | A YouTrack issue (bug, feature request, task) | YouTrack REST API / MCP |
| `feedback` | A customer comment, support request, or interview quote | YouTrack Helpdesk, Intercom |
| `feature` | A product capability (shipped or planned) | YouTrack tags/labels, manual |
| `code_area` | A module, package, or file path in the codebase | Codebase scanning |
| `metric` | A business or product metric (retention, NPS, etc.) | Amplitude, manual |
| `sprint` | A YouTrack sprint or agile board | YouTrack REST API / MCP |
| `competitor` | A competitor product or feature | Manual, feedback mentions |

**Edge types (relationships):**

| Edge | From → To | Description |
|------|-----------|-------------|
| `requested` | customer → ticket | Customer requested this feature |
| `reported` | customer → feedback | Customer submitted this feedback |
| `maps_to` | feedback → ticket | This feedback maps to this ticket |
| `implements` | ticket → feature | This ticket implements this feature |
| `touches` | ticket → code_area | This ticket modifies this code area |
| `depends_on` | ticket → code_area | This ticket depends on this component |
| `affects` | feature → metric | This feature affects this metric |
| `planned_in` | ticket → sprint | This ticket is planned in this sprint |
| `competes_with` | competitor → feature | Competitor has shipped this feature |
| `mentioned_by` | competitor → feedback | Competitor was mentioned in this feedback |

### Evidence Chains

An evidence chain is a traceable path through the Product Context Graph from an assertion back to raw data. Every claim PIA makes should be backed by a chain.

Example:
```
Claim: "Users struggle with data export"
  → 17 helpdesk tickets mentioning "export" (last 90 days)
    → 3 enterprise customers (Acme $120K, BigRetail $85K, StartupZ $8K)
  → Sentry: 23 timeout errors in services/export/ (past month)
  → Competitor A shipped CSV export on Feb 12
  → Estimated effort: 5 story points (based on code_area complexity)
```

### Impact Tracking

After a ticket is marked as done in YouTrack, PIA monitors:
- Did related helpdesk ticket volume decrease?
- Did the target metric move?
- Did new Sentry errors appear in the changed code paths?
- Did requesting customers increase usage?

---

## 5. Technical Stack

### Core

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| Language | Python 3.11+ | Developer familiarity, ACP Python SDK exists |
| ACP SDK | `agentclientprotocol/python-sdk` | Official ACP Python SDK for agent development |
| Database | SQLite | Zero-config, embedded, sufficient for single-team scale |
| LLM | Anthropic Claude API (primary), OpenAI as fallback | Best for structured reasoning tasks |
| HTTP Client | `httpx` | Async support, clean API for YouTrack REST calls |
| CLI Framework | `click` | For the agent's CLI entry point |

### Data & Search

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| Vector search | `sqlite-vec` or `chromadb` (local) | For semantic search over tickets/feedback |
| Embeddings | Sentence-transformers (local) or API-based | For vectorizing text content |
| Text search | SQLite FTS5 | For keyword search fallback |

### External Integrations (Phase 3+)

| Service | Integration Method | Data Retrieved |
|---------|-------------------|----------------|
| YouTrack | REST API + MCP Server | Tickets, sprints, helpdesk, KB articles, users |
| Codebase | Local file system (ACP gives access) | File tree, file contents, git log |
| Intercom | REST API | Conversations, contacts, tags |
| Sentry | REST API | Error events, issue frequency, affected files |
| Amplitude | REST API | Event counts, funnel metrics, cohort data |

---

## 6. Project Structure

```
product-intelligence-agent/
├── README.md
├── pyproject.toml                 # Package config, dependencies, entry points
├── LICENSE                        # Apache 2.0 (matches ACP ecosystem)
├── acp-registry.json              # ACP registry metadata for publishing
│
├── src/
│   └── pia/
│       ├── __init__.py
│       ├── __main__.py            # Entry point: `python -m pia`
│       ├── cli.py                 # Click CLI: `pia serve`, `pia sync`, `pia config`
│       │
│       ├── agent/                 # ACP agent implementation
│       │   ├── __init__.py
│       │   ├── server.py          # ACP server — handles protocol handshake, message routing
│       │   ├── router.py          # Routes user messages to appropriate handlers
│       │   └── auth.py            # Authentication (terminal auth for ACP registry)
│       │
│       ├── sources/               # Data source connectors
│       │   ├── __init__.py
│       │   ├── youtrack.py        # YouTrack REST API client
│       │   ├── youtrack_mcp.py    # YouTrack MCP server client (if using MCP)
│       │   ├── codebase.py        # Local codebase scanner (file tree, git log, grep)
│       │   ├── intercom.py        # Intercom API client (Phase 3)
│       │   ├── sentry.py          # Sentry API client (Phase 3)
│       │   └── amplitude.py       # Amplitude API client (Phase 3)
│       │
│       ├── graph/                 # Product Context Graph
│       │   ├── __init__.py
│       │   ├── models.py          # SQLAlchemy/dataclass models for nodes and edges
│       │   ├── store.py           # SQLite graph storage and query layer
│       │   ├── linker.py          # Infers relationships between entities
│       │   └── sync.py            # Orchestrates data sync from all sources into graph
│       │
│       ├── intelligence/          # Intelligence layer (Phase 4-5)
│       │   ├── __init__.py
│       │   ├── prioritizer.py     # "What should we build next?" logic
│       │   ├── impact_tracker.py  # Post-ship impact monitoring
│       │   ├── evidence.py        # Evidence chain construction
│       │   └── sprint_planner.py  # Sprint planning optimization
│       │
│       ├── llm/                   # LLM integration
│       │   ├── __init__.py
│       │   ├── client.py          # Anthropic/OpenAI client wrapper
│       │   ├── prompts.py         # All prompt templates (centralized)
│       │   └── context.py         # Context assembly — builds LLM prompts from graph data
│       │
│       └── config/                # Configuration
│           ├── __init__.py
│           ├── settings.py        # Pydantic settings model
│           └── defaults.py        # Default configuration values
│
├── tests/
│   ├── conftest.py                # Shared fixtures (mock YouTrack, test DB, etc.)
│   ├── test_agent/                # ACP protocol tests
│   ├── test_sources/              # Data source connector tests
│   ├── test_graph/                # Graph storage and linking tests
│   ├── test_intelligence/         # Intelligence layer tests
│   └── test_llm/                  # LLM integration tests (with mocked API)
│
├── fixtures/                      # Test data
│   ├── youtrack_responses/        # Sample YouTrack API responses (JSON)
│   ├── sample_codebase/           # Minimal codebase for testing code analysis
│   └── sample_graph.db            # Pre-populated test graph
│
└── docs/
    ├── architecture.md            # Detailed architecture documentation
    ├── acp-integration.md         # How ACP protocol is implemented
    ├── youtrack-setup.md          # How to configure YouTrack connection
    └── adding-sources.md          # How to add new data source connectors
```

---

## 7. Implementation Phases

### Overview of all phases

| Phase | Name | Duration | Deliverable | Dependencies |
|-------|------|----------|-------------|--------------|
| 1 | Foundation | 2 weeks | ACP agent that enriches YouTrack tickets with basic codebase context | ACP Python SDK, YouTrack API |
| 2 | Codebase Awareness | 2 weeks | Smart ticket-to-code linking using LLM | Phase 1 + LLM API |
| 3 | Customer Feedback | 2 weeks | YouTrack Helpdesk + (optionally) Intercom integration | Phase 2 |
| 4 | Product Context Graph | 3 weeks | Full graph with evidence chains | Phase 3 |
| 5 | Intelligence Layer | 4 weeks | Prioritization, impact tracking, sprint planning | Phase 4 |

### Critical rule: Each phase must be independently shippable

Every phase produces a working, useful agent that can be published to the ACP registry. You should NOT wait until Phase 5 to ship. Phase 1 alone is valuable.

---

## 8. Phase 1: Foundation — YouTrack Ticket Enricher

### Goal

Build a minimal ACP agent that an engineer installs in their JetBrains IDE. They type a YouTrack ticket ID and get an enriched summary that includes basic codebase context.

### User interaction

```
User: Tell me about PROJ-4521

PIA: ## PROJ-4521: Add CSV Export to Reports

**Status**: Open | **Priority**: Critical | **Sprint**: Sprint 14
**Assignee**: @john | **Reporter**: @sarah (PM)
**Created**: 2 weeks ago | **Updated**: 3 days ago

### Summary
This ticket requests adding CSV export functionality to the reporting
module. It was created after 3 helpdesk tickets from enterprise
customers requesting this capability.

### Linked Issues
- PROJ-4400: API refactor (DONE ✓) — was previously blocking this
- PROJ-4389: PDF export (DONE ✓) — similar implementation, can reference
- HD-892, HD-901: Related helpdesk tickets

### Likely Code Areas
Based on the ticket description and linked issues, the relevant code
is likely in:
- `src/services/export/` — existing export module (PDF export lives here)
- `src/api/routes/reports.py` — report API endpoints
- `tests/test_export/` — existing export tests

### Comments (3)
- @sarah (PM, 2 weeks ago): "Acme Corp specifically asked for this..."
- @john (Eng, 1 week ago): "Should be straightforward now that API refactor is done"
- @sarah (PM, 3 days ago): "Can we target Sprint 14?"
```

### Implementation steps for Phase 1

#### Step 1: Set up the Python project

```bash
# Create project
mkdir product-intelligence-agent && cd product-intelligence-agent
python -m venv .venv && source .venv/bin/activate

# Install dependencies
pip install acp-sdk httpx click anthropic pydantic sqlite-utils
```

Create `pyproject.toml`:
```toml
[project]
name = "product-intelligence-agent"
version = "0.1.0"
description = "Product intelligence for JetBrains IDEs via ACP"
requires-python = ">=3.11"
dependencies = [
    "acp-sdk",
    "httpx",
    "click",
    "anthropic",
    "pydantic>=2.0",
    "sqlite-utils",
]

[project.scripts]
pia = "pia.cli:main"
```

#### Step 2: Implement the ACP server

The agent must implement the ACP protocol. The Python SDK provides the scaffolding. The core is:

1. **Handshake**: When the IDE connects, the agent returns its capabilities and auth method
2. **Message handling**: When the user sends a message in AI Chat, the agent receives it, processes it, and returns a response
3. **Tool access**: The agent can read files from the project (the IDE exposes this via ACP)

Key ACP concepts:
- The agent runs as a local process (CLI)
- The IDE starts the agent process and communicates via stdio or HTTP
- The agent receives the user's message and the current file context
- The agent returns a response (markdown text)

#### Step 3: Implement YouTrack REST API client

YouTrack REST API reference: `https://www.jetbrains.com/help/youtrack/devportal/youtrack-rest-api.html`

Key endpoints:
```
GET /api/issues/{id}?fields=summary,description,project,priority,state,assignee,reporter,created,updated,comments(text,author,created),links(direction,linkType,issues(idReadable,summary))
GET /api/issues?query={query}&fields=...
GET /api/agiles/{id}/sprints?fields=...
```

Authentication: Permanent token (Bearer token in header)

#### Step 4: Implement basic codebase scanning

For Phase 1, codebase awareness is simple:
- List the project's file tree (directories and filenames)
- Given keywords from a ticket, grep for matching files
- Return the top-N most relevant file paths

This does NOT require an LLM. Simple keyword matching is sufficient for Phase 1.

```python
# Pseudocode for basic code area detection
def find_relevant_code(ticket_summary: str, ticket_description: str, project_root: str) -> list[str]:
    """Find files that might be related to a ticket based on keyword matching."""
    keywords = extract_keywords(ticket_summary + " " + ticket_description)
    matches = []
    for filepath in walk_project(project_root):
        score = sum(1 for kw in keywords if kw.lower() in filepath.lower())
        if score > 0:
            matches.append((filepath, score))
    return sorted(matches, key=lambda x: x[1], reverse=True)[:10]
```

#### Step 5: Wire up LLM for synthesis

Take the raw data (ticket details, linked issues, code areas) and send it to an LLM to produce a coherent, useful summary.

```python
TICKET_ENRICHMENT_PROMPT = """
You are a product intelligence assistant inside a developer's IDE.
The developer asked about a YouTrack ticket. Your job is to give them
a rich, actionable summary that includes business context, technical
context, and anything they need to start working on it.

## Ticket Data
{ticket_json}

## Linked Issues
{linked_issues_json}

## Likely Related Code Areas
{code_areas}

## Instructions
- Lead with what the ticket is about and why it matters
- Show the current status, assignee, sprint
- Summarize the comments — highlight decisions and open questions
- List related/linked issues with their status
- Show the likely code areas and explain why they're relevant
- If there are helpdesk tickets linked, mention the customer context
- Keep it concise but complete — the developer should not need to
  open YouTrack to understand this ticket
- Use markdown formatting
"""
```

#### Step 6: Test locally

Before publishing, test the agent locally by adding it to your `~/.jetbrains/acp.json`:

```json
{
  "agent_servers": {
    "Product Intelligence": {
      "command": "/path/to/venv/bin/python",
      "args": ["-m", "pia", "serve"],
      "env": {
        "YOUTRACK_URL": "https://your-instance.youtrack.cloud",
        "YOUTRACK_TOKEN": "your-permanent-token",
        "ANTHROPIC_API_KEY": "your-api-key"
      }
    }
  }
}
```

Open any JetBrains IDE, go to AI Chat, select "Product Intelligence" from the agent picker, and test.

---

## 9. Phase 2: Codebase Awareness

### Goal

Replace keyword-based code matching with LLM-powered understanding. The agent should be able to:

- Given a ticket, identify which modules/files are likely affected
- Estimate rough complexity based on the code area's size, test coverage, and recent change frequency
- Show the engineer the entry point for the work

### New capabilities

1. **Git log analysis**: Parse `git log` to understand which files change together (co-change analysis), who owns which areas, and how recently code was modified
2. **LLM-based code matching**: Send the ticket description + file tree to the LLM and ask it to identify relevant code areas (much more accurate than keyword grep)
3. **Complexity estimation**: Count lines of code, number of dependencies, test coverage (if available), and recent bug fix frequency for each code area

### Implementation details

```python
# Git log parsing for co-change analysis
def get_file_change_history(project_root: str, days: int = 90) -> dict:
    """Parse git log to get file change frequency and co-change patterns."""
    result = subprocess.run(
        ["git", "log", f"--since={days} days ago", "--name-only", "--pretty=format:---"],
        cwd=project_root, capture_output=True, text=True
    )
    # Parse commits, track which files change together
    # Return: {filepath: {changes: int, last_modified: date, co_changes: [filepaths]}}
```

```python
# LLM-based code area identification
CODE_MATCHING_PROMPT = """
Given this YouTrack ticket and the project's file structure,
identify the most likely code areas that would need to be modified.

## Ticket
Title: {title}
Description: {description}

## Project File Tree
{file_tree}

## Recent Git Activity (files changed in last 30 days)
{recent_changes}

Respond with a JSON array of objects:
[
  {{"path": "src/services/export/", "confidence": "high", "reason": "Export module — ticket is about adding CSV export"}},
  ...
]
"""
```

---

## 10. Phase 3: Customer Feedback Integration

### Goal

Connect customer feedback to engineering work. When an engineer looks at a ticket, they see which customers requested it, what they said, and how valuable those customers are.

### Data sources

**YouTrack Helpdesk** (built-in, no additional integration needed):
- Helpdesk tickets are already in YouTrack
- They can be linked to regular project tickets
- PIA reads helpdesk tickets and extracts customer information

**Intercom** (optional, requires API key):
- Conversations with customers
- Customer attributes (plan, revenue, company)
- Tags and segments

### New capabilities

1. **Customer attribution**: Every ticket gets annotated with which customers requested it and their value (ARR, plan tier)
2. **Feedback aggregation**: Multiple pieces of feedback about the same topic are grouped and summarized
3. **Revenue-weighted prioritization**: Tickets are scored not just by count of requests but by total ARR at risk

### New user interaction

```
User: Who wants CSV export and why?

PIA: ## Customer Demand for CSV Export

### Requesting Customers (3)
| Customer | Plan | ARR | Signal |
|----------|------|-----|--------|
| Acme Corp | Enterprise | $120K | Support ticket HD-892: "We need to export data to our BI tool" |
| BigRetail | Enterprise | $85K | Helpdesk HD-901: "Evaluating competitors because of export limitations" |
| StartupZ | SMB | $8K | Feature request in HD-915 |

### Total ARR at Risk: $213K

### Key Quotes
- Acme (HD-892): "This is blocking our quarterly reporting workflow"
- BigRetail (HD-901): "CompetitorA just shipped CSV export last week"

### Competitor Context
- CompetitorA shipped CSV export on Feb 12, 2026
- BigRetail explicitly mentioned this as reason for evaluation

### Recommendation
High priority. $205K in enterprise ARR is at risk, competitor has
moved, and the technical blocker (API refactor) is resolved.
```

---

## 11. Phase 4: Product Context Graph

### Goal

Build the full graph database that connects all entities and relationships. Enable evidence chains — every claim traceable back to raw data.

### Graph implementation

Use SQLite with a simple relational schema (not a graph database — SQLite is simpler and sufficient at this scale).

```sql
-- Nodes
CREATE TABLE nodes (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,  -- 'customer', 'ticket', 'feedback', 'feature', 'code_area', 'metric', 'sprint', 'competitor'
    label TEXT NOT NULL,
    data JSON,           -- Type-specific attributes
    source TEXT,         -- Where this data came from
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Edges (relationships)
CREATE TABLE edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_id TEXT NOT NULL REFERENCES nodes(id),
    to_id TEXT NOT NULL REFERENCES nodes(id),
    type TEXT NOT NULL,   -- 'requested', 'maps_to', 'touches', 'affects', etc.
    weight REAL DEFAULT 1.0,  -- Strength/confidence of relationship
    data JSON,            -- Edge-specific attributes
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Full-text search index on node labels and data
CREATE VIRTUAL TABLE nodes_fts USING fts5(label, data, content=nodes, content_rowid=rowid);

-- Indexes for common queries
CREATE INDEX idx_edges_from ON edges(from_id, type);
CREATE INDEX idx_edges_to ON edges(to_id, type);
CREATE INDEX idx_nodes_type ON nodes(type);
```

### Evidence chain query

```python
def build_evidence_chain(claim: str, graph: GraphStore) -> EvidenceChain:
    """Build an evidence chain for a claim by traversing the graph."""
    # 1. Find the central node(s) related to the claim
    central_nodes = graph.search(claim)

    # 2. Traverse outward to find supporting evidence
    evidence = []
    for node in central_nodes:
        # Find connected feedback
        feedback = graph.get_connected(node.id, edge_type="maps_to", node_type="feedback")
        # Find connected customers
        customers = graph.get_connected(node.id, edge_type="requested", node_type="customer")
        # Find connected code areas
        code = graph.get_connected(node.id, edge_type="touches", node_type="code_area")
        # Find connected metrics
        metrics = graph.get_connected(node.id, edge_type="affects", node_type="metric")
        # Find competitor signals
        competitors = graph.get_connected(node.id, edge_type="competes_with", node_type="competitor")

        evidence.append(EvidenceNode(
            node=node,
            feedback=feedback,
            customers=customers,
            code=code,
            metrics=metrics,
            competitors=competitors,
        ))

    return EvidenceChain(claim=claim, evidence=evidence)
```

---

## 12. Phase 5: Intelligence Layer

### Goal

Transform PIA from a data retrieval tool into a decision support system. Add proactive intelligence, impact tracking, and sprint optimization.

### Capability 1: "What should we build next?"

```python
def prioritize_tickets(graph: GraphStore, sprint_capacity: int) -> list[PrioritizedTicket]:
    """Score and rank tickets by impact, considering constraints."""
    open_tickets = graph.get_nodes(type="ticket", status="open")

    scored = []
    for ticket in open_tickets:
        score = PriorityScore(
            customer_value=sum_customer_arr(graph, ticket),  # Total ARR of requesting customers
            request_count=count_feedback(graph, ticket),      # Number of feedback items
            competitive_pressure=check_competitor(graph, ticket),  # Did competitor ship this?
            code_complexity=estimate_complexity(graph, ticket),    # How hard to build?
            dependency_risk=check_blockers(graph, ticket),        # Are blockers resolved?
            strategic_alignment=check_okr_alignment(graph, ticket),  # Does it align with OKRs?
        )
        scored.append(PrioritizedTicket(ticket=ticket, score=score))

    return sorted(scored, key=lambda x: x.score.total, reverse=True)
```

### Capability 2: Impact tracking

After a ticket is closed, PIA starts a monitoring window (default 30 days):

```python
class ImpactTracker:
    def check_impact(self, ticket_id: str, days_since_ship: int) -> ImpactReport:
        """Check the impact of a shipped feature."""
        ticket = self.graph.get_node(ticket_id)
        ship_date = ticket.data["resolved_date"]

        return ImpactReport(
            helpdesk_trend=self.compare_helpdesk_volume(ticket, ship_date),
            error_trend=self.compare_sentry_errors(ticket, ship_date),
            metric_movement=self.check_metric_targets(ticket, ship_date),
            customer_response=self.check_customer_activity(ticket, ship_date),
        )
```

### Capability 3: Sprint planning

```
User: We have 30 points of capacity. What's the best sprint plan?

PIA: ## Sprint 15 Planning — 30 Points Available

### Option A: Revenue Protection (Recommended)
| Ticket | Points | Impact |
|--------|--------|--------|
| PROJ-4521 CSV Export | 5 | $205K ARR at risk, competitor pressure |
| PROJ-4398 Onboarding fix | 3 | 33% drop-off at step 3, affects all new users |
| PROJ-4412 Dashboard perf | 8 | P1 performance issue, 2 enterprise complaints |
| PROJ-4455 API docs update | 3 | Blocks 2 partner integrations |
| Tech debt: Module B tests | 11 | Unblocks 3 features in Sprint 16 |
**Total: 30 pts | Revenue protected: $290K | Features unblocked: 3**

### Option B: Big Bet
| Ticket | Points | Impact |
|--------|--------|--------|
| PROJ-4600 New dashboard type | 13 | Top-requested feature (42 votes) |
| PROJ-4521 CSV Export | 5 | $205K ARR at risk |
| PROJ-4470 Mobile responsive | 8 | Growing mobile usage trend |
| PROJ-4488 Notification prefs | 4 | Quality of life improvement |
**Total: 30 pts | New capability: Yes | Revenue protected: $205K**

### Trade-off
Option A protects existing revenue and creates capacity for Sprint 16.
Option B bets on new growth but leaves Module B debt unaddressed
(continues to block 3 features).
```

---

## 13. ACP Agent Implementation Details

### ACP Protocol basics

ACP is a communication protocol between an IDE (client) and a coding agent (server). The agent is a local process that the IDE starts and communicates with via stdio.

The protocol flow:
1. **IDE starts the agent process** (your Python script)
2. **Handshake**: IDE sends `initialize` → Agent responds with capabilities
3. **Auth**: If required, agent returns auth URL → user authenticates
4. **Messages**: IDE sends user messages → Agent processes and responds
5. **Tool use**: Agent can read/write files, run terminal commands (with IDE approval)

### Key ACP Python SDK patterns

Refer to the `agentclientprotocol/python-sdk` repository on GitHub for the latest API. The SDK provides:

- `ACPServer` class to create the server
- Message handling decorators
- File access utilities
- Authentication helpers

### Important: PIA is NOT a coding agent

Unlike every other ACP agent, PIA does not write or modify code. It only reads the codebase for context. This means:

- It does NOT need terminal access
- It does NOT need file write access
- It ONLY needs file read access (to scan the codebase)
- It ONLY needs network access (to call YouTrack API and LLM API)

This makes the security/permissions model simpler and the agent more trustworthy.

---

## 14. YouTrack MCP Integration

### Two approaches to YouTrack data

**Approach A: REST API (recommended for Phase 1)**
- Direct HTTP calls to YouTrack
- Full control over what data you fetch
- Well-documented, stable API
- Requires a permanent token

**Approach B: MCP Server (for deeper integration)**
- YouTrack exposes an MCP server as of version 2025.3
- The MCP server provides pre-defined tools (create issue, update issue, etc.)
- More structured but less flexible than raw REST API
- Good for Phase 3+ when you want real-time sync

### YouTrack REST API — key endpoints for PIA

```
# Get a single issue with all fields
GET /api/issues/{idReadable}?fields=id,idReadable,summary,description,project(shortName),priority(name),state(name),assignee(login,fullName),reporter(login,fullName),created,updated,resolved,comments(id,text,author(login,fullName),created),tags(name),customFields(name,value(name)),links(direction,linkType(name),issues(idReadable,summary,state(name)))

# Search issues
GET /api/issues?query=project:{project}+state:Open&fields=...

# Get sprint issues
GET /api/agiles/{agileId}/sprints/{sprintId}?fields=issues(id,idReadable,summary,state(name),estimation(value))

# Get helpdesk tickets
GET /api/issues?query=project:{helpdeskProject}&fields=...
```

### Authentication

```python
import httpx

class YouTrackClient:
    def __init__(self, base_url: str, token: str):
        self.client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )

    async def get_issue(self, issue_id: str) -> dict:
        fields = "id,idReadable,summary,description,project(shortName),priority(name),state(name),assignee(login,fullName),reporter(login,fullName),created,updated,resolved,comments(id,text,author(login,fullName),created),tags(name),links(direction,linkType(name),issues(idReadable,summary,state(name)))"
        response = await self.client.get(f"/api/issues/{issue_id}", params={"fields": fields})
        response.raise_for_status()
        return response.json()
```

---

## 15. LLM Integration

### Prompt design principles

1. **Be explicit about role**: "You are a product intelligence assistant inside a developer's IDE"
2. **Provide structured data**: Send JSON, not prose, as context
3. **Request structured output**: Ask for markdown with specific sections
4. **Include constraints**: "Keep it concise", "Don't speculate", "Cite sources"
5. **Separate retrieval from generation**: First query the graph, then send results to LLM

### Prompt templates

All prompts live in `src/pia/llm/prompts.py` as string constants. Key prompts:

- `TICKET_ENRICHMENT_PROMPT` — Synthesize ticket data, linked issues, and code areas into a rich summary
- `CODE_AREA_IDENTIFICATION_PROMPT` — Given a ticket and file tree, identify relevant code areas
- `FEEDBACK_SYNTHESIS_PROMPT` — Summarize multiple feedback items about the same topic
- `PRIORITY_EXPLANATION_PROMPT` — Explain why a ticket should be prioritized (with evidence)
- `IMPACT_REPORT_PROMPT` — Generate a post-ship impact report from before/after data
- `SPRINT_PLANNING_PROMPT` — Generate sprint plan options with trade-offs

### Token management

- YouTrack tickets can be long (especially with comments). Truncate intelligently.
- Send only relevant portions of the file tree (not the entire project).
- Use a context budget: allocate tokens across ticket data (40%), code context (30%), linked issues (20%), instructions (10%).

```python
class ContextAssembler:
    def __init__(self, max_tokens: int = 6000):
        self.max_tokens = max_tokens
        self.budget = {
            "ticket": 0.4,
            "code": 0.3,
            "linked": 0.2,
            "instructions": 0.1,
        }

    def assemble(self, ticket: dict, code_areas: list, linked: list, prompt_template: str) -> str:
        """Assemble context within token budget."""
        ticket_budget = int(self.max_tokens * self.budget["ticket"])
        code_budget = int(self.max_tokens * self.budget["code"])
        # ... truncate each section to its budget
```

---

## 16. Data Model

### Node: Customer

```python
@dataclass
class Customer:
    id: str              # Unique identifier
    name: str            # Display name
    plan: str | None     # "enterprise", "pro", "free", etc.
    arr: float | None    # Annual recurring revenue
    contact_email: str | None
    source: str          # "youtrack_helpdesk", "intercom", "manual"
    metadata: dict       # Additional attributes
```

### Node: Ticket

```python
@dataclass
class Ticket:
    id: str              # YouTrack readable ID (e.g., "PROJ-4521")
    summary: str
    description: str
    project: str
    state: str           # "Open", "In Progress", "Done", etc.
    priority: str | None
    assignee: str | None
    reporter: str | None
    sprint: str | None
    tags: list[str]
    estimation: float | None  # Story points
    created: datetime
    updated: datetime
    resolved: datetime | None
    comments: list[dict]
    links: list[dict]    # Linked issues
    source: str          # "youtrack"
```

### Node: Feedback

```python
@dataclass
class Feedback:
    id: str              # Unique identifier
    text: str            # The actual feedback text
    author: str | None   # Who said it
    customer_id: str | None  # Link to customer node
    channel: str         # "helpdesk", "intercom", "interview", "nps"
    sentiment: str | None # "positive", "negative", "neutral"
    created: datetime
    source: str          # "youtrack_helpdesk", "intercom"
```

### Node: CodeArea

```python
@dataclass
class CodeArea:
    id: str              # Usually the filepath
    path: str            # Relative path in project
    type: str            # "file", "directory", "module"
    language: str | None
    lines_of_code: int | None
    last_modified: datetime | None
    change_frequency: int | None  # Changes in last 90 days
    authors: list[str]   # Git blame authors
    has_tests: bool | None
    source: str          # "codebase_scan"
```

---

## 17. User Interactions & Commands

### Natural language queries (primary interface)

Users interact with PIA through natural language in the IDE's AI Chat. PIA uses the LLM to interpret intent and route to the appropriate handler.

| User says | PIA does |
|-----------|----------|
| "Tell me about PROJ-4521" | Fetches ticket, enriches with code context, returns summary |
| "What's in Sprint 14?" | Fetches sprint, summarizes all tickets with context |
| "Who wants CSV export?" | Searches feedback/helpdesk for export mentions, aggregates by customer |
| "What code does PROJ-4521 touch?" | Analyzes ticket, identifies code areas with LLM |
| "What should we build next?" | Runs prioritization across open tickets (Phase 5) |
| "What happened after we shipped PROJ-4400?" | Runs impact analysis (Phase 5) |
| "Plan Sprint 15 with 30 points" | Generates optimized sprint plans (Phase 5) |
| "Connect this to Acme Corp" | Manually links a ticket to a customer in the graph |
| "Sync" | Triggers a full data sync from all connected sources |

### Intent detection

```python
INTENT_DETECTION_PROMPT = """
Classify the user's message into one of these intents:
- ticket_detail: Asking about a specific ticket (contains ticket ID like PROJ-1234 or HD-123)
- sprint_overview: Asking about a sprint or current work
- customer_demand: Asking about who wants something or customer feedback
- code_context: Asking about which code is affected
- prioritization: Asking what to build or prioritize
- impact_check: Asking about results of shipped work
- sprint_plan: Asking to plan a sprint
- manual_link: Asking to connect/link entities
- sync: Asking to refresh data
- general: Other/unclear

User message: "{message}"

Respond with JSON: {{"intent": "...", "entities": {{"ticket_id": "...", "sprint_name": "...", ...}}}}
"""
```

---

## 18. Configuration

### Configuration file

PIA uses a YAML configuration file at `~/.pia/config.yaml`:

```yaml
# YouTrack connection
youtrack:
  url: "https://your-instance.youtrack.cloud"
  token: "${YOUTRACK_TOKEN}"  # Environment variable reference
  projects:
    - "PROJ"        # Main project
    - "HD"          # Helpdesk project
  sync_interval: 300  # Seconds between auto-syncs (0 = manual only)

# LLM configuration
llm:
  provider: "anthropic"  # "anthropic" or "openai"
  model: "claude-sonnet-4-20250514"
  api_key: "${ANTHROPIC_API_KEY}"
  max_tokens: 4096
  temperature: 0.1  # Low temperature for factual responses

# Codebase configuration
codebase:
  root: "${PROJECT_ROOT}"  # Auto-detected from IDE context
  exclude_patterns:
    - "node_modules/"
    - ".git/"
    - "dist/"
    - "build/"
    - "__pycache__/"
    - "*.min.js"
  git_history_days: 90

# External integrations (Phase 3+)
integrations:
  intercom:
    enabled: false
    api_key: "${INTERCOM_API_KEY}"
  sentry:
    enabled: false
    auth_token: "${SENTRY_AUTH_TOKEN}"
    org_slug: "your-org"
    project_slug: "your-project"

# Database
database:
  path: "~/.pia/graph.db"

# Agent behavior
agent:
  name: "Product Intelligence"
  version: "0.1.0"
  auth_method: "terminal"  # "terminal" for ACP registry
```

### Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `YOUTRACK_URL` | Yes | YouTrack instance URL |
| `YOUTRACK_TOKEN` | Yes | YouTrack permanent token |
| `ANTHROPIC_API_KEY` | Yes (if using Claude) | Anthropic API key |
| `OPENAI_API_KEY` | Yes (if using OpenAI) | OpenAI API key |
| `INTERCOM_API_KEY` | No | Intercom API key (Phase 3) |
| `SENTRY_AUTH_TOKEN` | No | Sentry auth token (Phase 3) |

---

## 19. Testing Strategy

### Unit tests

- **YouTrack client**: Mock HTTP responses, verify parsing
- **Graph store**: Test CRUD operations, relationship queries, search
- **Linker**: Test entity resolution and relationship inference
- **LLM prompts**: Test that prompts are assembled correctly (don't test LLM output)

### Integration tests

- **ACP protocol**: Verify handshake, message handling, auth flow
- **YouTrack + Graph**: Sync real (fixture) data into graph, verify structure
- **End-to-end**: Send a user message, verify the full pipeline produces a reasonable response (using a mocked LLM that returns deterministic output)

### Test fixtures

Create realistic sample data in `fixtures/`:
- `youtrack_responses/issue_PROJ-4521.json` — A complete YouTrack issue response
- `youtrack_responses/sprint_14.json` — A sprint with multiple issues
- `sample_codebase/` — A minimal Python project with realistic structure
- `sample_graph.db` — A pre-populated SQLite database with test data

---

## 20. Publishing to ACP Registry

### Requirements

1. The agent must support authentication (terminal auth is simplest)
2. The agent must implement the ACP handshake correctly
3. Submit a PR to `github.com/agentclientprotocol/registry`

### Registry metadata file

```json
{
  "id": "product-intelligence-agent",
  "name": "Product Intelligence",
  "description": "Product management intelligence for JetBrains IDEs. Enriches YouTrack tickets with customer context, codebase awareness, and evidence-backed prioritization.",
  "vendor": "your-name",
  "license": "Apache-2.0",
  "homepage": "https://github.com/your-username/product-intelligence-agent",
  "distribution": {
    "type": "pypi",
    "package": "product-intelligence-agent"
  },
  "command": "pia",
  "args": ["serve"],
  "auth_methods": ["terminal"]
}
```

### Publishing checklist

- [ ] Agent passes ACP handshake verification (CI in registry repo checks this)
- [ ] README has clear setup instructions (YouTrack token, LLM API key)
- [ ] Published to PyPI
- [ ] PR submitted to `agentclientprotocol/registry`

---

## 21. Competitive Landscape

### Direct competitors: None

No product intelligence agent exists in the ACP registry. No tool connects YouTrack data to codebase context inside the IDE. This is a greenfield opportunity.

### Adjacent tools (and why they're different)

| Tool | What it does | Why PIA is different |
|------|-------------|---------------------|
| ChatPRD | AI PRD writer | Generates documents, doesn't understand your specific product/customers/code |
| Productboard | Feedback aggregation | Counts signals but doesn't connect to codebase complexity or revenue data |
| BuildBetter | Customer insights | Analyzes calls/feedback but disconnected from engineering tools |
| YouTrack AI | Ticket summarization | Works on individual tickets in isolation, no cross-system intelligence |
| Cursor/Copilot | Code generation | Writes code but doesn't understand WHY you're building something |

### PIA's unique positioning

PIA is the only tool that sits at the intersection of:
- Customer signals (who wants it, how much do they pay)
- Engineering reality (how hard is it, what code is involved)
- Business metrics (what moved after we shipped)
- All accessible inside the IDE, where engineers already work

---

## 22. Design Principles

1. **Evidence over opinion**: Every recommendation must be traceable to data. If PIA can't cite a source, it says so.

2. **Enrichment, not replacement**: PIA enriches human judgment. It never auto-closes tickets, auto-prioritizes sprints, or makes decisions. It provides information that helps humans decide better.

3. **Progressive disclosure**: Phase 1 gives basic ticket enrichment. Each phase adds a layer. The agent is useful at every stage, not just when "complete."

4. **Read-only by default**: PIA reads data from YouTrack and the codebase. It does NOT write, modify, or delete anything unless explicitly asked (and even then, with confirmation). This makes it safe and trustworthy.

5. **Local-first**: The Product Context Graph lives locally on the developer's machine. No data leaves the machine except to the LLM API (and this can be switched to a local model for privacy).

6. **Standard protocols**: ACP for IDE integration, MCP for tool communication, REST for APIs. No proprietary protocols.

7. **Minimal dependencies**: SQLite, not Postgres. httpx, not a full web framework. Click, not a complex CLI library. Keep it simple.

---

## 23. Appendix: Research & References

### JetBrains Ecosystem

- ACP specification: `https://agentclientprotocol.com/`
- ACP Python SDK: `https://github.com/agentclientprotocol/python-sdk`
- ACP Registry: `https://github.com/agentclientprotocol/registry`
- ACP Registry contributing guide: See `CONTRIBUTING.md` in the registry repo
- YouTrack REST API: `https://www.jetbrains.com/help/youtrack/devportal/youtrack-rest-api.html`
- YouTrack MCP Server: `https://www.jetbrains.com/help/youtrack/cloud/youtrack-mcp-server.html`
- JetBrains AI Assistant docs: `https://www.jetbrains.com/help/ai-assistant/`
- JetBrains Air (new ADE): `https://www.jetbrains.com/air/`

### YC Context

- YC Spring 2026 RFS — "Cursor for Product Managers": `https://www.ycombinator.com/rfs`
- YC explicitly calls for tools that help figure out WHAT to build, not just HOW to build it

### Product Management Frameworks

- Continuous Discovery Habits (Teresa Torres) — the interview/feedback synthesis workflow
- RICE scoring — Revenue, Impact, Confidence, Effort — used as basis for prioritization logic
- Evidence-Guided Product Development (Itamar Gilad) — evidence chains concept

---

## Quick Start for Claude Code

When working with Claude Code on this project, use the following approach:

1. **Start with Phase 1 only**. Do not attempt to build all phases at once.
2. **Create the project structure first** — set up `pyproject.toml`, directory structure, and empty `__init__.py` files before writing any logic.
3. **Build the YouTrack client first** — get data flowing before doing anything with it.
4. **Test against real YouTrack data** — use a free YouTrack Cloud instance for testing.
5. **Build the ACP server last in Phase 1** — get the logic working as a CLI tool first, then wrap it in ACP.
6. **Use the simplest possible approach at every step**. If keyword grep works for code matching in Phase 1, don't reach for embeddings. Upgrade later.

### Suggested Claude Code prompts for Phase 1

```
Prompt 1: "Set up the Python project structure for PIA as described in
the spec. Create pyproject.toml with all dependencies, the directory
structure under src/pia/, and placeholder __init__.py files. Use Python 3.11+."

Prompt 2: "Implement the YouTrack REST API client in src/pia/sources/youtrack.py.
It should be an async class using httpx that can fetch a single issue
with all fields (summary, description, comments, links, state, priority,
assignee, sprint). Include proper error handling and typing."

Prompt 3: "Implement the basic codebase scanner in src/pia/sources/codebase.py.
It should walk a project directory (excluding node_modules, .git, etc.),
build a file tree, and given a list of keywords, find files whose paths
or names match. Keep it simple — no LLM, just keyword matching."

Prompt 4: "Implement the LLM client in src/pia/llm/client.py and the
ticket enrichment prompt in src/pia/llm/prompts.py. Use the Anthropic
Python SDK. The enrichment prompt should take ticket JSON, linked issues,
and code areas as input and produce a markdown summary."

Prompt 5: "Implement the ACP server in src/pia/agent/server.py using the
ACP Python SDK. It should handle the initialize handshake, receive user
messages, detect if the message is asking about a ticket (by finding
a ticket ID pattern like PROJ-1234), and if so, fetch the ticket from
YouTrack, find related code areas, and return an enriched summary."

Prompt 6: "Write tests for the YouTrack client and codebase scanner.
Use pytest. Mock HTTP responses for YouTrack. Create a small fixture
codebase directory for testing the scanner."
```
