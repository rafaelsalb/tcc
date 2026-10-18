"""Durable, append-only checkpoints for sequential batch evaluations (POSIX)."""

from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import threading


JOURNAL_VERSION = 1


def canonical_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def checksum(value):
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def durable_flush(stream):
    stream.flush()
    os.fsync(stream.fileno())


def sync_directory(path):
    descriptor = os.open(Path(path), os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


@contextmanager
def defer_stop_signals():
    """Finish a small disk commit before delivering Ctrl+C or SIGTERM."""
    previous = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT, signal.SIGTERM})
    try:
        yield
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK, previous)


class BatchStopped(KeyboardInterrupt):
    def __init__(self, signum=signal.SIGINT):
        self.signum = signum


@contextmanager
def stop_on_termination():
    if threading.current_thread() is not threading.main_thread():
        yield
        return

    def stop(signum, frame):
        raise BatchStopped(signum)

    previous = signal.signal(signal.SIGTERM, stop)
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, previous)


@contextmanager
def output_lock(json_path):
    # Never unlink: replacing a lock inode would allow concurrent writers.
    lock_path = Path(str(json_path) + ".lock")
    with lock_path.open("a+b") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(f"another batch is using {json_path}") from exc
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


class ResultJournal:
    """Keeps only a completed counter in RAM, not past search responses."""

    def __init__(self, path, config, expected_tasks, resume=False):
        self.path = Path(path)
        self.completed = 0
        self.header = {
            "type": "batch", "journal_version": JOURNAL_VERSION,
            "config": config, "fingerprint": checksum(config),
        }
        if resume:
            self._recover(expected_tasks)
        else:
            with defer_stop_signals(), self.path.open("wb") as stream:
                stream.write((canonical_json(self.header) + "\n").encode("utf-8"))
                durable_flush(stream)
                sync_directory(self.path.parent)

    def _recover(self, expected_tasks):
        """Accept only an exact task prefix; discard only an uncommitted EOF tail."""
        with self.path.open("r+b") as stream:
            try:
                header_line = stream.readline()
                header = json.loads(header_line)
            except (ValueError, UnicodeDecodeError) as exc:
                raise ValueError("invalid checkpoint header; use a new output or --overwrite") from exc
            if not header_line.endswith(b"\n") or header != self.header:
                raise ValueError("checkpoint does not match input, API, search settings or metric rules")
            tasks = iter(expected_tasks)
            while True:
                position = stream.tell()
                line = stream.readline()
                if not line:
                    break
                if not line.endswith(b"\n"):
                    with defer_stop_signals():
                        stream.truncate(position)
                        durable_flush(stream)
                    print("Recovered an unfinished final checkpoint write; that request will run again.", flush=True)
                    break
                try:
                    record = json.loads(line)
                    digest = record.pop("checksum")
                    task = next(tasks)
                    if (
                        checksum(record) != digest
                        or record["type"] != "result"
                        or type(record["index"]) is not int
                        or record["index"] != self.completed
                        or record["task"] != task
                        or any(record["result"][key] != value for key, value in task.items() if key != "id")
                    ):
                        raise ValueError("checksum, sequence or task mismatch")
                except (ValueError, KeyError, TypeError, AttributeError, StopIteration, UnicodeDecodeError) as exc:
                    raise ValueError(f"corrupt checkpoint record {self.completed + 1}; refusing to skip it") from exc
                self.completed += 1

    def append(self, task, result):
        record = {"type": "result", "index": self.completed, "task": task, "result": result}
        record["checksum"] = checksum(record)
        with self.path.open("ab") as stream:
            stream.write((canonical_json(record) + "\n").encode("utf-8"))
            durable_flush(stream)
        self.completed += 1

    def records(self):
        with self.path.open("rb") as stream:
            next(stream)  # Configuration header; already verified on resume.
            for line in stream:
                if not line.endswith(b"\n"):
                    break  # Uncommitted tail, never export it as a completed result.
                yield json.loads(line)
