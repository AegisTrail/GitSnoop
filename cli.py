from __future__ import annotations

import argparse
import sys
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parent
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

from rich.console import Console
from rich.panel import Panel
from branding import ascii_banner
from config import load_config
from exporter import export_email_records
from git_client import GitCommandError
from scan_service import RepositoryScanService, ScanOptions, extract_repo_name
from tui import GitEmailReconTUI

console = Console()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            f"{ascii_banner()}\n\n"
            "GitSnoop extracts git author emails with an interactive TUI."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
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
    parser.add_argument(
        "--selected-output",
        help="Output JSON file for TUI-selected rows. Defaults to <output_dir>/<repo>_selected_emails.json.",
        default=None,
    )
    parser.add_argument(
        "--skip-breach-checks",
        action="store_true",
        help="Skip breach lookups.",
    )
    parser.add_argument(
        "--no-breach-details",
        action="store_true",
        help="Do not write breach metadata into exported JSON output.",
    )
    parser.add_argument(
        "--api",
        action="store_true",
        help="Run the FastAPI server.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=6969,
        help="Port for the API server when --api is used. Defaults to 6969.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.api:
        if args.no_tui:
            parser.error("--no-tui cannot be used together with --api")
        _run_api_server(args.port)
        return 0
    if args.no_tui and not args.repo:
        parser.error("repo is required when --no-tui is used")

    config = load_config(Path(args.config) if args.config else None)
    exclude_github_noreply = args.exclude_github_noreply or config.exclude_github_noreply
    include_breach_details = not args.no_breach_details

    try:
        scan_service = RepositoryScanService()
        scan_options = ScanOptions(
            exclude_github_noreply=exclude_github_noreply,
            sort_mode=config.sort_mode,
            skip_breach_checks=args.skip_breach_checks,
        )
        if args.no_tui:
            repo_url = args.repo
            repo_name = extract_repo_name(repo_url)
            output_path = (
                Path(args.output).expanduser()
                if args.output
                else config.output_dir / f"{repo_name}_emails.json"
            )
            selected_output_path = (
                Path(args.selected_output).expanduser()
                if args.selected_output
                else config.output_dir / f"{repo_name}_selected_emails.json"
            )
            session_manager = scan_service.scan_with_clone(repo_url, options=scan_options)
        else:
            prompt_result = GitEmailReconTUI.prompt_for_repo_and_scan(
                scan_service=scan_service,
                options=scan_options,
                initial_repo_source=args.repo,
            )
            if prompt_result is None:
                console.print(
                    Panel.fit(
                        "[bold red]No repository provided[/bold red]\n"
                        "GitSnoop needs a git repository URL or local path to continue.",
                        border_style="red",
                    )
                )
                return 1
            repo_url, session_manager = prompt_result
            repo_name = extract_repo_name(repo_url)
            output_path = (
                Path(args.output).expanduser()
                if args.output
                else config.output_dir / f"{repo_name}_emails.json"
            )
            selected_output_path = (
                Path(args.selected_output).expanduser()
                if args.selected_output
                else config.output_dir / f"{repo_name}_selected_emails.json"
            )

        with session_manager as session:
            scan_result = session.result
            records = scan_result.records
            breach_reports = scan_result.breach_reports

            if not args.no_tui:
                tui = GitEmailReconTUI(
                    records=scan_result.all_records,
                    repo_name=repo_name,
                    repo_path=session.repo_path,
                    output_dir=config.output_dir,
                    selected_output_path=selected_output_path,
                    initial_exclude_github_noreply=exclude_github_noreply,
                    initial_sort_mode=config.sort_mode,
                    compact_help=config.compact_help,
                    breach_reports=breach_reports,
                    include_breach_details=include_breach_details,
                )
                result = tui.run()
                records = result.visible_records

            export_email_records(
                output_path,
                repository=repo_name,
                records=records,
                breach_reports=breach_reports,
                include_breach_details=include_breach_details,
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


def _run_api_server(port: int) -> None:
    if port <= 0 or port > 65535:
        raise SystemExit("API port must be between 1 and 65535.")

    from api_runner import APIServerRunner

    APIServerRunner(port=port).run()
