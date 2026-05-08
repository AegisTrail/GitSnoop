from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from config import load_config
from exporter import export_email_records
from filters import apply_email_filters
from git_client import GitCommandError, GitRepositoryClient
from tui import GitEmailReconTUI, sort_records

console = Console()


def extract_repo_name(repo_url: str) -> str:
    name = repo_url.rstrip("/").split("/")[-1]
    return name.removesuffix(".git")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="GitSnoop extracts git author emails with an interactive TUI."
    )
    parser.add_argument("repo", nargs="?", help="Git repository URL or local path")
    parser.add_argument("-o", "--output", help="Output JSON file name", default=None)
    parser.add_argument(
        "--config",
        help="Optional JSON config file path.",
        default=None,
    )
    parser.add_argument(
        "--exclude-github-noreply",
        action="store_true",
        help="Exclude *@users.noreply.github.com addresses from the initial results.",
    )
    parser.add_argument(
        "--no-tui",
        action="store_true",
        help="Run only the CLI export without opening the interactive TUI.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.no_tui and not args.repo:
        parser.error("repo is required when --no-tui is used")

    config = load_config(Path(args.config) if args.config else None)
    repo_url = args.repo or GitEmailReconTUI.prompt_for_repo_url()
    if not repo_url:
        console.print(
            Panel.fit(
                "[bold red]No repository provided[/bold red]\n"
                "GitSnoop needs a git repository URL or local path to continue.",
                border_style="red",
            )
        )
        return 1

    repo_name = extract_repo_name(repo_url)
    output_path = (
        Path(args.output).expanduser()
        if args.output
        else config.output_dir / f"{repo_name}_emails.json"
    )
    exclude_github_noreply = args.exclude_github_noreply or config.exclude_github_noreply

    console.print(
        Panel.fit(
            f"[bold green]GitSnoop[/bold green]\n"
            f"[white]Repo:[/white] {repo_url}\n"
            f"[white]Output:[/white] {output_path}\n"
            f"[white]Output dir:[/white] {config.output_dir}\n"
            f"[white]GitHub noreply filter:[/white] "
            f"{'enabled' if exclude_github_noreply else 'disabled'}\n"
            f"[white]Sort:[/white] {config.sort_mode}",
            border_style="green",
        )
    )

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir) / repo_name
            client = GitRepositoryClient(repo_path)

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
                transient=True,
            ) as progress:
                task = progress.add_task("Cloning repository...", start=True)
                client.run("git", "clone", repo_url, str(repo_path), cwd=Path(tmpdir))
                progress.update(task, description="Collecting author emails...")
                all_records = client.collect_emails()

            records = apply_email_filters(
                all_records,
                exclude_github_noreply=exclude_github_noreply,
            )
            records = sort_records(records, config.sort_mode)

            if not args.no_tui:
                tui = GitEmailReconTUI(
                    records=all_records,
                    repo_name=repo_name,
                    repo_path=repo_path,
                    output_dir=config.output_dir,
                    initial_exclude_github_noreply=exclude_github_noreply,
                    initial_sort_mode=config.sort_mode,
                    compact_help=config.compact_help,
                )
                result = tui.run()
                records = result.visible_records

            export_email_records(
                output_path,
                repository=repo_name,
                records=records,
            )

    except GitCommandError as error:
        console.print(
            Panel.fit(
                f"[bold red]Git command failed[/bold red]\n{error}",
                border_style="red",
            )
        )
        return 1

    console.print(
        Panel.fit(
            f"[bold green]Completed[/bold green]\n"
            f"Saved {len(records)} emails to [cyan]{output_path}[/cyan]",
            border_style="green",
        )
    )
    return 0
