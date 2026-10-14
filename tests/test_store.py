from pathlib import Path

from errand import Job, Status
from errand.store import Store


def test_round_trips_a_job(tmp_path: Path) -> None:
    store = Store(tmp_path / "q.db")
    store.insert(Job("a", "echo", {"text": "你好"}))

    assert store.get("a") == Job("a", "echo", {"text": "你好"})
    assert store.get("missing") is None


def test_running_lists_unfinished_in_submission_order(tmp_path: Path) -> None:
    store = Store(tmp_path / "q.db")
    for id in ("c", "a", "b"):
        store.insert(Job(id, "echo", None))
    store.finish("a", [1, 2])
    store.fail("b", "RuntimeError: boom")

    assert [job.id for job in store.running()] == ["c"]
    assert store.get("a") == Job("a", "echo", None, Status.DONE, [1, 2])
    assert store.get("b") == Job("b", "echo", None, Status.FAILED, error="RuntimeError: boom")


def test_persists_across_connections(tmp_path: Path) -> None:
    Store(tmp_path / "q.db").insert(Job("a", "echo", 1))

    assert Store(tmp_path / "q.db").get("a") == Job("a", "echo", 1)
