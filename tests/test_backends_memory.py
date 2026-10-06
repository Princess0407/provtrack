from provtrack.backends.memory import MemoryBackend
from provtrack.logger import OperationRecord


def test_memory_backend_save_load_clear():
    backend = MemoryBackend()
    assert backend.load() == []

    rec = OperationRecord(
        id="rec-1",
        op_name="dropna",
        output_hash="hash-out",
        input_hash="hash-in",
    )
    backend.save([rec])
    records = backend.load()
    assert len(records) == 1
    assert records[0].id == "rec-1"
    assert records[0].op_name == "dropna"

    backend.clear()
    assert backend.load() == []
