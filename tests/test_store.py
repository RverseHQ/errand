from pathlib import Path

from errand import Status
from errand.store import Record, Store


def test_round_trips_a_record(tmp_path: Path) -> None:
    store = Store(tmp_path / "q.db")
    store.insert(Record("a", "echo", '{"text":"你好"}'))

    assert store.get("a") == Record("a", "echo", '{"text":"你好"}')
    assert store.get("missing") is None


def test_running_lists_unfinished_in_submission_order(tmp_path: Path) -> None:
    store = Store(tmp_path / "q.db")
    for id in ("c", "a", "b"):
        store.insert(Record(id, "echo", "null"))
    store.finish("a", "[1,2]")
    store.fail("b", "RuntimeError: boom")

    assert [record.id for record in store.running()] == ["c"]
    assert store.get("a") == Record("a", "echo", "null", Status.DONE, "[1,2]")
    assert store.get("b") == Record("b", "echo", "null", Status.FAILED, error="RuntimeError: boom")


def test_persists_across_connections(tmp_path: Path) -> None:
    Store(tmp_path / "q.db").insert(Record("a", "echo", "1"))

    assert Store(tmp_path / "q.db").get("a") == Record("a", "echo", "1")
