import json
from io import BytesIO
from unittest.mock import MagicMock
import pytest

from provtrack.backends.s3 import S3Backend
from provtrack.logger import OperationRecord


def test_s3_invalid_inputs():
    with pytest.raises(ValueError, match="requires either bucket or s3_uri"):
        S3Backend()

    with pytest.raises(ValueError, match="Invalid S3 URI"):
        S3Backend(s3_uri="http://not-an-s3-uri")


def test_s3_backend_operations():
    mock_client = MagicMock()
    backend = S3Backend(bucket="test-bucket", session_id="sess-1", client=mock_client)

    rec = OperationRecord(
        id="rec-s3",
        op_name="read_parquet",
        output_hash="hash-out",
        input_hash=None,
    )

    # Test save
    backend.save([rec])
    assert mock_client.put_object.called
    call_kwargs = mock_client.put_object.call_args.kwargs
    assert call_kwargs["Bucket"] == "test-bucket"
    assert call_kwargs["Key"] == "provtrack/sess-1.json"

    # Test load
    mock_payload = {
        "session_id": "sess-1",
        "nodes": [rec.to_dict()],
    }
    mock_body = MagicMock()
    mock_body.read.return_value = json.dumps(mock_payload).encode("utf-8")
    mock_client.get_object.return_value = {"Body": mock_body}

    loaded = backend.load()
    assert len(loaded) == 1
    assert loaded[0].id == "rec-s3"

    # Test clear
    backend.clear()
    assert mock_client.delete_object.called
