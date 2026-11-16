import fcntl
import os
import threading

import pytest

from engram import store
from engram.store import StoreBusyError


def _busy_message(lock_path):
    return f"engram store busy: {lock_path} is held by another harvest or rebuild"


def _probe_is_locked(lock_path):
    # Independent holder: its own open file description, never write_lock.
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(fd, fcntl.LOCK_UN)
        return False
    finally:
        os.close(fd)


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


def test_write_lock_holds_an_exclusive_flock_on_the_given_path(lock_path):
    with store.write_lock(lock_path):
        assert lock_path.exists()
        assert _probe_is_locked(lock_path)


def test_write_lock_failed_second_attempt_leaves_first_holder_locked(lock_path):
    with store.write_lock(lock_path):
        with pytest.raises(StoreBusyError):
            with store.write_lock(lock_path):
                pass
        assert _probe_is_locked(lock_path)


# --- never waits ---


def test_write_lock_does_not_wait_for_a_held_lock(lock_path):
    outcome = []

    def contend():
        try:
            with store.write_lock(lock_path):
                outcome.append("entered")
        except StoreBusyError:
            outcome.append("busy")

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

    assert not _probe_is_locked(lock_path)
    with store.write_lock(lock_path):
        assert _probe_is_locked(lock_path)
    assert not _probe_is_locked(lock_path)


def test_write_lock_released_after_body_raises(lock_path):
    with pytest.raises(ValueError, match="body failed"):
        with store.write_lock(lock_path):
            raise ValueError("body failed")

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
