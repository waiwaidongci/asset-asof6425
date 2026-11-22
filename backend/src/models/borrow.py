from datetime import date, datetime
from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from src.config.database import Base
from src.constants.enums import Arrange, PlanStatus
from src.utils.time import now

class Plan(Base):
    __tablename__ = 'plans'

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    run_id: Mapped[int] = mapped_column(ForeignKey('runs.id'))
    status: Mapped[str] = mapped_column(String(20), default=PlanStatus.DRAFT, index=True)
    author: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(default=now)
    confirmed_at: Mapped[datetime | None]

class PlanEvent(Base):
    __tablename__ = 'plan_events'

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey('plans.id'), index=True)
    name: Mapped[str] = mapped_column(String(120))
    start_date: Mapped[date]
    end_date: Mapped[date]
    priority: Mapped[str] = mapped_column(String(10))
    lines: Mapped[list] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default=Arrange.PENDING)
    assignments: Mapped[list] = mapped_column(JSON, default=list)
    reason: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(default=now)
