"""CLI chat session — interactive Rich REPL for conversational use.

Accumulates messages in a running conversation, supports session
persistence for continuity across restarts.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt

if TYPE_CHECKING:
    from evosys.agents.agent import Agent
    from evosys.storage.memory_store import MemoryStore

console = Console()


class CLIChatSession:
    """Interactive conversation session with the EvoSys agent.

    Messages accumulate in context across turns.  Optionally persists
    conversation history to the memory store under a session name.

    Parameters
    ----------
    agent:
        The general agent for handling messages.
    memory_store:
        Optional store for persisting session history.
    session_name:
        Session name for persistence (empty = ephemeral).
    """

    def __init__(
        self,
        agent: Agent,
        memory_store: MemoryStore | None = None,
        session_name: str = "",
    ) -> None:
        self._agent = agent
        self._memory = memory_store
        self._session_name = session_name
        self._history: list[dict[str, str]] = []

    async def run(self) -> None:
        """Start the interactive REPL loop."""
        console.print(
            Panel(
                "[bold]EvoSys Chat[/bold]\n"
                "Type your message and press Enter. "
                "Commands: /quit, /clear, /history, /save",
                border_style="blue",
            )
        )

        # Load previous session if available
        if self._session_name and self._memory:
            await self._load_session()

        while True:
            try:
                user_input = Prompt.ask("[bold blue]You[/bold blue]")
            except (KeyboardInterrupt, EOFError):
                break

            user_input = user_input.strip()
            if not user_input:
                continue

            # Handle commands
            if user_input.startswith("/"):
                should_continue = await self._handle_command(user_input)
                if not should_continue:
                    break
                continue

            # Add to history and run agent
            self._history.append({"role": "user", "content": user_input})

            # Build context from conversation history
            context: dict[str, object] | None = None
            if len(self._history) > 1:
                context = {
                    "conversation_history": self._history[-20:],
                    "session": self._session_name or "ephemeral",
                }

            console.print("[dim]Thinking...[/dim]")

            try:
                result = await self._agent.run(task=user_input, context=context)
                self._history.append({"role": "assistant", "content": result.answer})

                console.print()
                console.print(
                    Panel(
                        Markdown(result.answer),
                        title="[bold green]EvoSys[/bold green]",
                        border_style="green",
                        subtitle=(
                            f"[dim]{result.total_tokens} tokens"
                            f" | {result.iterations} iters[/dim]"
                        ),
                    )
                )

                # Auto-save session periodically
                if self._session_name and self._memory and len(self._history) % 5 == 0:
                    await self._save_session()

            except Exception as exc:
                console.print(f"[red]Error:[/red] {exc}")

    async def _handle_command(self, cmd: str) -> bool:
        """Handle a slash command. Returns False to quit."""
        if cmd in ("/quit", "/exit", "/q"):
            if self._session_name and self._memory:
                await self._save_session()
            console.print("[dim]Goodbye![/dim]")
            return False

        if cmd == "/clear":
            self._history.clear()
            console.print("[dim]Conversation cleared.[/dim]")
            return True

        if cmd == "/history":
            if not self._history:
                console.print("[dim]No messages yet.[/dim]")
            else:
                for msg in self._history[-10:]:
                    role = msg["role"]
                    content = msg["content"][:100]
                    color = "blue" if role == "user" else "green"
                    console.print(f"[{color}]{role}:[/{color}] {content}")
            return True

        if cmd == "/save":
            if self._session_name and self._memory:
                await self._save_session()
                console.print(f"[green]Session '{self._session_name}' saved.[/green]")
            else:
                console.print("[dim]No session name set. Use --session NAME.[/dim]")
            return True

        console.print(f"[dim]Unknown command: {cmd}[/dim]")
        return True

    async def _save_session(self) -> None:
        """Persist conversation history to memory store."""
        if not self._memory or not self._session_name:
            return
        data = json.dumps(self._history, default=str)
        await self._memory.set(
            "chat_history",
            data,
            namespace=self._session_name,
        )

    async def _load_session(self) -> None:
        """Load previous conversation history from memory store."""
        if not self._memory or not self._session_name:
            return
        data = await self._memory.get("chat_history", namespace=self._session_name)
        if data:
            try:
                self._history = json.loads(data)
                console.print(
                    f"[dim]Loaded {len(self._history)} messages from "
                    f"session '{self._session_name}'[/dim]"
                )
            except json.JSONDecodeError:
                pass
