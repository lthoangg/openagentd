"""Inspect and edit wiki files.

Reads files directly from OPENAGENTD_WIKI_DIR — no server required for
tree/read/write commands. The delete command calls DELETE /api/wiki/file
(server required).

Usage:
  uv run python -m manual.wiki tree                       # show full wiki tree
  uv run python -m manual.wiki tree --unprocessed         # notes not yet processed by dream
  uv run python -m manual.wiki read USER.md               # print file contents
  uv run python -m manual.wiki read topics/auth.md
  uv run python -m manual.wiki write topics/test.md       # write from stdin
  uv run python -m manual.wiki delete topics/test.md      # delete via API (server required)
"""

from __future__ import annotations

import argparse
import sys

from app.services.wiki import (
    WikiPathError,
    delete_file,
    list_tree,
    read_file,
    wiki_root,
    write_file,
)


# ── Tree ──────────────────────────────────────────────────────────────────────


def cmd_tree(*, unprocessed: bool) -> None:
    """Print the wiki tree."""
    if unprocessed:
        import asyncio

        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlmodel.ext.asyncio.session import AsyncSession

        from app.core.config import settings
        from app.services.dream import get_unprocessed_notes

        async def _get_unprocessed() -> set[str]:
            engine = create_async_engine(settings.DATABASE_URL.get_secret_value())
            async with AsyncSession(engine) as db:
                return set(await get_unprocessed_notes(db))

        unprocessed_set = asyncio.run(_get_unprocessed())
        tree = list_tree(unprocessed_notes=unprocessed_set)
        print(f"\nWiki root: {wiki_root()}  (unprocessed notes only)\n")
    else:
        tree = list_tree()
        print(f"\nWiki root: {wiki_root()}\n")

    sections = [("system", tree.system), ("topics", tree.topics), ("notes", tree.notes)]
    for name, files in sections:
        print(f"  {name}/  ({len(files)} files)")
        for f in files:
            desc = f"  — {f.description}" if f.description else ""
            upd = f"  [{f.updated}]" if f.updated else ""
            tags = f"  #{', #'.join(f.tags)}" if f.tags else ""
            print(f"    {f.path}{desc}{upd}{tags}")
        if not files:
            print("    (empty)")
        print()


# ── Read ──────────────────────────────────────────────────────────────────────


def cmd_read(path: str) -> None:
    """Print a wiki file's contents."""
    try:
        f = read_file(path)
    except WikiPathError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError:
        print(f"Not found: {path}", file=sys.stderr)
        sys.exit(1)

    print(f"# {path}")
    if f.description:
        print(f"# description: {f.description}")
    if f.updated:
        print(f"# updated:     {f.updated}")
    if f.tags:
        print(f"# tags:        {', '.join(f.tags)}")
    print()
    print(f.content)


# ── Write ─────────────────────────────────────────────────────────────────────


def cmd_write(path: str, content: str) -> None:
    """Write content to a wiki file."""
    try:
        f = write_file(path, content)
    except WikiPathError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"Written: {path}  ({len(f.content)} chars)")


# ── Delete ────────────────────────────────────────────────────────────────────


def cmd_delete(path: str) -> None:
    """Delete a wiki file (directly, no server required)."""
    try:
        delete_file(path)
    except WikiPathError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError:
        print(f"Not found: {path}", file=sys.stderr)
        sys.exit(1)

    print(f"Deleted: {path}")


# ── CLI ───────────────────────────────────────────────────────────────────────


def main() -> None:
    p = argparse.ArgumentParser(
        description="Inspect and edit wiki files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    tree_p = sub.add_parser("tree", help="Show wiki tree")
    tree_p.add_argument(
        "--unprocessed",
        action="store_true",
        help="Show only notes not yet processed by dream (requires DB)",
    )

    read_p = sub.add_parser("read", help="Print a wiki file")
    read_p.add_argument("path", help="Relative path, e.g. USER.md or topics/auth.md")

    write_p = sub.add_parser("write", help="Write a wiki file (reads content from stdin)")
    write_p.add_argument("path", help="Relative path, e.g. topics/test.md")
    write_p.add_argument(
        "--content",
        help="Content string (omit to read from stdin)",
    )

    del_p = sub.add_parser("delete", help="Delete a wiki file")
    del_p.add_argument("path", help="Relative path, e.g. topics/test.md")

    args = p.parse_args()

    if args.cmd == "tree":
        cmd_tree(unprocessed=args.unprocessed)
    elif args.cmd == "read":
        cmd_read(args.path)
    elif args.cmd == "write":
        content = args.content if args.content else sys.stdin.read()
        cmd_write(args.path, content)
    elif args.cmd == "delete":
        cmd_delete(args.path)


if __name__ == "__main__":
    main()
