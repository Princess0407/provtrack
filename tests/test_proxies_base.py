import pytest

from provtrack.proxies.base import BaseProxy


class DummyProxy(BaseProxy):
    def __init__(self, obj):
        self._obj = obj

    def unwrap(self):
        return self._obj

    def __getattr__(self, name):
        return getattr(self._obj, name)


def test_base_proxy_abstract():
    with pytest.raises(TypeError):
        BaseProxy()  # type: ignore


def test_dummy_proxy():
    p = DummyProxy("hello")
    assert p.unwrap() == "hello"
    assert p.upper() == "HELLO"
