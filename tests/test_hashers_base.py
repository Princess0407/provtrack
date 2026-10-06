import pytest

from provtrack.hashers.base import Hasher, short_id


class DummyHasher(Hasher):
    def hash(self, obj: object) -> str:
        return str(hash(obj))


def test_hasher_abstract():
    with pytest.raises(TypeError):
        Hasher()  # type: ignore


def test_dummy_hasher():
    h = DummyHasher()
    assert isinstance(h.hash("test"), str)


def test_short_id():
    full_hex = "a" * 64
    assert short_id(full_hex) == "a" * 16
    assert len(short_id(full_hex)) == 16
