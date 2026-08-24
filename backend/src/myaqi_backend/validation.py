from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


class PayloadError(Exception):
    pass


@dataclass(frozen=True)
class ReadingInput:
    sequence: int
    observed_at: datetime
    pm25_ug_m3: float
    temperature_c: float | None
    relative_humidity: float | None


def _number(
    value: Any,
    *,
    field: str,
    minimum: float,
    maximum: float,
    optional: bool = False,
) -> float | None:
    if value is None and optional:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PayloadError(f"{field} must be a number")
    converted = float(value)
    if not minimum <= converted <= maximum:
        raise PayloadError(f"{field} must be between {minimum:g} and {maximum:g}")
    return converted


def _timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise PayloadError("observed_at must be an RFC 3339 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PayloadError("observed_at must be an RFC 3339 timestamp") from exc
    if parsed.tzinfo is None:
        raise PayloadError("observed_at must include a timezone")
    return parsed


def parse_batch(payload: Any, *, max_batch_size: int) -> list[ReadingInput]:
    if not isinstance(payload, dict):
        raise PayloadError("Request body must be a JSON object")
    readings = payload.get("readings")
    if not isinstance(readings, list) or not readings:
        raise PayloadError("readings must be a non-empty array")
    if len(readings) > max_batch_size:
        raise PayloadError(f"readings may contain at most {max_batch_size} items")

    parsed: list[ReadingInput] = []
    seen_sequences: set[int] = set()
    for index, item in enumerate(readings):
        if not isinstance(item, dict):
            raise PayloadError(f"readings[{index}] must be an object")

        sequence = item.get("sequence")
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
            raise PayloadError(f"readings[{index}].sequence must be a non-negative integer")
        if sequence in seen_sequences:
            raise PayloadError(f"readings contains duplicate sequence {sequence}")
        seen_sequences.add(sequence)

        parsed.append(
            ReadingInput(
                sequence=sequence,
                observed_at=_timestamp(item.get("observed_at")),
                pm25_ug_m3=_number(
                    item.get("pm25_ug_m3"),
                    field=f"readings[{index}].pm25_ug_m3",
                    minimum=0,
                    maximum=5000,
                ),
                temperature_c=_number(
                    item.get("temperature_c"),
                    field=f"readings[{index}].temperature_c",
                    minimum=-80,
                    maximum=100,
                    optional=True,
                ),
                relative_humidity=_number(
                    item.get("relative_humidity"),
                    field=f"readings[{index}].relative_humidity",
                    minimum=0,
                    maximum=100,
                    optional=True,
                ),
            )
        )
    return parsed
