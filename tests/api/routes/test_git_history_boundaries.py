import subprocess
import pytest

from app.api.routes.agent.files import (
    _untracked_diff,
    get_coding_workspace_git_history,
)


@pytest.mark.parametrize("all_branches", [False, True])
async def test_git_history_pages_have_no_gaps_or_duplicate_graph(
    tmp_path, all_branches
):
    def git(*args):
        return subprocess.run(
            ["git", "-C", str(tmp_path), *args],
            capture_output=True,
            text=True,
            check=True,
        ).stdout

    git("init")
    git("config", "user.name", "Test")
    git("config", "user.email", "test@example.com")
    for number in range(5):
        git(
            "-c",
            "commit.gpgsign=false",
            "commit",
            "--allow-empty",
            "-m",
            f"commit-{number}",
        )
    first = await get_coding_workspace_git_history(
        str(tmp_path), limit=2, cursor=None, all_branches=all_branches
    )
    second = await get_coding_workspace_git_history(
        str(tmp_path), limit=2, cursor=first.next_cursor, all_branches=all_branches
    )
    assert [c.subject for c in first.commits + second.commits] == [
        "commit-4",
        "commit-3",
        "commit-2",
        "commit-1",
    ]
    assert "commit-4" not in second.graph
    assert "commit-2" in second.graph


def test_untracked_diff_does_not_read_outside_symlink(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    secret = tmp_path / "secret.txt"
    secret.write_text("private-content")
    (workspace / "link.txt").symlink_to(secret)
    assert "private-content" not in _untracked_diff(workspace, ["link.txt"])


def test_untracked_diff_has_aggregate_budget(tmp_path, monkeypatch):
    from app.api.routes.agent import files

    for number in range(4):
        (tmp_path / f"{number}.txt").write_text("large-output\n" * 100)
    monkeypatch.setattr(files, "_MAX_GIT_DIFF_CHARS", 256)
    result = _untracked_diff(tmp_path, [f"{i}.txt" for i in range(4)])
    assert len(result) <= 257
