from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from math import ceil
from pathlib import Path
from threading import Lock, Thread
from time import monotonic, sleep

import readchar
from breach_models import BreachLookupResult
from rich import box
from rich.console import Console, Group, RenderableType
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from branding import ascii_banner
from clipboard import ClipboardError, copy_text
from exporter import export_selected_records
from git_client import GitRepositoryClient
from models import EmailRecord

SORT_MODES = ("commits", "recent", "name", "email", "domain")
SORT_LABELS = {
    "commits": "Commits",
    "recent": "Recent",
    "name": "Name",
    "email": "Email",
    "domain": "Domain",
}


def sort_records(records: list[EmailRecord], sort_mode: str) -> list[EmailRecord]:
    if sort_mode == "recent":
        return sorted(
            records,
            key=lambda record: (
                record.last_seen,
                record.commit_count,
                record.name.lower(),
                record.email.lower(),
            ),
            reverse=True,
        )
    if sort_mode == "name":
        return sorted(records, key=lambda record: (record.name.lower(), record.email.lower()))
    if sort_mode == "email":
        return sorted(records, key=lambda record: (record.email.lower(), record.name.lower()))
    if sort_mode == "domain":
        return sorted(
            records,
            key=lambda record: (
                record.domain,
                -record.commit_count,
                record.name.lower(),
            ),
        )
    return sorted(
        records,
        key=lambda record: (
            -record.commit_count,
            -record.last_seen.toordinal(),
            record.name.lower(),
            record.email.lower(),
        ),
    )


@dataclass(slots=True)
class TUIResult:
    visible_records: list[EmailRecord]


@dataclass(slots=True)
class ScanProgressState:
    repo_source: str
    message: str = "Waiting to start..."
    stage: str = "idle"
    current: int = 0
    total: int = 0
    done: bool = False
    cancelled: bool = False
    error: Exception | None = None
    session: object | None = None
    started_at: float = field(default_factory=monotonic)


@dataclass(slots=True)
class TUIState:
    all_records: list[EmailRecord]
    repo_name: str
    repo_path: Path
    output_dir: Path
    selected_output_path: Path
    breach_reports: dict[str, BreachLookupResult] = field(default_factory=dict)
    selected_emails: set[str] = field(default_factory=set)
    index: int = 0
    scroll_offset: int = 0
    exclude_github_noreply: bool = False
    search_query: str = ""
    sort_mode: str = "commits"
    status_message: str = "Ready"
    status_style: str = "green"
    compact_help: bool = False
    include_breach_details: bool = True

    def filtered_records(self) -> list[EmailRecord]:
        records = list(self.all_records)
        if self.exclude_github_noreply:
            records = [record for record in records if not record.is_github_noreply]

        query = self.search_query.strip().lower()
        if query:
            records = [
                record
                for record in records
                if query in record.name.lower()
                or query in record.email.lower()
                or query in record.domain.lower()
            ]

        return sort_records(records, self.sort_mode)

    def current_record(self) -> EmailRecord | None:
        records = self.filtered_records()
        if not records:
            return None
        self.index = max(0, min(self.index, len(records) - 1))
        return records[self.index]

    def clamp_index(self) -> None:
        records = self.filtered_records()
        if not records:
            self.index = 0
            self.scroll_offset = 0
            return
        self.index = max(0, min(self.index, len(records) - 1))

    def ensure_visible(self, window_size: int) -> None:
        self.clamp_index()
        if window_size <= 0:
            self.scroll_offset = 0
            return

        records = self.filtered_records()
        if not records:
            self.scroll_offset = 0
            return

        max_offset = max(0, len(records) - window_size)
        self.scroll_offset = min(self.scroll_offset, max_offset)

        if self.index < self.scroll_offset:
            self.scroll_offset = self.index
        elif self.index >= self.scroll_offset + window_size:
            self.scroll_offset = self.index - window_size + 1

        self.scroll_offset = max(0, min(self.scroll_offset, max_offset))

    def visible_selected_count(self) -> int:
        visible = {record.email for record in self.filtered_records()}
        return len(self.selected_emails & visible)


