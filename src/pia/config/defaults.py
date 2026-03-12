"""Default configuration values.

All constants here are pure Python — no imports from the rest of the
package. Every default must have a comment explaining the rationale.
"""

# ---------------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------------

# claude-sonnet-4-6 balances capability and cost for ticket enrichment.
DEFAULT_LLM_PROVIDER: str = "anthropic"
DEFAULT_LLM_MODEL: str = "claude-sonnet-4-6"
DEFAULT_LLM_MAX_TOKENS: int = 4096
# 0.1 keeps responses factual and consistent; avoids hallucinated details.
DEFAULT_LLM_TEMPERATURE: float = 0.1

# ---------------------------------------------------------------------------
# YouTrack
# ---------------------------------------------------------------------------

# No auto-sync by default — user triggers manually via `pia sync`.
DEFAULT_SYNC_INTERVAL: int = 0
DEFAULT_YOUTRACK_PROJECTS: list[str] = []

# ---------------------------------------------------------------------------
# Codebase scanner
# ---------------------------------------------------------------------------

# Directories that are almost never relevant to ticket context.
DEFAULT_EXCLUDE_PATTERNS: list[str] = [
    "node_modules/",
    ".git/",
    "dist/",
    "build/",
    "__pycache__/",
    ".venv/",
    "venv/",
    ".mypy_cache/",
    ".pytest_cache/",
    "*.min.js",
    "*.pyc",
]

# 90 days captures recent activity without being too slow on large repos.
DEFAULT_GIT_HISTORY_DAYS: int = 90

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

DEFAULT_DATABASE_PATH: str = "~/.pia/graph.db"

# ---------------------------------------------------------------------------
# Agent / ACP
# ---------------------------------------------------------------------------

DEFAULT_AGENT_NAME: str = "Product Intelligence"
DEFAULT_AGENT_VERSION: str = "0.1.0"
DEFAULT_AUTH_METHOD: str = "terminal"

# ---------------------------------------------------------------------------
# Filesystem
# ---------------------------------------------------------------------------

DEFAULT_CONFIG_PATH: str = "~/.pia/config.yaml"
