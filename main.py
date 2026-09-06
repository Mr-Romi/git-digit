#!/usr/bin/env python3
"""git-digit: Analyze git repository commit history and developer sentiment."""

import argparse
import io
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime

import git
import requests
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from textblob import TextBlob

# Force UTF-8 on Windows (default cp1252 crashes on non-ASCII author names)
console = Console(file=io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace"))

UNKNOWN_AUTHOR = "<unknown>"
GITHUB_API     = "https://api.github.com"
GITHUB_URL_RE  = re.compile(r"^(?:https?://github\.com/|github\.com/)([^/]+)/([^/\s]+?)(?:\.git)?/?$")


# ── Helpers ───────────────────────────────────────────────────────────────────

def sentiment_label(p: float) -> str:
    return "[bold green]+ Positive[/bold green]" if p > 0.3 else "[bold red]- Negative[/bold red]" if p < -0.3 else "[bold yellow]~ Neutral[/bold yellow]"

def mood_bar(p: float) -> str:
    n = max(0, min(10, int((max(-1.0, min(1.0, p)) + 1) / 2 * 10)))
    return f"[green]{'#' * n}[/green][dim]{'-' * (10 - n)}[/dim]"

def parse_github_url(v: str):
    """Return (owner, repo) for a GitHub URL, else None."""
    m = GITHUB_URL_RE.match(v.strip())
    return (m.group(1), m.group(2)) if m else None

def _commit_table(title: str, has_files: bool) -> Table:
    """Build a standard commit history Rich table."""
    t = Table(title=f"[bold]{title}[/bold]", box=box.ROUNDED, show_lines=False, header_style="bold magenta")
    t.add_column("Hash",    style="dim",     width=9,  no_wrap=True)
    t.add_column("Author",  style="cyan",    min_width=14, no_wrap=True)
    t.add_column("Date",    style="magenta", width=12, no_wrap=True)
    t.add_column("Hr",      justify="center",width=4,  no_wrap=True)
    if has_files:
        t.add_column("Files", justify="right", width=6, no_wrap=True)
    t.add_column("Mood",    min_width=12,    no_wrap=True)
    t.add_column("Bar",     min_width=12,    no_wrap=True)
    t.add_column("Message", min_width=30,    no_wrap=True, overflow="fold")
    return t

def _render_dev_table(author_data: dict, has_files: bool) -> None:
    """Print the developer summary table."""
    t = Table(title="[bold]Developer Summary[/bold]", box=box.ROUNDED, show_lines=False, header_style="bold magenta")
    t.add_column("Author",       style="cyan",    no_wrap=True)
    t.add_column("Commits",      justify="right", no_wrap=True)
    t.add_column("Avg Polarity", justify="right", no_wrap=True)
    t.add_column("Sentiment",    min_width=14,    no_wrap=True)
    t.add_column("Mood Bar",     min_width=12,    no_wrap=True)
    if has_files:
        t.add_column("Files Touched", justify="right", no_wrap=True)
    for author, d in sorted(author_data.items(), key=lambda x: -x[1]["count"]):
        avg = d["polarity_sum"] / d["count"]
        row = [author, str(d["count"]), f"{avg:+.3f}", sentiment_label(avg), mood_bar(avg)]
        if has_files:
            row.append(str(d["files"]))
        t.add_row(*row)
    console.print(t)

def _render_summary(total: int, hour_counter: Counter, zombie_commits: int, total_polarity: float) -> None:
    """Print the summary panel."""
    peak     = f"{hour_counter.most_common(1)[0][0]:02d}:00" if hour_counter else "N/A"
    mood     = total_polarity / total if total else 0.0
    owl      = " [red]<-- night owl alert![/red]" if zombie_commits else ""
    console.print(Panel(
        f"[bold white]Total Commits Analyzed:[/bold white] [cyan]{total}[/cyan]\n"
        f"[bold white]Peak Activity Hour:    [/bold white] [cyan]{peak}[/cyan]\n"
        f"[bold white]Zombie Commits (1-5AM):[/bold white] [cyan]{zombie_commits}[/cyan]{owl}\n"
        f"[bold white]Overall Repo Mood:     [/bold white] [cyan]{mood:+.3f}[/cyan]  {sentiment_label(mood)}\n"
        f"[bold white]Mood Bar:              [/bold white] {mood_bar(mood)}",
        title="[bold cyan]Summary[/bold cyan]", expand=False, border_style="cyan"
    ))


# ── GitHub API mode ───────────────────────────────────────────────────────────

def analyze_github(owner: str, repo: str, limit: int, branch: str, token: str = None) -> None:
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    console.print(Panel(
        f"[bold cyan]git-digit[/bold cyan]  GitHub API Mode\n"
        f"[dim]Repo:[/dim] [white]github.com/{owner}/{repo}[/white]  "
        f"[dim]Branch:[/dim] [white]{branch}[/white]  [dim]Limit:[/dim] [white]{limit}[/white]",
        expand=False, border_style="cyan"
    ))

    commits, page, ref = [], 1, (None if branch == "HEAD" else branch)
    with console.status("[cyan]Fetching commits from GitHub API...[/cyan]"):
        while len(commits) < limit:
            params = {"per_page": min(100, limit - len(commits)), "page": page}
            if ref:
                params["sha"] = ref
            resp = requests.get(f"{GITHUB_API}/repos/{owner}/{repo}/commits", headers=headers, params=params, timeout=10)
            if resp.status_code == 404:
                console.print(f"[bold red]Error:[/bold red] Repo '{owner}/{repo}' not found or is private.")
                sys.exit(1)
            if resp.status_code == 403:
                console.print("[bold red]Error:[/bold red] Rate limit hit. Use --token to authenticate.")
                sys.exit(1)
            if resp.status_code != 200:
                console.print(f"[bold red]GitHub API error {resp.status_code}:[/bold red] {resp.text[:200]}")
                sys.exit(1)
            batch = resp.json()
            if not batch:
                break
            commits.extend(batch)
            if len(batch) < params["per_page"]:
                break
            page += 1

    if not commits:
        console.print("[yellow]No commits found.[/yellow]")
        return

    console.print(f"[dim]GitHub API rate limit remaining: {resp.headers.get('X-RateLimit-Remaining', '?')}/60[/dim]\n")

    hour_counter  = Counter()
    author_data   = defaultdict(lambda: {"count": 0, "polarity_sum": 0.0})
    zombie_commits = 0
    total_polarity = 0.0
    tbl = _commit_table("Commit History (GitHub)", has_files=False)

    for raw in commits:
        try:
            sha    = raw["sha"][:7]
            msg    = raw["commit"]["message"].strip().splitlines()[0]
            author = raw["commit"]["author"].get("name") or UNKNOWN_AUTHOR
            date_s = raw["commit"]["author"].get("date", "")
            dt     = datetime.fromisoformat(date_s.replace("Z", "+00:00")) if date_s else datetime.utcnow()
        except (KeyError, ValueError, AttributeError):
            continue

        hour = dt.hour
        pol  = TextBlob(msg).sentiment.polarity
        hour_counter[hour] += 1
        author_data[author]["count"] += 1
        author_data[author]["polarity_sum"] += pol
        total_polarity += pol
        if 1 <= hour <= 5:
            zombie_commits += 1
        tbl.add_row(sha, author, dt.strftime("%Y-%m-%d"), f"{hour:02d}", sentiment_label(pol), mood_bar(pol), msg)

    console.print(tbl)
    _render_dev_table(author_data, has_files=False)
    _render_summary(len(commits), hour_counter, zombie_commits, total_polarity)


# ── Local Git mode ────────────────────────────────────────────────────────────

def analyze_repo(repo_path: str, limit: int, branch: str) -> None:
    try:
        repo = git.Repo(repo_path, search_parent_directories=True)
    except git.InvalidGitRepositoryError:
        console.print(f"[bold red]Error:[/bold red] '{repo_path}' is not a valid git repository.")
        sys.exit(1)
    except git.NoSuchPathError:
        console.print(f"[bold red]Error:[/bold red] Path '{repo_path}' does not exist.")
        sys.exit(1)
    except Exception as e:
        console.print(f"[bold red]Unexpected error:[/bold red] {e}")
        sys.exit(1)

    if not branch or not branch.strip():
        console.print("[bold red]Error:[/bold red] Branch name cannot be empty.")
        sys.exit(1)

    console.print(Panel(
        f"[bold cyan]git-digit[/bold cyan]  Commit Sentiment Analyzer\n"
        f"[dim]Repo:[/dim] [white]{repo_path}[/white]  "
        f"[dim]Branch:[/dim] [white]{branch}[/white]  [dim]Limit:[/dim] [white]{limit}[/white]",
        expand=False, border_style="cyan"
    ))

    try:
        commits = list(repo.iter_commits(branch, max_count=limit))
    except git.GitCommandError:
        console.print(
            f"[bold red]Error:[/bold red] Branch [yellow]'{branch}'[/yellow] does not exist.\n"
            f"[dim]Tip: run [white]git branch -a[/white] to list available branches.[/dim]"
        )
        sys.exit(1)

    if not commits:
        console.print("[yellow]No commits found on this branch.[/yellow]")
        return

    hour_counter   = Counter()
    author_data    = defaultdict(lambda: {"count": 0, "polarity_sum": 0.0, "files": 0})
    zombie_commits = 0
    total_polarity = 0.0
    tbl = _commit_table("Commit History", has_files=True)

    for c in commits:
        try:
            dt     = c.committed_datetime
        except Exception:
            dt     = datetime.utcnow()
        author = (getattr(c.author, "name", None) or UNKNOWN_AUTHOR)
        msg    = (getattr(c, "message", "") or "").strip().splitlines()[0] if getattr(c, "message", "") else "<empty>"
        try:
            files  = len(c.stats.files)
        except Exception:
            files  = 0

        hour = dt.hour
        pol  = TextBlob(msg).sentiment.polarity
        hour_counter[hour] += 1
        author_data[author]["count"] += 1
        author_data[author]["polarity_sum"] += pol
        author_data[author]["files"] += files
        total_polarity += pol
        if 1 <= hour <= 5:
            zombie_commits += 1
        tbl.add_row(c.hexsha[:7], author, dt.strftime("%Y-%m-%d"), f"{hour:02d}", str(files), sentiment_label(pol), mood_bar(pol), msg)

    console.print(tbl)
    _render_dev_table(author_data, has_files=True)
    _render_summary(len(commits), hour_counter, zombie_commits, total_polarity)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="git-digit",
        description="Analyze git commit history and developer sentiment.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py .                                    # local repo
  python main.py /path/to/repo -n 100                 # last 100 commits
  python main.py https://github.com/user/repo -n 50   # GitHub, no clone
  python main.py https://github.com/user/repo --token ghp_xxx
        """
    )
    parser.add_argument("repo",      nargs="?", default=".", help="Local path or GitHub URL (default: .)")
    parser.add_argument("-n", "--limit",  type=int, default=50,   metavar="N",      help="Max commits (default: 50)")
    parser.add_argument("-b", "--branch", default="HEAD",         metavar="BRANCH", help="Branch/ref (default: HEAD)")
    parser.add_argument("--token",        default=None,           metavar="TOKEN",  help="GitHub PAT for higher rate limit")

    args = parser.parse_args()

    if args.limit <= 0:
        console.print("[bold red]Error:[/bold red] --limit must be a positive integer.")
        sys.exit(1)

    gh = parse_github_url(args.repo)
    if gh:
        analyze_github(*gh, args.limit, args.branch, token=args.token)
    else:
        analyze_repo(args.repo, args.limit, args.branch)


if __name__ == "__main__":
    main()
