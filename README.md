
![ascii-art](.media/ascii-art-text.png)

                                                                
GitSnoop extracts git author emails with a TUI, and optional data breach checks. No API key needed.


## How It Works

GitSnoop is not doing any black magic behind the scenes. Git commits already store author metadata, and that usually includes the author name and email address. If that data exists in the repository history, `git log` can print it back out.

Under the hood, GitSnoop is basically automating this kind of query:

```bash
git log --format='%an <%ae>'
```

That means the tool is not "finding" hidden emails so much as reading commit metadata that is already present in the repo. If someone used a personal email when they committed, and that commit is still in the history, the address is recoverable by anyone who has the repository. GitSnoop just collects those entries, groups them, and makes them easier to inspect.

If you want the underlying Git behavior - https://git-scm.com/docs/git-log

## Install

Install with UV :

```bash
uv tool install git+https://github.com/AegisTrail/GitSnoop.git
```

## Usage

![Usage](.media/gitsnoop.gif)


```bash
> $ gitsnoop --help                                                                                                                                        
usage: gitsnoop [-h] [-o OUTPUT] [--config CONFIG] [--exclude-github-noreply] [--no-tui] [--selected-output SELECTED_OUTPUT] [--skip-breach-checks] [--no-breach-details] [remote-repo | /absolute/path/to/local/repo]


 ██████  ██ ████████ ███████ ███    ██  ██████   ██████  ██████
██       ██    ██    ██      ████   ██ ██    ██ ██    ██ ██   ██
██   ███ ██    ██    ███████ ██ ██  ██ ██    ██ ██    ██ ██████
██    ██ ██    ██         ██ ██  ██ ██ ██    ██ ██    ██ ██
 ██████  ██    ██    ███████ ██   ████  ██████   ██████  ██

GitSnoop extracts git author emails with a stable interactive TUI.

positional arguments:
  repo                  Git repository URL or local path

options:
  -h, --help            show this help message and exit
  -o OUTPUT, --output OUTPUT
                        Output JSON file name
  --config CONFIG       Optional JSON config file path.
  --exclude-github-noreply
                        Exclude *@users.noreply.github.com addresses from the initial results.
  --no-tui              Run only the CLI export without opening the interactive TUI.
  --selected-output SELECTED_OUTPUT
                        Output JSON file for TUI-selected rows. Defaults to <output_dir>/<repo>_selected_emails.json.
  --skip-breach-checks  Skip breach lookups and omit live breach status in the TUI.
  --no-breach-details   Do not write breach metadata into exported JSON output.
  --api                 Run the FastAPI server.
  --port PORT           Port for the API server when --api is used. Defaults to 6969.
                                                                                         
```

If you start gitsnoop with no arguments, it will ask for the repository URL or local path inside the TUI.

## API

GitSnoop also includes an HTTP API.

Start the API server with:

```bash
gitsnoop --api
```

By default, the API runs on:

```text
http://127.0.0.1:6969
```

Once the server is running, you can open the interactive Swagger API docs here:

```text
http://127.0.0.1:6969/docs
```

The OpenAPI JSON is available here:

```text
http://127.0.0.1:6969/openapi.json
```

For full API details, request examples, and response format, see [api-docs.md](api-docs.md).

## Use cases

From a supply chain attacker point of view, commit history is a starting point for target selection.

An exposed email can be enough to identify which developer is worth following. From there, an attacker can connect that person to public profiles, old usernames, breach records, and other public traces. That makes it easier to build a believable phishing message or a fake support request.

The goal is not always to attack the repository directly. In many cases, the easier path is to reach the person who has access to source code, CI, package publishing, secrets, or release systems.

That is where GitSnoop is useful for defenders. It shows what an attacker can learn from commit metadata before any exploit is used.

GitSnoop can also run as a service with the built-in FastAPI server. That makes it easier to plug scans into internal tools, dashboards, or automation jobs over HTTP.

Teams can use the results to review old identity exposure, spot risky addresses, and improve future Git setup and commit practices.


## Config

GitSnoop stores its config at `~/.config/gitsnoop/config.json`. Customize that `config.json` file according to your liking. On first run, GitSnoop creates it with sensible defaults.

By default, exported JSON files go to `~/.config/gitsnoop/output/`. You can change that by editing `output_dir` in `config.json`, bypass the main export path for a single run with `--output`, and override the selected-row export path with `--selected-output`. Main and selected exports now include breach status, breach counts, API errors, and per-breach details unless you pass `--no-breach-details`.

```json
{
  "exclude_github_noreply": false,
  "sort_mode": "commits",
  "compact_help": false,
  "output_dir": "~/.config/gitsnoop/output"
}
```

## TUI

The interface supports search, sort modes, paging, commit inspection, clipboard copy, domain insights, and filtered export.

- `Up/Down` or `j/k` move selection.
- `PgUp/PgDn` move by page.
- `Space` selects or unselects an email.
- `Enter` opens breach details for the highlighted author.
- Inside breach details, `Up/Down` and `PgUp/PgDn` scroll through the full breach list.
- `h` shows recent commits for the highlighted author.
- `/` searches by name, email, or domain.
- `s` cycles sort modes.
- `c` copies the highlighted email to the clipboard.
- `n` toggles GitHub noreply filtering.
- `i` opens domain insights.
- `g` / `G` jump to top or bottom.
- `e` exports selected visible emails.
- `q` quits and writes the current visible result set to the main output file.


## License

![License: MIT](.media/mit-license.png)
