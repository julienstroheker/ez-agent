"""Main CLI application using Typer."""

from __future__ import annotations

import asyncio
import sys
from enum import Enum
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from ez_agent import __version__

app = typer.Typer(
    name="ezagent",
    help="EZ-Agent: A CLI framework for developing, testing, and deploying AI agents.",
    add_completion=True,
    no_args_is_help=True,
)

console = Console()
error_console = Console(stderr=True)


class RunMode(str, Enum):
    """Available run modes."""

    TERMINAL = "terminal"
    HTTP = "http"


def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        console.print(f"EZ-Agent version {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-v",
        help="Show version and exit.",
        callback=version_callback,
        is_eager=True,
    ),
) -> None:
    """EZ-Agent: Build and deploy AI agents with YAML configuration."""
    pass


@app.command()
def run(
    config: Path = typer.Option(
        ...,
        "--config",
        "-c",
        help="Path to agent configuration YAML file.",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
    ),
    mode: RunMode = typer.Option(
        RunMode.TERMINAL,
        "--mode",
        "-m",
        help="Run mode: terminal (interactive) or http (server).",
    ),
    host: str = typer.Option(
        "0.0.0.0",
        "--host",
        "-h",
        help="Host to bind HTTP server (http mode only).",
    ),
    port: int = typer.Option(
        8000,
        "--port",
        "-p",
        help="Port to bind HTTP server (http mode only).",
    ),
    reload: bool = typer.Option(
        False,
        "--reload",
        help="Enable auto-reload on code changes (development only).",
    ),
    tls_cert: Path | None = typer.Option(
        None,
        "--tls-cert",
        help="Path to TLS certificate file for HTTPS (production).",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
    ),
    tls_key: Path | None = typer.Option(
        None,
        "--tls-key",
        help="Path to TLS private key file for HTTPS (production).",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
    ),
) -> None:
    """
    Run an agent from a configuration file.

    Examples:
        ezagent run -c my-agent.yaml -m terminal
        ezagent run -c my-agent.yaml -m http --port 8080
    """
    from ez_agent.config import load_config, ConfigError

    try:
        # Load and validate configuration
        console.print(f"Loading configuration from [cyan]{config}[/cyan]...")
        agent_config = load_config(config)
        console.print(f"✓ Loaded agent [green]{agent_config.name}[/green] v{agent_config.version}")

        if mode == RunMode.TERMINAL:
            _run_terminal_mode(agent_config)
        else:
            _run_http_mode(agent_config, host, port, reload, tls_cert, tls_key)

    except ConfigError as e:
        error_console.print(f"[red]Configuration error:[/red] {e.message}")
        if e.errors:
            for err in e.errors:
                error_console.print(f"  • {err['loc']}: {err['msg']}")
        raise typer.Exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted[/yellow]")
        raise typer.Exit(0)
    except Exception as e:
        error_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


def _run_terminal_mode(config) -> None:
    """Run agent in terminal/REPL mode."""
    import logging
    from ez_agent.runtime.terminal import TerminalRunner

    # Configure logging - start quiet, users can enable with /logs command
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stderr,  # Use stderr so it doesn't interfere with Rich console output
    )
    
    # Quiet noisy Azure SDK and HTTP loggers
    logging.getLogger("azure").setLevel(logging.WARNING)
    logging.getLogger("azure.core.pipeline.policies.http_logging_policy").setLevel(logging.WARNING)
    logging.getLogger("azure.identity").setLevel(logging.WARNING)
    logging.getLogger("azure.monitor").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    # Suppress OpenTelemetry internal warnings (span already ended, context errors)
    # These are expected in async generators and handled gracefully
    logging.getLogger("opentelemetry").setLevel(logging.WARNING)
    logging.getLogger("opentelemetry.sdk.trace").setLevel(logging.ERROR)
    logging.getLogger("opentelemetry.context").setLevel(logging.ERROR)
    
    # ez_agent logger starts at WARNING, user can toggle with /logs
    logging.getLogger("ez_agent").setLevel(logging.WARNING)

    console.print("\n[bold]Starting terminal mode...[/bold]")
    console.print("Type your messages and press Enter. Type 'exit' or Ctrl+C to quit.\n")

    runner = TerminalRunner(config, console)
    asyncio.run(runner.run())