class GitEmailReconTUI:
    @classmethod
    def prompt_for_repo_url(cls) -> str | None:
        console = Console()
        layout = Layout()
        layout.split(
            Layout(name="header", size=7),
            Layout(name="body", ratio=1),
            Layout(name="footer", size=6),
        )
        layout["header"].update(cls._render_repo_prompt_header())
        layout["body"].update(
            cls._build_prompt_panel(
                title="Open Repository",
                prompt="Type a git repository URL or local path. Enter clones it. Q cancels.",
                current="",
            )
        )
        layout["footer"].update(cls._build_input_footer())

        tui = cls.__new__(cls)
        tui.console = console

        with Live(
            layout,
            screen=True,
            auto_refresh=False,
            console=console,
        ) as live:
            return tui._prompt_text(
                layout,
                live,
                title="Open Repository",
                prompt="Type a git repository URL or local path. Enter clones it. Q cancels.",
            )

    @classmethod
    def prompt_for_repo_and_scan(
        cls,
        *,
        scan_service: object,
        options: object,
        initial_repo_source: str | None = None,
    ) -> tuple[str, object] | None:
        console = Console()
        layout = Layout()
        layout.split(
            Layout(name="header", size=7),
            Layout(name="body", ratio=1),
            Layout(name="footer", size=6),
        )
        layout["header"].update(cls._render_repo_prompt_header())
        layout["body"].update(
            cls._build_prompt_panel(
                title="Open Repository",
                prompt="Type a git repository URL or local path. Enter starts the scan. Q cancels.",
                current="",
            )
        )
        layout["footer"].update(cls._build_input_footer())

        tui = cls.__new__(cls)
        tui.console = console

        with Live(layout, screen=True, auto_refresh=False, console=console) as live:
            repo_source = initial_repo_source
            if repo_source is None:
                repo_source = tui._prompt_text(
                    layout,
                    live,
                    title="Open Repository",
                    prompt="Type a git repository URL or local path. Enter starts the scan. Q cancels.",
                )
            if not repo_source:
                return None
            return tui._run_scan_loading_screen(
                layout,
                live,
                repo_source=repo_source,
                scan_service=scan_service,
                options=options,
            )

    def __init__(
        self,
        *,
        records: list[EmailRecord],
        repo_name: str,
        repo_path: Path,
        output_dir: Path,
        selected_output_path: Path,
        initial_exclude_github_noreply: bool,
        initial_sort_mode: str,
        compact_help: bool,
        breach_reports: dict[str, BreachLookupResult],
        include_breach_details: bool,
    ) -> None:
        self.console = Console()
        self.client = GitRepositoryClient(repo_path)
        self.state = TUIState(
            all_records=records,
            repo_name=repo_name,
            repo_path=repo_path,
            output_dir=output_dir,
            selected_output_path=selected_output_path,
            breach_reports=breach_reports,
            exclude_github_noreply=initial_exclude_github_noreply,
            sort_mode=initial_sort_mode if initial_sort_mode in SORT_MODES else "commits",
            status_message="Use arrows or j/k to navigate",
            status_style="green",
            compact_help=compact_help,
            include_breach_details=include_breach_details,
        )

    def run(self) -> TUIResult:
        layout = self._build_layout()

        with Live(
            layout,
            screen=True,
            auto_refresh=False,
            console=self.console,
        ) as live:
            self._render(layout)
            live.refresh()
            while True:
                key = readchar.readkey()
                if key == "Q":
                    break
                action = self._normalize_key(key)

                if action == "up":
                    self._move(-1)
                elif action == "down":
                    self._move(1)
                elif action == "page_up":
                    self._page(-1)
                elif action == "page_down":
                    self._page(1)
                elif action == "toggle_select":
                    self._toggle_select()
                elif action == "toggle_noreply":
                    self._toggle_github_noreply_filter()
                elif action == "view_breaches":
                    self._show_breach_view(layout, live)
                elif action == "view_commits":
                    self._show_commit_view(layout, live)
                elif action == "export_selected":
                    self._export_selected(layout, live)
                elif action == "search":
                    self._set_search(layout, live)
                elif action == "sort":
                    self._cycle_sort_mode()
                elif action == "copy":
                    self._copy_current_email()
                elif action == "insights":
                    self._show_domain_insights(layout, live)
                elif action == "help":
                    self._show_help(layout, live)
                elif action == "top":
                    self._jump_to_top()
                elif action == "bottom":
                    self._jump_to_bottom()
                elif action == "quit":
                    break

                self._render(layout)
                live.refresh()

        return TUIResult(visible_records=self.state.filtered_records())

    def _build_layout(self) -> Layout:
        layout = Layout()
        layout.split(
            Layout(name="header", size=7),
            Layout(name="body", ratio=1),
            Layout(name="footer", size=6),
        )
        return layout

    def _render(self, layout: Layout) -> None:
        self.state.clamp_index()
        self.state.ensure_visible(self._table_window_size())
        layout["header"].update(self._render_header())
        layout["body"].update(self._render_body())
        layout["footer"].update(self._render_footer())

    def _table_window_size(self) -> int:
        return max(8, self.console.size.height - 18)

    def _page_info(self, record_count: int) -> tuple[int, int]:
        page_size = self._table_window_size()
        if record_count == 0:
            return (0, 0)
        page = min(record_count - 1, self.state.index) // page_size + 1
        total_pages = ceil(record_count / page_size)
        return (page, total_pages)

    def _render_header(self) -> Panel:
        visible_records = self.state.filtered_records()
        visible_count = len(visible_records)
        page, total_pages = self._page_info(visible_count)
        noreply_count = sum(
            1 for record in self.state.all_records if record.is_github_noreply
        )
        search_text = Text.assemble(
            ("Search ", "green"),
            (self.state.search_query if self.state.search_query else "none", "bold white"),
        )
        status_text = Text.assemble(
            ("Status ", "green"),
            (self.state.status_message, self.state.status_style),
        )

        hero = Table.grid(expand=True)
        hero.add_column(justify="left", ratio=2)
        hero.add_column(justify="center", ratio=2)
        hero.add_column(justify="right", ratio=2)
        hero.add_row(
            f"[bold white]{self.state.repo_name}[/bold white]",
            f"[green]Visible[/green] [bold white]{visible_count}[/bold white]   "
            f"[green]Total[/green] [bold white]{len(self.state.all_records)}[/bold white]",
            f"[green]Page[/green] [bold white]{page}/{total_pages}[/bold white]",
        )
        hero.add_row(
            f"[green]Selected[/green] [bold white]{self.state.visible_selected_count()}[/bold white]",
            f"[green]Sort[/green] [bold white]{SORT_LABELS[self.state.sort_mode]}[/bold white]",
            f"[green]Noreply[/green] [bold white]{noreply_count}[/bold white] "
            f"[green]({'hidden' if self.state.exclude_github_noreply else 'shown'})[/green]",
        )
        hero.add_row(
            search_text,
            "",
            status_text,
        )

        return Panel(
            hero,
            title="[bold green]GitSnoop[/bold green]",
            border_style="green",
            box=box.HEAVY,
            style="white on black",
            padding=(0, 1),
        )

    @staticmethod
    def _render_repo_prompt_header() -> Panel:
        hero = Table.grid(expand=True)
        hero.add_column(justify="left", ratio=2)
        hero.add_column(justify="center", ratio=2)
        hero.add_column(justify="right", ratio=2)
        hero.add_row(
            "[bold white]Awaiting repository[/bold white]",
            "[green]Visible[/green] [bold white]0[/bold white]   "
            "[green]Total[/green] [bold white]0[/bold white]",
            "[green]Page[/green] [bold white]0/0[/bold white]",
        )
        hero.add_row(
            "[green]Selected[/green] [bold white]0[/bold white]",
            "[green]Sort[/green] [bold white]Commits[/bold white]",
            "[green]Noreply[/green] [bold white]0[/bold white] [green](shown)[/green]",
        )
        hero.add_row(
            Text.assemble(("Search ", "green"), ("none", "bold white")),
            "",
            Text.assemble(("Status ", "green"), ("Enter a repository path or URL", "green")),
        )

        return Panel(
            hero,
            title="[bold green]GitSnoop[/bold green]",
            border_style="green",
            box=box.HEAVY,
            style="white on black",
            padding=(0, 1),
        )

    def _render_body(self) -> Panel:
        records = self.state.filtered_records()
        if not records:
            empty = Group(
                Text("No emails match the active filters.", style="bold yellow"),
                Text("Press / to search again or n to toggle the noreply filter.", style="white"),
            )
            return Panel(
                empty,
                border_style="green",
                title="[bold green]Results[/bold green]",
                style="white on black",
                box=box.ROUNDED,
                padding=(1, 2),
            )

        start = self.state.scroll_offset
        end = min(len(records), start + self._table_window_size())
        visible_slice = records[start:end]

        table = Table(
            expand=True,
            header_style="bold green",
            border_style="green",
            box=box.SIMPLE_HEAVY,
            row_styles=["white on black", "white on color(232)"],
            pad_edge=False,
        )
        table.add_column("", width=3, justify="center")
        table.add_column("Name", ratio=2, style="bold white")
        table.add_column("Email", ratio=3, style="white")
        table.add_column("Domain", ratio=2, style="green")
        table.add_column("isBreached", width=10, justify="center")
        table.add_column("Commits", width=9, justify="right", style="bold white")
        table.add_column("Last Seen", width=10, style="white")

        for index, record in enumerate(visible_slice, start=start):
            selected = "[bold green]●[/bold green]" if record.email in self.state.selected_emails else ""
            breach_result = self.state.breach_reports.get(record.email)
            breach_marker = "[bold red]■[/bold red]" if breach_result and breach_result.is_breached else ""
            row_style = "bold white on green" if index == self.state.index else ""
            table.add_row(
                selected,
                record.name,
                record.email,
                record.domain,
                breach_marker,
                str(record.commit_count),
                record.last_seen.isoformat(),
                style=row_style,
            )

        top_indicator = (
            Text.from_markup("[bold green]▲ more above[/bold green]")
            if start > 0
            else Text(" ", style="white")
        )
        bottom_indicator = (
            Text.from_markup("[bold green]▼ more below[/bold green]")
            if end < len(records)
            else Text(" ", style="white")
        )
        stats_line = Text.from_markup(
            f"[green]Showing[/green] [bold white]{start + 1}-{end}[/bold white] "
            f"[green]of[/green] [bold white]{len(records)}[/bold white]   "
            f"[green]Page size[/green] [bold white]{self._table_window_size()}[/bold white]"
        )

        content: RenderableType = Group(top_indicator, table, bottom_indicator, stats_line)
        return Panel(
            content,
            title="[bold green]Authors[/bold green]",
            border_style="green",
            style="white on black",
            box=box.ROUNDED,
            padding=(0, 1),
        )

    def _render_footer(self) -> Panel:
        footer = Group(
            Text.from_markup(
                "[bold cyan]↑/↓[/bold cyan] move   "
                "[bold cyan]PgUp/PgDn[/bold cyan] page   "
                "[bold green]space[/bold green] select   "
                "[bold yellow]enter[/bold yellow] breaches   "
                "[bold magenta]/[/bold magenta] search   "
                "[bold blue]s[/bold blue] sort   "
                "[bold white]c[/bold white] copy email"
            ),
            Text.from_markup(
                "[bold magenta]n[/bold magenta] noreply   "
                "[bold cyan]h[/bold cyan] commits   "
                "[bold cyan]i[/bold cyan] insights   "
                "[bold yellow]?[/bold yellow] help   "
                "[bold blue]g/G[/bold blue] top/bottom   "
                "[bold green]e[/bold green] export   "
                "[bold red]q[/bold red] quit"
            ),
        )
        return Panel(
            footer,
            border_style="green",
            title="[bold green]Controls[/bold green]",
            style="white on black",
            box=box.HEAVY,
            padding=(0, 1),
        )

    def _normalize_key(self, key: str) -> str | None:
        page_up = getattr(readchar.key, "PAGE_UP", "")
        page_down = getattr(readchar.key, "PAGE_DOWN", "")
        mapping = {
            readchar.key.UP: "up",
            readchar.key.DOWN: "down",
            readchar.key.ENTER: "view_breaches",
            page_up: "page_up",
            page_down: "page_down",
            "k": "up",
            "j": "down",
            " ": "toggle_select",
            "n": "toggle_noreply",
            "e": "export_selected",
            "/": "search",
            "s": "sort",
            "c": "copy",
            "h": "view_commits",
            "i": "insights",
            "?": "help",
            "g": "top",
            "G": "bottom",
            "q": "quit",
            "Q": "quit",
            "\x1b[A": "up",
            "\x1b[B": "down",
            "\x1b[5~": "page_up",
            "\x1b[6~": "page_down",
        }
        return mapping.get(key if key == "G" else key.lower() if len(key) == 1 else key)

    def _move(self, delta: int) -> None:
        if not self.state.filtered_records():
            return
        self.state.index += delta
        self.state.clamp_index()
        self.state.ensure_visible(self._table_window_size())
        self.state.status_message = "Selection moved"
        self.state.status_style = "green"

    def _page(self, direction: int) -> None:
        page_size = self._table_window_size()
        self.state.index += direction * page_size
        self.state.clamp_index()
        self.state.ensure_visible(page_size)
        self.state.status_message = "Page moved"
        self.state.status_style = "green"

    def _jump_to_top(self) -> None:
        self.state.index = 0
        self.state.ensure_visible(self._table_window_size())
        self.state.status_message = "Jumped to top"
        self.state.status_style = "green"

    def _jump_to_bottom(self) -> None:
        records = self.state.filtered_records()
        if not records:
            return
        self.state.index = len(records) - 1
        self.state.ensure_visible(self._table_window_size())
        self.state.status_message = "Jumped to bottom"
        self.state.status_style = "green"

    def _toggle_select(self) -> None:
        record = self.state.current_record()
        if record is None:
            self.state.status_message = "Nothing to select"
            self.state.status_style = "yellow"
            return

        if record.email in self.state.selected_emails:
            self.state.selected_emails.remove(record.email)
            self.state.status_message = f"Unselected {record.email}"
        else:
            self.state.selected_emails.add(record.email)
            self.state.status_message = f"Selected {record.email}"
        self.state.status_style = "green"

    def _toggle_github_noreply_filter(self) -> None:
        self.state.exclude_github_noreply = not self.state.exclude_github_noreply
        self.state.clamp_index()
        self.state.ensure_visible(self._table_window_size())
        mode = "hidden" if self.state.exclude_github_noreply else "shown"
        self.state.status_message = f"GitHub noreply addresses are now {mode}"
        self.state.status_style = "green"

    def _cycle_sort_mode(self) -> None:
        current_index = SORT_MODES.index(self.state.sort_mode)
        next_index = (current_index + 1) % len(SORT_MODES)
        self.state.sort_mode = SORT_MODES[next_index]
        self.state.clamp_index()
        self.state.ensure_visible(self._table_window_size())
        self.state.status_message = f"Sort mode: {SORT_LABELS[self.state.sort_mode]}"
        self.state.status_style = "green"

    def _copy_current_email(self) -> None:
        record = self.state.current_record()
        if record is None:
            self.state.status_message = "No author selected"
            self.state.status_style = "yellow"
            return

        try:
            copy_text(record.email)
        except ClipboardError as error:
            self.state.status_message = str(error)
            self.state.status_style = "red"
            return

        self.state.status_message = f"Copied {record.email}"
        self.state.status_style = "green"

    def _set_search(self, layout: Layout, live: Live) -> None:
        value = self._prompt_text(
            layout,
            live,
            title="Search Authors",
            prompt="Type a name, email, or domain. Enter applies. Q cancels.",
            initial=self.state.search_query,
        )
        if value is None:
            self.state.status_message = "Search unchanged"
            self.state.status_style = "yellow"
            return

        self.state.search_query = value.strip()
        self.state.index = 0
        self.state.scroll_offset = 0
        self.state.ensure_visible(self._table_window_size())
        label = self.state.search_query or "cleared"
        self.state.status_message = f"Search {label}"
        self.state.status_style = "green"

    def _prompt_text(
        self,
        layout: Layout,
        live: Live,
        *,
        title: str,
        prompt: str,
        initial: str = "",
    ) -> str | None:
        buffer = list(initial)
        while True:
            current = "".join(buffer)
            layout["body"].update(self._build_prompt_panel(title=title, prompt=prompt, current=current))
            layout["footer"].update(self._build_input_footer())
            live.refresh()

            key = readchar.readkey()
            if key == readchar.key.ENTER:
                return "".join(buffer)
            if key == "Q":
                return None
            if key in (readchar.key.BACKSPACE, "\x7f"):
                if buffer:
                    buffer.pop()
                continue
            if len(key) == 1 and key.isprintable():
                buffer.append(key)

    def _run_scan_loading_screen(
        self,
        layout: Layout,
        live: Live,
        *,
        repo_source: str,
        scan_service: object,
        options: object,
    ) -> tuple[str, object]:
        progress = ScanProgressState(repo_source=repo_source, stage="starting", message="Starting scan...")
        state_lock = Lock()
        spinner_frames = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")

        def on_progress(stage: str, payload: dict[str, object] | None) -> None:
            payload = payload or {}
            with state_lock:
                progress.stage = stage
                progress.message = str(payload.get("message", progress.message))
                progress.current = int(payload.get("current", progress.current) or 0)
                progress.total = int(payload.get("total", progress.total) or 0)

        def worker() -> None:
            try:
                session = scan_service.scan_with_clone(
                    repo_source,
                    options=options,
                    on_progress=on_progress,
                )
            except Exception as error:  # pragma: no cover - surfaced to the caller
                with state_lock:
                    progress.error = error
                    progress.done = True
                return

            with state_lock:
                progress.session = session
                progress.done = True

        thread = Thread(target=worker, daemon=True)
        thread.start()
        frame = 0

        while True:
            with state_lock:
                if progress.error is not None:
                    raise progress.error
                if progress.done:
                    return repo_source, progress.session
                snapshot = ScanProgressState(
                    repo_source=progress.repo_source,
                    message=progress.message,
                    stage=progress.stage,
                    current=progress.current,
                    total=progress.total,
                    done=progress.done,
                    cancelled=progress.cancelled,
                    error=progress.error,
                    session=progress.session,
                    started_at=progress.started_at,
                )

            layout["header"].update(self._render_scan_header(snapshot))
            layout["body"].update(
                self._build_loading_panel(
                    repo_source=repo_source,
                    progress=snapshot,
                    spinner=spinner_frames[frame % len(spinner_frames)],
                )
            )
            layout["footer"].update(self._build_loading_footer())
            live.refresh()
            frame += 1
            sleep(0.12)

    @staticmethod
    def _render_scan_header(progress: ScanProgressState) -> Panel:
        hero = Table.grid(expand=True)
        hero.add_column(justify="left", ratio=2)
        hero.add_column(justify="center", ratio=2)
        hero.add_column(justify="right", ratio=2)
        total = progress.total if progress.total else "-"
        current = progress.current if progress.current else 0
        hero.add_row(
            "[bold white]Scanning repository[/bold white]",
            f"[green]Checked[/green] [bold white]{current}/{total}[/bold white]",
            "[green]Page[/green] [bold white]0/0[/bold white]",
        )
        hero.add_row(
            "[green]Selected[/green] [bold white]0[/bold white]",
            f"[green]Stage[/green] [bold white]{GitEmailReconTUI._stage_label(progress.stage)}[/bold white]",
            "[green]Noreply[/green] [bold white]0[/bold white] [green](shown)[/green]",
        )
        hero.add_row(
            Text.assemble(("Search ", "green"), ("none", "bold white")),
            "",
            Text.assemble(("Status ", "green"), (progress.message, "green")),
        )

        return Panel(
            hero,
            title="[bold green]GitSnoop[/bold green]",
            border_style="green",
            box=box.HEAVY,
            style="white on black",
            padding=(0, 1),
        )

    @staticmethod
    def _build_loading_panel(
        *,
        repo_source: str,
        progress: ScanProgressState,
        spinner: str,
    ) -> Panel:
        elapsed = max(0, int(monotonic() - progress.started_at))
        eta = GitEmailReconTUI._estimate_scan_time(progress)
        percent = 0
        if progress.total > 0:
            percent = min(100, int((progress.current / progress.total) * 100))
        status_lines: list[RenderableType] = [
            Text(ascii_banner(), style="bold green"),
            Text(f"{spinner} Loading repository data...", style="bold white"),
            Text(f"Repo: {repo_source}", style="white"),
            Text(f"Elapsed: {elapsed}s", style="green"),
            Text(f"Estimated time: {eta}", style="green"),
        ]
        if progress.total > 0:
            status_lines.append(
                Text(f"Progress: {progress.current}/{progress.total} ({percent}%)", style="white")
            )
        else:
            status_lines.append(Text("Progress: starting...", style="white"))
        return Panel(
            Group(*status_lines),
            title="[bold green]Loading[/bold green]",
            border_style="green",
            style="white on black",
            box=box.ROUNDED,
            padding=(1, 2),
        )

    @staticmethod
    def _build_loading_footer() -> Panel:
        return Panel(
            Text.from_markup("[green]Please wait[/green]"),
            title="[bold green]Status[/bold green]",
            border_style="green",
            style="white on black",
            box=box.HEAVY,
        )

    @staticmethod
    def _stage_label(stage: str) -> str:
        labels = {
            "starting": "Starting",
            "clone": "Cloning repository",
            "collect": "Reading commit history",
            "breach_start": "Checking email breaches",
            "breach_progress": "Checking email breaches",
            "breach_skip": "Breach checks skipped",
            "done": "Finished",
        }
        return labels.get(stage, stage.replace("_", " ").title())

    @staticmethod
    def _estimate_scan_time(progress: ScanProgressState) -> str:
        if progress.stage == "clone":
            return "10-60s depending on repo size"
        if progress.stage in {"collect", "breach_start", "breach_progress"}:
            if progress.total > 0 and progress.current > 0:
                elapsed = monotonic() - progress.started_at
                estimated_total = elapsed * (progress.total / progress.current)
                remaining = max(1, int(estimated_total - elapsed))
                return f"about {remaining}s left"
            return "15-90s depending on email count"
        return "calculating..."

    @staticmethod
    def _build_prompt_panel(*, title: str, prompt: str, current: str) -> Panel:
        return Panel(
            Group(
                Text(ascii_banner(), style="bold green"),
                Text(prompt, style="white"),
                Text.assemble(
                    ("> ", "green"),
                    (current, "bold white"),
                    ("_", "bold green"),
                ),
            ),
            title=f"[bold green]{title}[/bold green]",
            border_style="green",
            style="white on black",
            box=box.ROUNDED,
            padding=(1, 2),
        )

    @staticmethod
    def _build_input_footer() -> Panel:
        return Panel(
            Text.from_markup(
                "[bold yellow]Enter[/bold yellow] apply   "
                "[bold red]Q[/bold red] cancel   "
                "[bold cyan]Backspace[/bold cyan] delete"
            ),
            title="[bold green]Input[/bold green]",
            border_style="green",
            style="white on black",
        )

    def _show_breach_view(self, layout: Layout, live: Live) -> None:
        record = self.state.current_record()
        if record is None:
            self.state.status_message = "No record selected"
            self.state.status_style = "yellow"
            return

        breach_result = self.state.breach_reports.get(record.email)
        if breach_result is None:
            self.state.status_message = f"No breach lookup data for {record.email}"
            self.state.status_style = "yellow"
            return

        if breach_result.error:
            self._render_breach_summary(
                layout,
                live,
                title=f"[bold green]Breach Details for {record.name}[/bold green]",
                body=Group(
                    Text(f"Email: {record.email}", style="bold white"),
                    Text(f"Lookup failed: {breach_result.error}", style="bold red"),
                ),
            )
        elif not breach_result.is_breached:
            self._render_breach_summary(
                layout,
                live,
                title=f"[bold green]Breach Details for {record.name}[/bold green]",
                body=Group(
                    Text(f"Email: {record.email}", style="bold white"),
                    Text("No breaches found.", style="bold green"),
                ),
            )
        else:
            self._show_breach_table(layout, live, record.name, record.email, breach_result)
        if breach_result.error:
            self.state.status_message = f"Breach lookup failed for {record.email}"
            self.state.status_style = "red"
        elif breach_result.is_breached:
            self.state.status_message = f"Loaded breach details for {record.email}"
            self.state.status_style = "green"
        else:
            self.state.status_message = f"No breaches found for {record.email}"
            self.state.status_style = "green"

    def _show_commit_view(self, layout: Layout, live: Live) -> None:
        record = self.state.current_record()
        if record is None:
            self.state.status_message = "No record selected"
            self.state.status_style = "yellow"
            return

        commits = self.client.commits_by_author(record.email)
        offset = 0
        cursor = 0
        window_size = max(8, self.console.size.height - 17)

        while True:
            visible_commits = commits[offset : offset + window_size]
            commit_table = Table(
                expand=True,
                show_header=True,
                header_style="bold green",
                box=box.SIMPLE_HEAVY,
                row_styles=["white on black", "white on color(232)"],
            )
            commit_table.add_column("Recent commits", style="white")

            if visible_commits:
                for index, commit in enumerate(visible_commits):
                    row_style = "bold white on green" if index == cursor else ""
                    commit_table.add_row(commit, style=row_style)
            else:
                commit_table.add_row("No commits found.")

            top_indicator = (
                Text.from_markup("[bold green]▲ more above[/bold green]")
                if offset > 0
                else Text(" ", style="white")
            )
            bottom_indicator = (
                Text.from_markup("[bold green]▼ more below[/bold green]")
                if offset + window_size < len(commits)
                else Text(" ", style="white")
            )
            summary = Text.from_markup(
                f"[green]Author[/green] [bold white]{record.name}[/bold white]   "
                f"[green]Commits[/green] [bold white]{record.commit_count}[/bold white]   "
                f"[green]First[/green] [bold white]{record.first_seen.isoformat()}[/bold white]   "
                f"[green]Last[/green] [bold white]{record.last_seen.isoformat()}[/bold white]"
            )
            stats = Text.from_markup(
                f"[green]Showing[/green] [bold white]{offset + 1 if commits else 0}-"
                f"{min(len(commits), offset + window_size)}[/bold white] "
                f"[green]of[/green] [bold white]{len(commits)}[/bold white]"
            )

            layout["body"].update(
                Panel(
                    Group(summary, top_indicator, commit_table, bottom_indicator, stats),
                    title=f"[bold green]Commits by {record.email}[/bold green]",
                    border_style="green",
                    style="white on black",
                    box=box.ROUNDED,
                    padding=(0, 1),
                )
            )
            layout["footer"].update(
                Panel(
                    Text.from_markup(
                        "[bold cyan]↑/↓[/bold cyan] scroll   "
                        "[bold cyan]PgUp/PgDn[/bold cyan] page   "
                        "[bold white]c[/bold white] copy line   "
                        "[bold yellow]b[/bold yellow] return   "
                        "[bold green]Keyboard copy replaces mouse selection in fullscreen mode[/bold green]"
                    ),
                    border_style="green",
                    style="white on black",
                    title="[bold green]Viewer[/bold green]",
                    box=box.HEAVY,
                )
            )
            live.refresh()

            key = readchar.readkey()
            action = self._normalize_key(key)
            max_offset = max(0, len(commits) - window_size)
            visible_max_cursor = max(0, len(visible_commits) - 1)
            cursor = min(cursor, visible_max_cursor)

            if key.lower() == "b" or key == "Q":
                break
            if action == "copy":
                if visible_commits:
                    self._copy_commit_line(visible_commits[cursor])
                else:
                    self.state.status_message = "No commit line to copy"
                    self.state.status_style = "yellow"
                continue
            if action == "down" and visible_commits:
                if cursor < visible_max_cursor:
                    cursor += 1
                elif offset < max_offset:
                    offset += 1
                continue
            if action == "up" and visible_commits:
                if cursor > 0:
                    cursor -= 1
                elif offset > 0:
                    offset -= 1
                continue
            if action == "page_down" and offset < max_offset:
                offset = min(max_offset, offset + window_size)
                cursor = min(cursor, max(0, len(commits[offset : offset + window_size]) - 1))
                continue
            if action == "page_up" and offset > 0:
                offset = max(0, offset - window_size)
                cursor = min(cursor, max(0, len(commits[offset : offset + window_size]) - 1))
                continue

        self.state.status_message = f"Loaded commits for {record.email}"
        self.state.status_style = "green"

    def _copy_commit_line(self, line: str) -> None:
        try:
            copy_text(line)
        except ClipboardError as error:
            self.state.status_message = str(error)
            self.state.status_style = "red"
            return

        self.state.status_message = "Copied commit line"
        self.state.status_style = "green"

    def _show_domain_insights(self, layout: Layout, live: Live) -> None:
        records = self.state.filtered_records()
        aggregated: dict[str, dict[str, int]] = defaultdict(lambda: {"authors": 0, "commits": 0, "noreply": 0})
        for record in records:
            stats = aggregated[record.domain or "(unknown)"]
            stats["authors"] += 1
            stats["commits"] += record.commit_count
            stats["noreply"] += int(record.is_github_noreply)

        insight_table = Table(expand=True, header_style="bold green", box=box.SIMPLE_HEAVY)
        insight_table.add_column("Domain", style="bold white")
        insight_table.add_column("Authors", justify="right", style="white")
        insight_table.add_column("Commits", justify="right", style="white")
        insight_table.add_column("Noreply", justify="right", style="white")

        ranked = sorted(
            aggregated.items(),
            key=lambda item: (-item[1]["authors"], -item[1]["commits"], item[0]),
        )
        for domain, stats in ranked[:12]:
            insight_table.add_row(
                domain,
                str(stats["authors"]),
                str(stats["commits"]),
                str(stats["noreply"]),
            )

        summary = Text.from_markup(
            f"[green]Domains[/green] [bold white]{len(aggregated)}[/bold white]   "
            f"[green]Visible authors[/green] [bold white]{len(records)}[/bold white]   "
            f"[green]Visible commits[/green] [bold white]{sum(record.commit_count for record in records)}[/bold white]"
        )
        layout["body"].update(
            Panel(
                Group(summary, insight_table),
                title="[bold green]Domain Insights[/bold green]",
                border_style="green",
                style="white on black",
                box=box.ROUNDED,
                padding=(0, 1),
            )
        )
        layout["footer"].update(
            Panel(
                Text.from_markup("[bold yellow]Press b[/bold yellow] or [bold red]Q[/bold red] to return"),
                border_style="green",
                style="white on black",
                title="[bold green]Insights[/bold green]",
                box=box.HEAVY,
            )
        )
        live.refresh()
        self._wait_for_back()
        self.state.status_message = "Viewed domain insights"
        self.state.status_style = "green"

    def _show_help(self, layout: Layout, live: Live) -> None:
        help_lines = [
            "[bold cyan]↑/↓[/bold cyan] Move one row",
            "[bold cyan]PgUp/PgDn[/bold cyan] Move one page",
            "[bold green]space[/bold green] Select highlighted author",
            "[bold yellow]enter[/bold yellow] View breach details for the highlighted author",
            "[bold cyan]h[/bold cyan] Open commit history and author stats",
            "[bold magenta]/[/bold magenta] Search by name, email, or domain",
            "[bold blue]s[/bold blue] Cycle sort mode",
            "[bold white]c[/bold white] Copy highlighted email or commit line to clipboard",
            "[bold magenta]n[/bold magenta] Toggle GitHub noreply visibility",
            "[bold cyan]i[/bold cyan] Open domain insights panel",
            "[bold blue]g/G[/bold blue] Jump to top or bottom",
            "[bold green]e[/bold green] Export selected visible rows",
            "[bold yellow]b[/bold yellow] Return from detail panels",
            "[bold red]q[/bold red] Quit and write current visible results",
        ]
        if self.state.compact_help:
            help_lines = help_lines[:8]

        help_group = Group(*(Text.from_markup(line) for line in help_lines))
        layout["body"].update(
            Panel(
                help_group,
                title="[bold green]Help[/bold green]",
                border_style="green",
                style="white on black",
                box=box.ROUNDED,
                padding=(1, 2),
            )
        )
        layout["footer"].update(
            Panel(
                Text.from_markup("[bold yellow]Press b[/bold yellow] or [bold red]Q[/bold red] to return"),
                border_style="green",
                style="white on black",
                title="[bold green]Help[/bold green]",
                box=box.HEAVY,
            )
        )
        live.refresh()
        self._wait_for_back()
        self.state.status_message = "Viewed help"
        self.state.status_style = "green"

    def _export_selected(self, layout: Layout, live: Live) -> None:
        visible_records = self.state.filtered_records()
        export_records = [
            record for record in visible_records if record.email in self.state.selected_emails
        ]
        if not export_records:
            self.state.status_message = "Select at least one visible email before exporting"
            self.state.status_style = "yellow"
            return

        output_path = self.state.selected_output_path
        export_selected_records(
            output_path,
            repository=self.state.repo_name,
            records=export_records,
            breach_reports=self.state.breach_reports,
            include_breach_details=self.state.include_breach_details,
        )
        layout["body"].update(
            Panel(
                Group(
                    Text(
                        f"Exported {len(export_records)} selected authors",
                        style="bold green",
                    ),
                    Text(f"Path: {output_path}", style="white"),
                ),
                title="[bold green]Export complete[/bold green]",
                border_style="green",
                style="white on black",
                box=box.ROUNDED,
                padding=(1, 2),
            )
        )
        layout["footer"].update(
            Panel(
                Text.from_markup("[bold yellow]Press b[/bold yellow] or [bold red]Q[/bold red] to continue"),
                border_style="green",
                style="white on black",
                title="[bold green]Export[/bold green]",
                box=box.HEAVY,
            )
        )
        live.refresh()
        self._wait_for_back()
        self.state.status_message = f"Exported {len(export_records)} selected emails"
        self.state.status_style = "green"

    def _show_breach_table(
        self,
        layout: Layout,
        live: Live,
        name: str,
        email: str,
        breach_result: BreachLookupResult,
    ) -> None:
        breaches = breach_result.breaches
        offset = 0
        window_size = self._breach_window_size()

        while True:
            window_size = self._breach_window_size()
            visible_breaches = breaches[offset : offset + window_size]
            breach_table = Table(
                expand=True,
                show_header=True,
                header_style="bold green",
                box=box.SIMPLE_HEAVY,
                row_styles=["white on black", "white on color(232)"],
            )
            breach_table.add_column("Breach", style="bold white", ratio=2, no_wrap=True, overflow="ellipsis")
            breach_table.add_column("Domain", style="green", ratio=2, no_wrap=True, overflow="ellipsis")
            breach_table.add_column("Date", width=10, style="white", no_wrap=True)
            breach_table.add_column("Records", justify="right", style="white", width=12, no_wrap=True)
            breach_table.add_column("Exposed Data", ratio=4, style="white", no_wrap=True, overflow="ellipsis")

            for breach in visible_breaches:
                breach_table.add_row(
                    breach.title,
                    breach.domain or "-",
                    breach.breach_date,
                    f"{breach.pwn_count:,}",
                    ", ".join(breach.data_classes) or "-",
                )

            top_indicator = (
                Text.from_markup("[bold green]▲ more above[/bold green]")
                if offset > 0
                else Text(" ", style="white")
            )
            bottom_indicator = (
                Text.from_markup("[bold green]▼ more below[/bold green]")
                if offset + window_size < len(breaches)
                else Text(" ", style="white")
            )
            summary = Text.from_markup(
                f"[green]Email[/green] [bold white]{email}[/bold white]   "
                f"[green]Breaches[/green] [bold white]{len(breaches)}[/bold white]"
            )
            stats = Text.from_markup(
                f"[green]Showing[/green] [bold white]{offset + 1}-{min(len(breaches), offset + window_size)}[/bold white] "
                f"[green]of[/green] [bold white]{len(breaches)}[/bold white]   "
                f"[green]Page size[/green] [bold white]{window_size}[/bold white]"
            )

            layout["body"].update(
                Panel(
                    Group(summary, top_indicator, breach_table, bottom_indicator, stats),
                    title=f"[bold green]Breach Details for {name}[/bold green]",
                    border_style="green",
                    style="white on black",
                    box=box.ROUNDED,
                    padding=(0, 1),
                )
            )
            layout["footer"].update(
                Panel(
                    Text.from_markup(
                        "[bold cyan]↑/↓[/bold cyan] scroll   "
                        "[bold cyan]PgUp/PgDn[/bold cyan] page   "
                        "[bold yellow]b[/bold yellow] return"
                    ),
                    border_style="green",
                    style="white on black",
                    title="[bold green]Breaches[/bold green]",
                    box=box.HEAVY,
                )
            )
            live.refresh()

            key = readchar.readkey()
            action = self._normalize_key(key)
            max_offset = max(0, len(breaches) - window_size)

            if key.lower() == "b" or key == "Q":
                return
            if action == "down" and offset < max_offset:
                offset += 1
                continue
            if action == "up" and offset > 0:
                offset -= 1
                continue
            if action == "page_down" and offset < max_offset:
                offset = min(max_offset, offset + window_size)
                continue
            if action == "page_up" and offset > 0:
                offset = max(0, offset - window_size)
                continue

    def _render_breach_summary(
        self,
        layout: Layout,
        live: Live,
        *,
        title: str,
        body: RenderableType,
    ) -> None:
        layout["body"].update(
            Panel(
                body,
                title=title,
                border_style="green",
                style="white on black",
                box=box.ROUNDED,
                padding=(1, 2),
            )
        )
        layout["footer"].update(
            Panel(
                Text.from_markup("[bold yellow]Press b[/bold yellow] or [bold red]Q[/bold red] to return"),
                border_style="green",
                style="white on black",
                title="[bold green]Breaches[/bold green]",
                box=box.HEAVY,
            )
        )
        live.refresh()
        self._wait_for_back()

    def _breach_window_size(self) -> int:
        return max(4, self.console.size.height - 18)

    def _wait_for_back(self) -> None:
        while True:
            key = readchar.readkey()
            action = self._normalize_key(key)
            if key.lower() == "b" or key == "Q" or action in {"view_commits", "help"}:
                return
