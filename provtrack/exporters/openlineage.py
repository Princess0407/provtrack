from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from provtrack.logger import OperationRecord


def export_openlineage(
    records: List[OperationRecord],
    run_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    active_run_id = run_id or str(uuid.uuid4())
    total = len(records)
    events: List[Dict[str, Any]] = []

    for idx, rec in enumerate(records):
        if total == 1:
            event_type = "COMPLETE"
        elif idx == 0:
            event_type = "START"
        elif idx == total - 1:
            event_type = "COMPLETE"
        else:
            event_type = "RUNNING"

        inputs: List[Dict[str, str]] = []
        if rec.input_hash:
            inputs.append({"namespace": "provtrack", "name": rec.input_hash})

        outputs: List[Dict[str, str]] = []
        if rec.output_hash:
            outputs.append({"namespace": "provtrack", "name": rec.output_hash})

        event_time = datetime.fromtimestamp(rec.timestamp, tz=timezone.utc).isoformat()

        event = {
            "eventType": event_type,
            "eventTime": event_time,
            "run": {
                "runId": active_run_id,
            },
            "job": {
                "namespace": "provtrack",
                "name": "provtrack.pipeline",
            },
            "inputs": inputs,
            "outputs": outputs,
        }
        events.append(event)

    return events
