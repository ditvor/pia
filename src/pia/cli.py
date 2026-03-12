"""Click CLI: `pia serve`, `pia config`, `pia test-connection`."""

from __future__ import annotations

import asyncio
import json
import logging
import sys

import click

logger = logging.getLogger(__name__)


@click.group()
@click.option("--debug", is_flag=True, default=False, help="Enable debug logging.")
def main(debug: bool) -> None:
    """Product Intelligence Agent."""
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s")


@main.command()
def serve() -> None:
    """Start the ACP agent server (stdio transport)."""
    from pia.agent.server import create_pia_server
    from pia.config.settings import load_settings

    try:
        settings = load_settings()
    except Exception as exc:
        click.echo(f"Configuration error: {exc}", err=True)
        sys.exit(1)

    server = create_pia_server(settings)
    logger.info("Starting PIA server (stdio)")
    server.run("stdio")


@main.command("config")
@click.option(
    "--config-file",
    default=None,
    metavar="PATH",
    help="Path to YAML config file (default: ~/.pia/config.yaml).",
)
def show_config(config_file: str | None) -> None:
    """Print current resolved configuration (secrets masked)."""
    from pia.config.settings import load_settings

    try:
        settings = load_settings(config_file)
    except Exception as exc:
        click.echo(f"Configuration error: {exc}", err=True)
        sys.exit(1)

    click.echo(json.dumps(settings.masked(), indent=2))


@main.command("test-connection")
@click.option(
    "--config-file",
    default=None,
    metavar="PATH",
    help="Path to YAML config file (default: ~/.pia/config.yaml).",
)
def test_connection(config_file: str | None) -> None:
    """Verify that YouTrack and LLM connections are working."""
    from pia.config.settings import load_settings

    try:
        settings = load_settings(config_file)
    except Exception as exc:
        click.echo(f"Configuration error: {exc}", err=True)
        sys.exit(1)

    asyncio.run(_run_connection_tests(settings))


async def _run_connection_tests(settings) -> None:  # noqa: ANN001
    """Run async connectivity checks and print results."""
    import httpx

    from pia.llm.client import LLMClient, LLMError
    from pia.sources.youtrack import YouTrackClient, YouTrackError

    ok = True

    # --- YouTrack ---
    click.echo("Checking YouTrack…", nl=False)
    try:
        async with YouTrackClient(
            base_url=settings.youtrack.url,
            token=settings.youtrack.token,
        ) as yt:
            issues = await yt.search_issues("project: * order by: created desc", max_results=1)
        click.echo(f" OK (found {len(issues)} issue(s))")
    except YouTrackError as exc:
        click.echo(f" FAILED ({exc})")
        ok = False
    except httpx.HTTPError as exc:
        click.echo(f" FAILED (network: {exc})")
        ok = False
    except Exception as exc:
        click.echo(f" FAILED ({exc})")
        ok = False

    # --- LLM ---
    click.echo("Checking LLM…", nl=False)
    try:
        async with LLMClient(
            provider=settings.llm.provider,
            model=settings.llm.model,
            api_key=settings.llm.api_key,
            max_tokens=16,
            temperature=0.0,
        ) as llm:
            reply = await llm.complete("Reply with the single word: OK")
        click.echo(f" OK (model replied: {reply.strip()[:40]!r})")
    except LLMError as exc:
        click.echo(f" FAILED ({exc})")
        ok = False
    except Exception as exc:
        click.echo(f" FAILED ({exc})")
        ok = False

    if not ok:
        sys.exit(1)
