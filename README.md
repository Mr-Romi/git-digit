# git-digit 🔍

> Analyze git commit history and developer sentiment — locally or directly from GitHub, no cloning needed.

## What It Does

git-digit reads commit messages and scores them with AI sentiment analysis (-1.0 to +1.0), then prints a rich terminal report showing:

- 📊 Per-commit mood (Positive / Neutral / Negative)
- 👤 Developer summary — who commits most, and how stressed they seem
- 🕐 Peak activity hour
- 🧟 Zombie commits (1–5 AM late-night coding)
- 📈 Overall repo mood bar

## Stack

| Library | Purpose |
|---------|---------|
| [GitPython](https://gitpython.readthedocs.io/) | Read local git history |
| [TextBlob](https://textblob.readthedocs.io/) | Commit message sentiment scoring |
| [Rich](https://rich.readthedocs.io/) | Terminal tables and panels |
| [requests](https://requests.readthedocs.io/) | GitHub REST API (no-clone mode) |

## Setup

```bash
# Clone the repo
git clone https://github.com/Mr-Romi/git-digit.git
cd git-digit

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate       # Windows
# source .venv/bin/activate  # macOS/Linux

# Install dependencies
pip install gitpython textblob rich requests
```

## Usage

```bash
# Analyze a local git repo
python main.py /path/to/repo

# Analyze any GitHub repo — no cloning needed
python main.py https://github.com/pallets/flask -n 100

# Specific branch, last 50 commits
python main.py /path/to/repo -b main -n 50

# With GitHub token (5000 req/hr instead of 60)
python main.py https://github.com/user/repo --token ghp_yourtoken
```

## Options

| Flag | Default | Description |
|------|---------|-------------|
| epo | . | Local path or GitHub URL |
| -n / --limit | 50 | Max commits to analyze |
| -b / --branch | HEAD | Branch or ref |
| --token | None | GitHub personal access token |

## Example Output

```
┌──────────────────────────────────────────────────────────┐
│ git-digit  GitHub API Mode                               │
│ Repo: github.com/pallets/flask  Branch: HEAD  Limit: 20  │
└──────────────────────────────────────────────────────────┘

  Commit History (GitHub)
  ┌─────────┬──────────────┬────────────┬────┬──────────────┬──────────────┬──────────────────────┐
  │ Hash    │ Author       │ Date       │ Hr │ Mood         │ Bar          │ Message              │
  ├─────────┼──────────────┼────────────┼────┼──────────────┼──────────────┼──────────────────────┤
  │ b7e610b │ David Lord   │ 2026-08-01 │ 14 │ ~ Neutral    │ #####-----   │ fix typos            │
  └─────────┴──────────────┴────────────┴────┴──────────────┴──────────────┴──────────────────────┘

  ┌─────────────────── Summary ───────────────────┐
  │ Total Commits Analyzed: 20                    │
  │ Peak Activity Hour:     14:00                 │
  │ Zombie Commits (1-5AM): 0                     │
  │ Overall Repo Mood:      +0.000  ~ Neutral     │
  │ Mood Bar:               #####-----            │
  └───────────────────────────────────────────────┘
```

## Built In

24-hour coding challenge — built with Python.
