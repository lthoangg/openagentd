import os
import stat

from app.api.routes.agent.files import _run_bounded_git_diff


async def test_bounded_git_diff_terminates_output_that_exceeds_its_budget(
    tmp_path, monkeypatch
):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_git = fake_bin / "git"
    fake_git.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "while True:\n"
        "    sys.stdout.write('x' * 1024)\n"
        "    sys.stdout.flush()\n",
        encoding="utf-8",
    )
    fake_git.chmod(fake_git.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", f"{fake_bin}{os.pathsep}{os.environ['PATH']}")

    stdout, stderr, returncode, truncated = await _run_bounded_git_diff(
        str(tmp_path), ["diff", "HEAD"], max_bytes=128
    )

    assert stdout == "x" * 129
    assert stderr == ""
    assert returncode != 0
    assert truncated is True