def _run_http_mode(
    config, 
    host: str, 
    port: int, 
    reload: bool,
    tls_cert: Path | None = None,
    tls_key: Path | None = None,
) -> None:
    """Run agent in HTTP server mode with optional TLS support."""
    import uvicorn

    from ez_agent.a2a.server import create_app

    # Determine protocol based on TLS settings
    use_tls = tls_cert is not None and tls_key is not None
    protocol = "https" if use_tls else "http"
    
    console.print(f"\n[bold]Starting HTTP{'S' if use_tls else ''} server on {host}:{port}...[/bold]")
    if use_tls:
        console.print(f"[green]TLS enabled[/green] - Certificate: {tls_cert}")
    console.print(f"Agent Card: {protocol}://{host}:{port}/.well-known/agent-card.json")
    console.print(f"A2A Endpoint: {protocol}://{host}:{port}/v1/message:send\n")

    app = create_app(config)
    
    # Build uvicorn config
    uvicorn_kwargs = {
        "host": host,
        "port": port,
        "reload": reload,
        "log_level": "info",
    }
    
    # Add TLS configuration if provided
    if use_tls:
        uvicorn_kwargs["ssl_certfile"] = str(tls_cert)
        uvicorn_kwargs["ssl_keyfile"] = str(tls_key)
    
    uvicorn.run(app, **uvicorn_kwargs)


@app.command()
def validate(
    config: Path = typer.Option(
        ...,
        "--config",
        "-c",
        help="Path to agent configuration YAML file.",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
    ),
) -> None:
    """
    Validate an agent configuration file.

    Checks YAML syntax and schema validation without running the agent.
    """
    from ez_agent.config import load_config, ConfigError

    try:
        console.print(f"Validating [cyan]{config}[/cyan]...")
        agent_config = load_config(config)

        console.print("\n[green]✓ Configuration is valid![/green]\n")

        # Show summary
        table = Table(title="Agent Configuration")
        table.add_column("Field", style="cyan")
        table.add_column("Value", style="white")

        table.add_row("Name", agent_config.name)
        table.add_row("Description", agent_config.description[:50] + "..." if len(agent_config.description) > 50 else agent_config.description)
        table.add_row("Version", agent_config.version)
        table.add_row("Model", agent_config.model)
        table.add_row("Provider", agent_config.configuration.provider.value)
        table.add_row("Tools", str(len(agent_config.tools)))

        # Feature flags
        features = []
        if agent_config.features.streaming:
            features.append("streaming")
        if agent_config.features.tool_execution:
            features.append("tools")
        if agent_config.features.conversation_history:
            features.append("history")
        table.add_row("Features", ", ".join(features) or "none")

        console.print(table)

    except ConfigError as e:
        error_console.print(f"\n[red]✗ Validation failed:[/red] {e.message}")
        if e.errors:
            for err in e.errors:
                error_console.print(f"  • {err['loc']}: {err['msg']}")
        raise typer.Exit(1)


@app.command()
def init(
    output_dir: Path = typer.Option(
        Path("."),
        "--output",
        "-o",
        help="Directory to create agent files in.",
    ),
    name: Optional[str] = typer.Option(
        None,
        "--name",
        "-n",
        help="Agent name (will prompt if not provided).",
    ),
) -> None:
    """
    Initialize a new agent project interactively.

    Creates a configuration file and optional tool files.
    """
    from ez_agent.cli.init import run_init_wizard

    run_init_wizard(output_dir, name, console)


if __name__ == "__main__":
    app()
