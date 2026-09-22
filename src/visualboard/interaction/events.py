from __future__ import annotations

from dataclasses import dataclass

from visualboard.core.types import KeyId, TriggerSource


@dataclass(frozen=True, slots=True)
class KeyTriggerEvent:
    key_id: KeyId
    source: TriggerSource
    timestamp: float
