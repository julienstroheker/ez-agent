"""Terminal-based REPL runner for local agent testing."""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import TYPE_CHECKING

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.spinner import Spinner

if TYPE_CHECKING:
    from ez_agent.config.models import AgentConfig

logger = logging.getLogger(__name__)


class TerminalRunner:
    """
    Interactive terminal runner for testing agents locally.

    Provides a REPL interface for conversing with the agent,
    with support for:
    - Streaming responses
    - Conversation history
    - Tool execution visualization
    """

    def __init__(self, config: "AgentConfig", console: Console | None = None) -> None:
        """
        Initialize the terminal runner.

        Args:
            config: Agent configuration.
            console: Optional Rich console for output.
        """
        self._config = config
        self._console = console or Console()
        self._agent = None
        self._session_id: str | None = None

    async def run(self) -> None:
        """Run the interactive REPL loop."""
        from ez_agent.runtime.factory import create_agent_from_config

        # Create agent
        self._agent = create_agent_from_config(self._config)

        # Print welcome message
        self._print_welcome()

        # Main loop
        while True:
            try:
                # Get user input
                user_input = await self._get_input()

                if user_input is None:
                    break

                # Process special commands
                if user_input.startswith("/"):
                    if await self._handle_command(user_input):
                        continue
                    else:
                        break

                # Process message
                await self._process_message(user_input)

            except KeyboardInterrupt:
                self._console.print("\n[yellow]Interrupted[/yellow]")
                break
            except EOFError:
                break

        # Cleanup
        await self._cleanup()

    def _print_welcome(self) -> None:
        """Print welcome message."""
        self._console.print(Panel.fit(
            f"[bold]{self._config.name}[/bold]\n"
            f"[dim]{self._config.description}[/dim]\n\n"
            f"Model: [cyan]{self._config.model}[/cyan]\n"
            f"Provider: [cyan]{self._config.configuration.provider.value}[/cyan]",
            title="EZ-Agent Terminal",
            border_style="blue",
        ))

        self._console.print("\n[dim]Commands:[/dim]")
        self._console.print("  [cyan]/new[/cyan]    - Start a new conversation")
        self._console.print("  [cyan]/clear[/cyan]  - Clear the screen")
        self._console.print("  [cyan]/logs[/cyan]   - Toggle log output")
        self._console.print("  [cyan]/status[/cyan] - Show agent status")
        self._console.print("  [cyan]/exit[/cyan]   - Exit the agent")
        self._console.print("  [cyan]/help[/cyan]   - Show this help\n")

    async def _get_input(self) -> str | None:
        """Get user input from terminal."""
        try:
            # Use asyncio to allow for cancellation
            loop = asyncio.get_event_loop()
            user_input = await loop.run_in_executor(
                None,
                lambda: input("\n[You]: "),
            )
            return user_input.strip()
        except (EOFError, KeyboardInterrupt):
            return None

    async def _handle_command(self, command: str) -> bool:
        """
        Handle a slash command.

        Returns:
            True to continue, False to exit.
        """
        cmd = command.lower().strip()

        if cmd in ("/exit", "/quit", "/q"):
            self._console.print("[yellow]Goodbye![/yellow]")
            return False

        elif cmd == "/new":
            self._session_id = None
            self._console.print("[green]Started new conversation[/green]")
            return True

        elif cmd == "/clear":
            self._console.clear()
            self._print_welcome()
            return True

        elif cmd == "/help":
            self._print_welcome()
            return True

        elif cmd == "/status":
            if self._agent:
                health = await self._agent.health_check()
                self._console.print(f"Agent: [green]{health['status']}[/green]")
                self._console.print(f"Provider: {health['provider']['name']} - {'[green]healthy[/green]' if health['provider']['healthy'] else '[red]unhealthy[/red]'}")
            return True

        elif cmd == "/logs":
            # Toggle logging visibility
            import logging
            ez_logger = logging.getLogger("ez_agent")
            if ez_logger.level == logging.WARNING:
                ez_logger.setLevel(logging.INFO)
                self._console.print("[green]Logs enabled[/green] (INFO level)")
            elif ez_logger.level == logging.INFO:
                ez_logger.setLevel(logging.DEBUG)
                self._console.print("[green]Logs enabled[/green] (DEBUG level)")
            else:
                ez_logger.setLevel(logging.WARNING)
                self._console.print("[yellow]Logs disabled[/yellow]")
            return True

        else:
            self._console.print(f"[yellow]Unknown command: {cmd}[/yellow]")
            return True

    async def _process_message(self, message: str) -> None:
        """Process a user message and display the response."""
        if not self._agent:
            self._console.print("[red]Agent not initialized[/red]")
            return

        if not message:
            return

        try:
            if self._config.features.streaming:
                await self._process_streaming(message)
            else:
                await self._process_sync(message)

        except Exception as e:
            self._console.print(f"\n[red]Error:[/red] {e}")

    async def _process_streaming(self, message: str) -> None:
        """Process message with streaming response."""
        self._console.print()

        full_response = ""
        tool_calls_shown = set()

        with Live(
            Spinner("dots", text="Thinking..."),
            console=self._console,
            refresh_per_second=10,
        ) as live:
            async for task, chunk in self._agent.stream_message(
                message,
                session_id=self._session_id,
            ):
                # Update session ID from first response
                if self._session_id is None and task.session_id:
                    self._session_id = task.session_id

                # Handle tool calls
                for tool_call in chunk.tool_calls:
                    if tool_call.id not in tool_calls_shown:
                        tool_calls_shown.add(tool_call.id)
                        live.update(
                            f"[cyan]Using tool: {tool_call.name}[/cyan]"
                        )

                # Accumulate content
                if chunk.content:
                    full_response += chunk.content
                    # Update display with markdown rendering
                    live.update(Markdown(full_response))

                if chunk.is_final:
                    break

        # Final newline for clean prompt (content already displayed via Live)
        if full_response:
            self._console.print()

    async def _process_sync(self, message: str) -> None:
        """Process message synchronously (non-streaming)."""
        with self._console.status("Thinking...", spinner="dots"):
            task, response = await self._agent.process_message(
                message,
                session_id=self._session_id,
            )

            if self._session_id is None and task.session_id:
                self._session_id = task.session_id

        self._console.print(f"\n[bold blue][{self._config.name}]:[/bold blue]")
        self._console.print(Markdown(response))

    async def _cleanup(self) -> None:
        """Clean up resources."""
        if self._agent:
            await self._agent.close()
