from __future__ import annotations
from dataclasses import dataclass
from enum import Enum

class PlanFormat(str, Enum):
    NL = "nl"
    YAML = "yaml"
    DSL = "dsl"
    MERMAID = "mermaid"

@dataclass
class Plan:
    format: PlanFormat
    content: str  # rendered plan text
