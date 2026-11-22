from datetime import date, datetime
from typing import Annotated
from pydantic import BaseModel, ConfigDict, Field
from src.constants.enums import Priority, Review

class Request(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')

class Credentials(Request):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)

class Upload(Request):
    name: str = Field(min_length=1, max_length=120)
    filename: str = Field(min_length=1, max_length=160)
    csv_text: str = Field(min_length=1, max_length=2_000_000)

class RunRequest(Request):
    dataset_id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=120)
    params: dict = Field(default_factory=dict)

class ReviewRequest(Request):
    review: Review
    note: str = Field(min_length=1, max_length=500)
    decision: str = Field(default='', max_length=120)

class ScheduleRequest(RunRequest):
    recipient: str = Field(min_length=1, max_length=100)
    first_at: datetime
    repeat_daily: bool = False

class PlanRequest(Request):
    name: str = Field(min_length=1, max_length=120)
    run_id: int = Field(gt=0)

class LineRequest(Request):
    tool: str = Field(min_length=1, max_length=120)
    quantity: int = Field(ge=1, le=99)
    substitutes: list[Annotated[str, Field(min_length=1, max_length=120)]] = Field(default_factory=list, max_length=5)

class EventRequest(Request):
    name: str = Field(min_length=1, max_length=120)
    start_date: date
    end_date: date
    priority: Priority
    lines: list[LineRequest] = Field(min_length=1, max_length=20)
