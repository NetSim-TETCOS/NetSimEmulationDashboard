from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


ExperimentMode = Literal[
    "BASELINE", "DELAY", "JITTER", "LOSS", "CONGESTION", "OUTAGE", "FDI", "RECOVERY", "CUSTOM"
]


class SessionStart(BaseModel):
    name: str = Field(default="NetSim Online Emulation Demo", min_length=1, max_length=120)
    instructor: str = Field(default="Instructor", min_length=1, max_length=80)


class ExperimentUpdate(BaseModel):
    mode: ExperimentMode
    label: str = Field(default="", max_length=240)


class MarkerCreate(BaseModel):
    label: str = Field(min_length=1, max_length=240)
    event_type: str = Field(default="MARKER", min_length=1, max_length=40)
    notes: str = Field(default="", max_length=1000)

    @field_validator("label", "event_type", "notes")
    @classmethod
    def strip_control_characters(cls, value: str) -> str:
        return "".join(ch for ch in value.strip() if ch >= " " or ch in "\t")
