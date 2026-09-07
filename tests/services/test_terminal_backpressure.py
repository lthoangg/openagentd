import asyncio
import signal
from unittest.mock import AsyncMock, Mock

import pytest

from app.services import terminal_service as terminal


@pytest.fixture
async def session(monkeypatch):
    loop = asyncio.get_running_loop()
    monkeypatch.setattr(loop, "add_reader", Mock())
    monkeypatch.setattr(loop, "remove_reader", Mock())
    monkeypatch.setattr(terminal.os, "close", Mock())
    monkeypatch.setattr(terminal.os, "getpgid", lambda _: 999999)
    monkeypatch.setattr(terminal.os, "killpg", Mock())
    proc = Mock()
    proc.poll.return_value = None
    proc.wait.return_value = -signal.SIGKILL
    return terminal.TerminalSession("test-terminal", 999999, 999999, "/test", proc)


async def test_close_escalates_and_reaps_live_process(session, monkeypatch):
    monkeypatch.setattr(terminal.asyncio, "sleep", AsyncMock())
    await session.close()
    assert any(
        call.args[1] == signal.SIGKILL for call in terminal.os.killpg.call_args_list
    )
    session._proc.wait.assert_called_once()


async def test_close_unblocks_full_queue(session):
    session._proc.poll.return_value = 0
    session._read_queue = asyncio.Queue(maxsize=1)
    session._read_queue.put_nowait(b"output")
    await session.close()
    while await session.read() is not None:
        pass


async def test_write_retries_partial_writes(session, monkeypatch):
    writes = []

    def write(_fd, data):
        writes.append(bytes(data))
        return min(2, len(data))

    monkeypatch.setattr(terminal.os, "write", write)
    await session.write(b"abcdef")
    assert writes == [b"abcdef", b"cdef", b"ef"]


async def test_write_waits_for_writable_fd(session, monkeypatch):
    write = Mock(side_effect=[BlockingIOError(), 3])
    monkeypatch.setattr(terminal.os, "write", write)
    loop = asyncio.get_running_loop()
    monkeypatch.setattr(
        loop, "add_writer", lambda _fd, callback: loop.call_soon(callback)
    )
    monkeypatch.setattr(loop, "remove_writer", Mock())
    await session.write(b"abc")
    assert write.call_count == 2
