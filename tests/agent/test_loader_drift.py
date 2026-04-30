"""Drift-detection helpers in app/agent/loader.py."""

from __future__ import annotations

from pathlib import Path

from app.agent.loader import detect_drift, stamp_agent_files


def _touch(path: Path, content: str = "x") -> None:
    """Write content; bumps mtime."""
    path.write_text(content)


def test_stamp_records_existing_and_missing(tmp_path: Path) -> None:
    agent_md = tmp_path / "a.md"
    agent_md.write_text("---\nname: a\n---\n")
    skills = tmp_path / "skills"
    skills.mkdir()
    mcp = tmp_path / "mcp.json"  # missing on purpose

    stamp = stamp_agent_files(agent_md, ["unknown"], skills, mcp)

    assert stamp[str(agent_md)] is not None
    assert stamp[str(mcp)] is None
    assert stamp[str(skills / "unknown" / "SKILL.md")] is None


def test_detect_drift_clean(tmp_path: Path) -> None:
    md = tmp_path / "a.md"
    md.write_text("hi")
    stamp = stamp_agent_files(md, [], tmp_path, tmp_path / "mcp.json")
    assert detect_drift(stamp) == []


def test_detect_drift_when_file_changes(tmp_path: Path) -> None:
    md = tmp_path / "a.md"
    md.write_text("hi")
    stamp = stamp_agent_files(md, [], tmp_path, tmp_path / "mcp.json")

    # Sleep-free mtime bump: rewrite via os.utime.
    import os

    new_ns = stamp[str(md)] + 1_000_000  # pyright: ignore[reportOptionalOperand]
    os.utime(md, ns=(new_ns, new_ns))

    drifted = detect_drift(stamp)
    assert drifted == [str(md)]


def test_detect_drift_when_file_appears(tmp_path: Path) -> None:
    md = tmp_path / "a.md"
    md.write_text("hi")
    mcp = tmp_path / "mcp.json"  # absent at stamp time
    stamp = stamp_agent_files(md, [], tmp_path, mcp)

    mcp.write_text("{}")  # appearance

    assert str(mcp) in detect_drift(stamp)


def test_detect_drift_when_file_disappears(tmp_path: Path) -> None:
    md = tmp_path / "a.md"
    md.write_text("hi")
    stamp = stamp_agent_files(md, [], tmp_path, tmp_path / "mcp.json")

    md.unlink()

    assert detect_drift(stamp) == [str(md)]
