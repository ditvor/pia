# Test Fixtures

Static data used by the test suite. All fixtures are committed to the repo.
Tests must never call real external APIs — use these files instead.

## Directory layout

```
fixtures/
├── youtrack_responses/     # Sample YouTrack REST API JSON responses
│   ├── issue_PROJ-4521.json    # A complete issue with comments, links, sprint
│   └── issue_PROJ-4400.json    # A linked "done" issue
│
├── sample_codebase/        # Minimal Python project for codebase scanner tests
│   └── src/
│       ├── services/export/pdf_export.py
│       └── api/routes/reports.py
│
└── sample_graph.db         # Pre-populated SQLite graph (Phase 4+)
```

## YouTrack response fixtures

Captured from the YouTrack REST API with this field set:

```
fields=idReadable,summary,description,project(name),
       priority(name),customFields(name,value(name)),
       assignee(login,fullName),reporter(login,fullName),
       created,updated,
       comments(text,author(login),created),
       links(direction,linkType(name),issues(idReadable,summary,resolved))
```

Add new fixtures by saving real API responses (with sensitive data scrubbed)
or by constructing them by hand to match the schema above.

## Sample codebase

A small set of stub files whose paths and contents contain keywords that
the `CodebaseScanner` should be able to match against ticket text.
Do not add real application logic — file existence and path names are enough.

## Adding fixtures

1. Create the JSON file in the appropriate subdirectory.
2. Load it in `tests/conftest.py` using a pytest fixture that reads the file.
3. Never reference fixture paths directly inside test functions — always go
   through a `conftest.py` fixture so paths stay portable.
