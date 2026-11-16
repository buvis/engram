import errno
import fcntl
import os
import subprocess
import sys
import threading
import time

import pytest

from engram import store
from engram.store import StoreBusyError


def _busy_message(lock_path):
    return f"engram store busy: {lock_path} is held by another harvest or rebuild"


def _probe_is_locked(lock_path, operation=fcntl.LOCK_EX):
    # Independent holder: its own open file description, never write_lock.
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT)
    try:
        try:
            fcntl.flock(fd, operation | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(fd, fcntl.LOCK_UN)
        return False
    finally:
        os.close(fd)


_CHILD_CONTENDER = """
import pathlib
import sys

from engram import store

try:
    with store.write_lock(pathlib.Path(sys.argv[1])):
        print("entered")
except store.StoreBusyError as exc:
    print("busy")
    print(exc)
"""


def _contend_from_child_process(lock_path):
    result = subprocess.run(
        [sys.executable, "-c", _CHILD_CONTENDER, str(lock_path)],
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    return result.stdout.splitlines()


@pytest.fixture(params=["engram.db.lock", "other-store.db.lock"])
def lock_path(request, tmp_path):
    return tmp_path / request.param


# --- a second holder fails loud with StoreBusyError ---


def test_write_lock_second_holder_raises_store_busy(lock_path):
    with store.write_lock(lock_path):
        with pytest.raises(StoreBusyError) as exc_info:
            with store.write_lock(lock_path):
                pytest.fail("second holder entered a held write lock")

    message = str(exc_info.value)
    assert message == _busy_message(lock_path)
    assert str(lock_path) in message
    assert "another harvest or rebuild" in message


def test_write_lock_blocks_a_holder_in_another_process(lock_path):
    # An in-process "already held" set cannot stop a second process.
    with store.write_lock(lock_path):
        assert _contend_from_child_process(lock_path) == [
            "busy",
            _busy_message(lock_path),
        ]
        assert _probe_is_locked(lock_path)

    assert _contend_from_child_process(lock_path) == ["entered"]


def test_store_busy_error_is_a_runtime_error():
    assert issubclass(StoreBusyError, RuntimeError)


def test_write_lock_raises_store_busy_when_held_by_an_independent_flock(lock_path):
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(StoreBusyError) as exc_info:
            with store.write_lock(lock_path):
                pytest.fail("write_lock entered while another holder had the flock")
    finally:
        os.close(fd)

    assert str(exc_info.value) == _busy_message(lock_path)


def test_write_lock_holds_an_exclusive_flock_on_the_given_path(lock_path, monkeypatch):
    real_flock = fcntl.flock
    calls = []

    def spy_flock(fd, operation):
        calls.append((fd, operation))
        return real_flock(fd, operation)

    monkeypatch.setattr(fcntl, "flock", spy_flock)

    with store.write_lock(lock_path):
        assert lock_path.exists()

        # Pinned to fcntl.flock (not lockf), non-blocking exclusive, on this file.
        assert calls, "write_lock never called fcntl.flock"
        locked_fd, operation = calls[0]
        assert operation == fcntl.LOCK_EX | fcntl.LOCK_NB
        fileno = locked_fd if isinstance(locked_fd, int) else locked_fd.fileno()
        locked_stat = os.fstat(fileno)
        path_stat = lock_path.stat()
        assert (locked_stat.st_dev, locked_stat.st_ino) == (
            path_stat.st_dev,
            path_stat.st_ino,
        )

        # The lock must still hold after a delay, not only right after acquiring.
        time.sleep(1.5)
        assert _probe_is_locked(lock_path, fcntl.LOCK_EX)
        assert _probe_is_locked(lock_path, fcntl.LOCK_SH)


def test_write_lock_failed_second_attempt_leaves_first_holder_locked(lock_path):
    with store.write_lock(lock_path):
        with pytest.raises(StoreBusyError):
            with store.write_lock(lock_path):
                pass
        assert _probe_is_locked(lock_path)


# --- never waits ---


def test_write_lock_does_not_wait_for_a_held_lock(lock_path):
    outcome = []
    elapsed = []

    def contend():
        started = time.perf_counter()
        try:
            with store.write_lock(lock_path):
                outcome.append("entered")
        except StoreBusyError:
            outcome.append("busy")
        finally:
            elapsed.append(time.perf_counter() - started)

    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        worker = threading.Thread(target=contend, daemon=True)
        worker.start()
        worker.join(timeout=5)
        returned_promptly = not worker.is_alive()
    finally:
        os.close(fd)

    assert returned_promptly, "write_lock blocked instead of raising StoreBusyError"
    assert outcome == ["busy"]
    assert elapsed[0] < 0.5, f"write_lock took {elapsed[0]:.3f}s to report busy"


# --- non-busy errors are not busy ---


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores directory permissions")
def test_write_lock_propagates_permission_error_instead_of_store_busy(tmp_path):
    locked_dir = tmp_path / "read-only"
    locked_dir.mkdir()
    lock_path = locked_dir / "engram.db.lock"
    locked_dir.chmod(0o500)
    try:
        with pytest.raises(PermissionError) as exc_info:
            with store.write_lock(lock_path):
                pytest.fail("write_lock entered without a lock file")
    finally:
        locked_dir.chmod(0o700)

    assert not isinstance(exc_info.value, StoreBusyError)
    assert not lock_path.exists()


# --- lock path scoping ---


def test_write_lock_on_a_near_miss_path_does_not_conflict(tmp_path):
    held = tmp_path / "engram.db.lock"
    near_misses = [
        tmp_path / "engram.db.lock2",
        tmp_path / "engram.db",
        tmp_path / "sub" / "engram.db.lock",
    ]

    with store.write_lock(held):
        for other in near_misses:
            with store.write_lock(other):
                assert _probe_is_locked(other)
        assert _probe_is_locked(held)


def test_write_lock_creates_missing_parent_dirs(tmp_path):
    lock_path = tmp_path / "share" / "engram" / "engram.db.lock"
    assert not lock_path.parent.exists()

    with store.write_lock(lock_path):
        assert lock_path.exists()
        assert _probe_is_locked(lock_path)

    assert not (tmp_path / "engram.db.lock").exists()


# --- release on exit ---


def test_write_lock_released_after_exit(lock_path):
    with store.write_lock(lock_path):
        pass

    # The lock file stays: unlinking it lets a later holder lock a new inode
    # while an earlier one still holds the old one.
    assert lock_path.exists()
    keeper = os.open(lock_path, os.O_RDONLY)
    try:
        inode = os.fstat(keeper).st_ino
        assert not _probe_is_locked(lock_path)
        with store.write_lock(lock_path):
            assert lock_path.stat().st_ino == inode
            assert _probe_is_locked(lock_path)
        assert lock_path.exists()
        assert lock_path.stat().st_ino == inode
    finally:
        os.close(keeper)
    assert not _probe_is_locked(lock_path)


@pytest.mark.parametrize(
    "make_body_error",
    [
        lambda: ValueError("body failed"),
        lambda: BlockingIOError(errno.EAGAIN, "body would block"),
        lambda: PermissionError(errno.EACCES, "body denied"),
    ],
    ids=["value-error", "blocking-io-error", "permission-error"],
)
def test_write_lock_released_after_body_raises(lock_path, make_body_error):
    body_error = make_body_error()
    with pytest.raises(type(body_error)) as exc_info:
        with store.write_lock(lock_path):
            raise body_error

    # The body's own error passes through unchanged, never as StoreBusyError.
    assert exc_info.value is body_error
    assert not isinstance(exc_info.value, StoreBusyError)
    assert not _probe_is_locked(lock_path)
    with store.write_lock(lock_path):
        pass


def test_write_lock_closes_its_file_descriptor_on_exit(lock_path):
    with store.write_lock(lock_path):
        pass
    fds_before = set(os.listdir("/dev/fd"))

    for _ in range(3):
        with store.write_lock(lock_path):
            pass

    assert set(os.listdir("/dev/fd")) == fds_before


def test_write_lock_closes_its_file_descriptor_when_busy(lock_path):
    holder = os.open(lock_path, os.O_RDWR | os.O_CREAT)
    # Keep each traceback alive so a leaked file object cannot be closed by GC.
    kept = []
    try:
        fcntl.flock(holder, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(StoreBusyError) as warm_up:
            with store.write_lock(lock_path):
                pass
        kept.append(warm_up)
        fds_before = set(os.listdir("/dev/fd"))

        for _ in range(3):
            with pytest.raises(StoreBusyError) as busy:
                with store.write_lock(lock_path):
                    pass
            kept.append(busy)

        assert set(os.listdir("/dev/fd")) == fds_before
    finally:
        os.close(holder)
