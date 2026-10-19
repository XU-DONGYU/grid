#!/usr/bin/env python3
"""Scan repository files for secrets and personal information.

Usage:
    python3 scripts/scan_secrets.py
    python3 scripts/scan_secrets.py --staged

Exit code is non-zero when a finding is detected.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

PATTERNS: dict[str, re.Pattern[str]] = {
    "private-key": re.compile(r"BEGIN [A-Z ]*PRIVATE KEY"),
    "github-token": re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"),
    "aws-access-key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "openai-key": re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    "slack-token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    "generic-secret": re.compile(
        r"(?i)\b(api[_-]?key|secret|password|passwd|access[_-]?token|client[_-]?secret)\b"
        r"\s*[:=]\s*['\"][^'\"]{6,}['\"]"
    ),
    "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    "home-path": re.compile(r"(/home/[A-Za-z0-9._-]+/|/Users/[A-Za-z0-9._-]+/|[A-Z]:\\\\Users\\\\)"),
    "cn-mobile": re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
}

SKIP_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".ico",
    ".pdf",
    ".zip",
    ".gz",
    ".woff",
    ".woff2",
    ".ttf",
}

SKIP_PARTS = {".git", "__pycache__", ".venv", "venv", "node_modules"}


def git_files(staged: bool) -> list[str]:
    if staged:
        cmd = ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"]
    else:
        cmd = ["git", "ls-files", "-co", "--exclude-standard"]
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def scan_file(path: Path) -> list[tuple[int, str, str]]:
    if path.suffix.lower() in SKIP_SUFFIXES:
        return []
    if any(part in SKIP_PARTS for part in path.parts):
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []

    findings: list[tuple[int, str, str]] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        if "# nosecret" in line:
            continue
        for name, pattern in PATTERNS.items():
            match = pattern.search(line)
            if match:
                value = match.group(0)
                masked = value[:6] + "***" if len(value) > 6 else "***"
                findings.append((lineno, name, masked))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--staged", action="store_true", help="scan staged files only")
    args = parser.parse_args()

    files = git_files(args.staged)
    if not files:
        print("secret-scan: no files to scan")
        return 0

    total = 0
    for name in files:
        path = Path(name)
        for lineno, rule, masked in scan_file(path):
            total += 1
            print(f"{name}:{lineno}: [{rule}] {masked}")

    if total:
        print(f"secret-scan: {total} finding(s). Remove or redact before committing.")
        return 1

    print(f"secret-scan: {len(files)} file(s) checked, no findings")
    return 0


if __name__ == "__main__":
    sys.exit(main())
