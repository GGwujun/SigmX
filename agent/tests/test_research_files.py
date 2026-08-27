import pytest

from src.research_agent.files import ResearchFileStore


def test_file_store_isolates_tasks_and_rejects_unsafe_types(tmp_path) -> None:
    store = ResearchFileStore(tmp_path, max_bytes=20)
    saved = store.save("task-a", "facts.csv", b"code,value\n1,2\n")
    assert store.read("task-a", saved.id).startswith(b"code")
    with pytest.raises(KeyError):
        store.read("task-b", saved.id)
    with pytest.raises(ValueError, match="file type"):
        store.save("task-a", "run.exe", b"bad")


def test_file_store_rejects_traversal_and_large_files(tmp_path) -> None:
    store = ResearchFileStore(tmp_path, max_bytes=4)
    with pytest.raises(ValueError):
        store.save("../escape", "a.txt", b"ok")
    with pytest.raises(ValueError, match="size"):
        store.save("task-a", "a.txt", b"12345")
