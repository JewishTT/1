from typing import ClassVar as _ClassVar

from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message

DESCRIPTOR: _descriptor.FileDescriptor

class EventEnvelope(_message.Message):
    __slots__ = ("event_id", "event_type", "event_version", "investigation_id", "correlation_id", "causation_id", "producer", "producer_version", "produced_at", "observation_id", "entity_id", "payload")
    EVENT_ID_FIELD_NUMBER: _ClassVar[int]
    EVENT_TYPE_FIELD_NUMBER: _ClassVar[int]
    EVENT_VERSION_FIELD_NUMBER: _ClassVar[int]
    INVESTIGATION_ID_FIELD_NUMBER: _ClassVar[int]
    CORRELATION_ID_FIELD_NUMBER: _ClassVar[int]
    CAUSATION_ID_FIELD_NUMBER: _ClassVar[int]
    PRODUCER_FIELD_NUMBER: _ClassVar[int]
    PRODUCER_VERSION_FIELD_NUMBER: _ClassVar[int]
    PRODUCED_AT_FIELD_NUMBER: _ClassVar[int]
    OBSERVATION_ID_FIELD_NUMBER: _ClassVar[int]
    ENTITY_ID_FIELD_NUMBER: _ClassVar[int]
    PAYLOAD_FIELD_NUMBER: _ClassVar[int]
    event_id: str
    event_type: str
    event_version: str
    investigation_id: str
    correlation_id: str
    causation_id: str
    producer: str
    producer_version: str
    produced_at: str
    observation_id: str
    entity_id: str
    payload: bytes
    def __init__(self, event_id: str | None = ..., event_type: str | None = ..., event_version: str | None = ..., investigation_id: str | None = ..., correlation_id: str | None = ..., causation_id: str | None = ..., producer: str | None = ..., producer_version: str | None = ..., produced_at: str | None = ..., observation_id: str | None = ..., entity_id: str | None = ..., payload: bytes | None = ...) -> None: ...
