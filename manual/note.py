"""Write a note to wiki/notes/ — smoke-test the note tool pipeline.

Appends a timestamped entry to wiki/notes/{date}.md directly via
write_note() — no server or agent required.  All notes for the same day
share one file.  Use this to seed note files before running dream, or to
verify the note format is correct.

Usage:
  uv run python -m manual.note "Remember: user prefers dark mode."
  uv run python -m manual.note --list                  # list all note files
  uv run python -m manual.note --cat 2026-04-30.md
"""

from __future__ import annotations

import argparse
import sys

from app.services.wiki import NOTES_DIR, wiki_root, write_note


def cmd_write(content: str) -> None:
    path = write_note(content)
    print(f"Note written to: {path}")
    print()
    print(path.read_text(encoding="utf-8"))


def cmd_list() -> None:
    notes_dir = wiki_root() / NOTES_DIR
    if not notes_dir.is_dir():
        print("No notes directory yet.")
        return
    files = sorted(notes_dir.glob("*.md"))
    if not files:
        print("No note files.")
        return
    print(f"Notes ({len(files)} files):\n")
    for f in files:
        size = f.stat().st_size
        lines = f.read_text(encoding="utf-8").count("\n")
        print(f"  {f.name:50s}  {size:6d} bytes  {lines} lines")


def cmd_cat(filename: str) -> None:
    notes_dir = wiki_root() / NOTES_DIR
    path = notes_dir / filename
    if not path.exists():
        print(f"Not found: {path}", file=sys.stderr)
        sys.exit(1)
    print(path.read_text(encoding="utf-8"))


def main() -> None:
    p = argparse.ArgumentParser(
        description="Write a test note to wiki/notes/",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("content", nargs="?", help="Note content to write")
    p.add_argument("--list", action="store_true", help="List all note files")
    p.add_argument("--cat", metavar="FILENAME", help="Print contents of a note file")

    args = p.parse_args()

    if args.list:
        cmd_list()
    elif args.cat:
        cmd_cat(args.cat)
    elif args.content:
        cmd_write(args.content)
    else:
        p.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
