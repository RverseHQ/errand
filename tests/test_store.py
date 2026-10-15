from contextlib import closing
from pathlib import Path

from errand import Job, Status
from errand.store import Store


def test_round_trips_a_job(tmp_path: Path) -> None:
    with closing(Store(tmp_path / "q.db")) as store:
        store.insert(Job("a", "echo", {"text": "你好"}))

        assert store.get("a") == Job("a", "echo", {"text": "你好"})
        assert store.get("missing") is None


def test_running_lists_unfinished_in_submission_order(tmp_path: Path) -> None:
    with closing(Store(tmp_path / "q.db")) as store:
        for id in ("c", "a", "b"):
            store.insert(Job(id, "echo", None))
        store.finish("a", [1, 2])
        store.fail("b", "RuntimeError: boom")

        assert [job.id for job in store.running()] == ["c"]
        a, b = store.get("a"), store.get("b")
        assert a is not None and b is not None
        assert (a.status, a.result, a.error) == (Status.DONE, [1, 2], None)
        assert (b.status, b.result, b.error) == (Status.FAILED, None, "RuntimeError: boom")
        assert a.finished_at is not None and b.finished_at is not None


def test_persists_across_connections(tmp_path: Path) -> None:
    with closing(Store(tmp_path / "q.db")) as store:
        store.insert(Job("a", "echo", 1))

    with closing(Store(tmp_path / "q.db")) as store:
        assert store.get("a") == Job("a", "echo", 1)
