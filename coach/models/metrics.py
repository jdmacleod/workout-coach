from dataclasses import dataclass
from datetime import date


@dataclass
class Metric:
    name: str
    value: float
    unit: str
    date: date
    source: str = "manual"
