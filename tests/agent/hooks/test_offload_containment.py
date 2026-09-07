import pytest

from app.agent.hooks import tool_result_offload as offload


@pytest.mark.parametrize(
    "call_id", ["../outside", "absolute", "a/b", "a\\b", "normal-id"]
)
def test_offload_uses_local_filename(tmp_path, monkeypatch, call_id):
    if call_id == "absolute":
        call_id = str(tmp_path / "outside")
    monkeypatch.setattr(offload, "tool_results_dir", lambda *_: tmp_path / "agent")
    path = offload.ToolResultOffloadHook()._write_offload("agent", call_id, "output")
    assert path.parent == tmp_path / "agent"
    assert path.read_text() == "output"
    assert len(path.stem) == 64


def test_offload_does_not_follow_existing_file_symlink(tmp_path, monkeypatch):
    import hashlib

    directory = tmp_path / "agent"
    directory.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("private")
    filename = hashlib.sha256(b"call").hexdigest() + ".txt"
    (directory / filename).symlink_to(outside)
    monkeypatch.setattr(offload, "tool_results_dir", lambda *_: directory)
    path = offload.ToolResultOffloadHook()._write_offload("agent", "call", "output")
    assert outside.read_text() == "private"
    assert not path.is_symlink()
    assert path.read_text() == "output"
