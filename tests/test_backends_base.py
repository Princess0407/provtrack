import pytest

from provtrack.backends.base import Backend


class DummyBackend(Backend):
    def save(self, records):
        pass

    def load(self):
        return []

    def clear(self):
        pass


def test_backend_abstract():
    with pytest.raises(TypeError):
        Backend()  # type: ignore


def test_dummy_backend():
    b = DummyBackend()
    assert b.load() == []
