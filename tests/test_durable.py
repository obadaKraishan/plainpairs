import hashlib
import stat

import pytest

from plainpairs import durable


def test_write_once_writes_checks_and_makes_read_only(tmp_path):
    dest = tmp_path / "raw" / "page.json"
    digest = durable.write_once(dest, b'{"a": 1}')
    assert dest.read_bytes() == b'{"a": 1}'
    assert digest == hashlib.sha256(b'{"a": 1}').hexdigest()
    assert not dest.stat().st_mode & stat.S_IWUSR
    assert not list(dest.parent.glob(".*.tmp"))


def test_write_once_refuses_an_existing_file(tmp_path):
    dest = tmp_path / "page.json"
    durable.write_once(dest, b"one")
    with pytest.raises(FileExistsError, match="written once"):
        durable.write_once(dest, b"two")
    assert dest.read_bytes() == b"one"


def test_write_once_catches_a_file_that_differs_on_disk(tmp_path, monkeypatch):
    monkeypatch.setattr(durable, "sha256_file", lambda path: "0" * 64)
    with pytest.raises(durable.WriteCheckFailed, match="drive is still connected"):
        durable.write_once(tmp_path / "page.json", b"data")


def test_flush_fd_falls_back_to_fsync(tmp_path, monkeypatch):
    calls = []

    class NoFullSync:
        F_FULLFSYNC = 51

        @staticmethod
        def fcntl(fd, op):
            raise OSError("not supported")

    monkeypatch.setattr(durable, "fcntl", NoFullSync)
    monkeypatch.setattr(durable.os, "fsync", lambda fd: calls.append(fd))
    with (tmp_path / "f").open("wb") as fh:
        durable.flush_fd(fh.fileno())
    assert len(calls) == 1


def test_write_chunks_once_streams_checks_and_counts(tmp_path):
    dest = tmp_path / "raw" / "part.zip"
    digest, total = durable.write_chunks_once(dest, iter([b"ab", b"cd", b"e"]))
    assert dest.read_bytes() == b"abcde"
    assert (digest, total) == (hashlib.sha256(b"abcde").hexdigest(), 5)
    assert not dest.stat().st_mode & stat.S_IWUSR


def test_write_chunks_once_leaves_no_half_file_when_reading_fails(tmp_path):
    def broken():
        yield b"ab"
        raise ConnectionError("cut")

    dest = tmp_path / "part.zip"
    with pytest.raises(ConnectionError):
        durable.write_chunks_once(dest, broken())
    assert not dest.exists()
    assert not list(tmp_path.glob(".*.tmp"))


def test_write_chunks_once_refuses_an_existing_file_and_checks_the_disk(tmp_path, monkeypatch):
    dest = tmp_path / "part.zip"
    durable.write_chunks_once(dest, [b"one"])
    with pytest.raises(FileExistsError):
        durable.write_chunks_once(dest, [b"two"])
    monkeypatch.setattr(durable, "sha256_file", lambda path: "0" * 64)
    with pytest.raises(durable.WriteCheckFailed):
        durable.write_chunks_once(tmp_path / "other.zip", [b"x"])
