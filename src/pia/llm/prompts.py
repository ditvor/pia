"""All LLM prompt templates, centralised as string constants.

Rules:
- Every prompt used anywhere in PIA must be defined here, never inline.
- Use Python str.format() placeholders: {slot_name}.
- Keep prompts provider-agnostic — they are passed to whichever LLM is
  configured.
- Phase markers show which phase introduces each prompt.
"""

# ---------------------------------------------------------------------------
# Phase 1 — YouTrack ticket enrichment
# ---------------------------------------------------------------------------

TICKET_ENRICHMENT_PROMPT = """\
You are a product intelligence assistant embedded in a developer's IDE.
The developer asked about a YouTrack ticket. Give them a rich, actionable
summary that covers business context, technical context, and everything
they need to start working on it — without requiring them to open YouTrack.

## Ticket Data
```json
{ticket_json}
```

## Linked Issues
```json
{linked_issues_json}
```

## Likely Related Code Areas
{code_areas}

## Output instructions
- Open with one sentence stating what the ticket is and why it matters.
- Show a compact status line: ID · State · Priority · Assignee · Sprint.
- Summarise comments in 2–4 bullet points. Highlight decisions already made
  and any open questions the developer should be aware of.
- List linked issues grouped by relationship type. Mark resolved ones clearly.
- If helpdesk tickets (e.g. HD-*) are linked, call out the customer context
  explicitly — mention company names or counts if present in the data.
- Show the code areas section only when files were found. For each file,
  explain in one phrase *why* it is likely relevant based on the matched
  keywords.
- Do not speculate beyond what is in the data.
- Do not repeat the raw JSON; synthesise it into readable prose and lists.
- Format the response in Markdown. Use headers (##), bullet lists, and
  inline code for file paths.
"""

# ---------------------------------------------------------------------------
# Phase 2 — LLM-assisted code area identification
# (stub — implemented in Phase 2)
# ---------------------------------------------------------------------------

CODE_AREA_IDENTIFICATION_PROMPT = """\
[Phase 2 — not yet implemented]

Given the following YouTrack ticket and project file tree, identify the
files and directories most likely to be relevant to the work described.

## Ticket
{ticket_json}

## File Tree
{file_tree}

## Instructions
- Return a JSON array of objects: [{{"path": "...", "reason": "..."}}]
- Limit to the 10 most relevant paths.
- Give a concrete one-sentence reason for each path.
- Do not include test files unless the ticket is specifically about tests.
"""

# ---------------------------------------------------------------------------
# Phase 3 — Customer feedback synthesis
# (stub — implemented in Phase 3)
# ---------------------------------------------------------------------------

FEEDBACK_SYNTHESIS_PROMPT = """\
[Phase 3 — not yet implemented]

Synthesise the following customer feedback items into a structured summary.

## Feedback Items
{feedback_json}

## Instructions
- Identify the top themes (max 5).
- Quote representative verbatim excerpts for each theme.
- Note the volume of feedback per theme.
- Flag any urgent or blocking issues explicitly.
"""

# ---------------------------------------------------------------------------
# Phase 5 — Priority explanation
# (stub — implemented in Phase 5)
# ---------------------------------------------------------------------------

PRIORITY_EXPLANATION_PROMPT = """\
[Phase 5 — not yet implemented]

Explain why the following ticket should (or should not) be prioritised,
citing evidence from the product context graph.

## Ticket
{ticket_json}

## Evidence
{evidence_json}

## Instructions
- Lead with a one-sentence recommendation.
- Support it with 3–5 bullet points, each citing a specific evidence item.
- Note any counter-arguments or risks.
- Be concise — this will be shown inline in the IDE.
"""

# ---------------------------------------------------------------------------
# Phase 5 — Post-ship impact report
# (stub — implemented in Phase 5)
# ---------------------------------------------------------------------------

IMPACT_REPORT_PROMPT = """\
[Phase 5 — not yet implemented]

Generate a post-ship impact report comparing before/after metrics.

## Shipped Ticket
{ticket_json}

## Before Metrics
{before_json}

## After Metrics
{after_json}

## Instructions
- State the overall impact (positive / neutral / negative) in one sentence.
- Show key metric changes as a table.
- Note any unexpected side effects.
- Suggest follow-up actions if warranted.
"""

# ---------------------------------------------------------------------------
# Phase 5 — Sprint planning
# (stub — implemented in Phase 5)
# ---------------------------------------------------------------------------

SPRINT_PLANNING_PROMPT = """\
[Phase 5 — not yet implemented]

Generate sprint plan options with trade-offs for the given backlog.

## Candidate Tickets
{tickets_json}

## Team Capacity
{capacity_json}

## Constraints
{constraints}

## Instructions
- Propose two or three sprint configurations.
- For each: list included tickets, total estimate, expected impact.
- Call out dependencies and risks for each option.
- Recommend one option with a brief rationale.
"""
