"""Check relative Markdown links from the repository root without Git or dependencies."""

import os
import re
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import unquote

EXCLUDED_DIRS = {
    ".cache",
    ".git",
    ".hypothesis",
    ".mypy_cache",
    ".pre-commit-cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    ".vercel",
    ".vite",
    "__pycache__",
    "blob-report",
    "build",
    "coverage",
    "dist",
    "htmlcov",
    "node_modules",
    "playwright-report",
    "staticfiles",
    "test-results",
    "venv",
}

INLINE_LINK = re.compile(
    r"\[[^\]\n]*\]\(\s*(?:<([^>\n]+)>|([^\s()]+))"
    r"""(?:[ \t]+(?:"[^"\n]*"|'[^'\n]*'))?\s*\)"""
)
URL_SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")


def markdown_files(root: Path) -> Iterator[Path]:
    """Walk the snapshot, pruning generated directories before descending."""
    for directory, dirs, files in os.walk(root):
        folder = Path(directory)
        dirs[:] = sorted(
            name for name in dirs if name not in EXCLUDED_DIRS and not name.endswith(".egg-info")
        )
        if folder == root / "backend" and "media" in dirs:
            dirs.remove("media")
        for name in sorted(files):
            if name.endswith(".md"):
                yield folder / name


def broken_links(document: Path) -> Iterator[str]:
    """Yield inline link and image targets whose relative paths do not exist."""
    for match in INLINE_LINK.finditer(document.read_text(encoding="utf-8")):
        target = match.group(1) or match.group(2)
        if target.startswith(("#", "/")) or URL_SCHEME.match(target):
            continue
        path = target.split("#", 1)[0].split("?", 1)[0]
        if path and not (document.parent / unquote(path)).exists():
            yield target


def main() -> int:
    """Print broken targets and return a failing status if any were found."""
    root = Path.cwd()
    failed = False
    for document in markdown_files(root):
        for target in broken_links(document):
            print(f"{document.relative_to(root).as_posix()}: {target}")
            failed = True
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
