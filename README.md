
![ascii-art](.media/ascii-art-text.png)

                                                                
GitSnoop extracts git author emails with an interactive TUI.


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
usage: gitsnoop [-h] [-o OUTPUT] [--config CONFIG] [--exclude-github-noreply] [--no-tui] [remote-repo | /absolute/path/to/local/repo]


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
                                                                                         
```

If you start gitsnoop with no arguments, it will ask for the repository URL or local path inside the TUI.

## Use cases

GitSnoop is an OSINT starter for measuring developer exposure. One email in commit history is often enough. Enough to connect a person to old usernames, public profiles, forgotten accounts, and breach data that never really disappeared.

That is why this matters in supply chain security. The first move is not always malware. Not always a zero day. Sometimes it is one believable phishing link delivered to the one developer whose history made them easy to identify, profile, and pressure.

And this is the part teams get wrong: cleaning up your setup today does not clean up your history. You can use a dedicated Git email on every new repo and still have old commits telling the real story. If that metadata is still in the graph, assume it can be correlated, enriched, and used as a stepping stone.


## Config

GitSnoop stores its config at `~/.config/gitsnoop/config.json`. Customize that `config.json` file according to your liking. On first run, GitSnoop creates it with sensible defaults.

By default, exported JSON files go to `~/.config/gitsnoop/output/`. You can change that by editing `output_dir` in `config.json`, and you can bypass it for a single run with `--output`.

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
- `Enter` shows recent commits for the highlighted author.
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
