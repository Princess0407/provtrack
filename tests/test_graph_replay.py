import pytest

from provtrack.graph.replay import replay_pipeline


def test_replay_pipeline_raises_not_implemented():
    with pytest.raises(NotImplementedError, match="not implemented in v2"):
        replay_pipeline("session.json")
