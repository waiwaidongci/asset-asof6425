from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from src.config.database import connection
from src.constants.enums import Role, Status
from src.controllers.auth import allow, current
from src.models.borrow import Plan, PlanEvent
from src.models.identity import User
from src.models.jobs import Run
from src.schemas.requests import EventRequest, PlanRequest
from src.services import borrow
from src.services.audit import record
from src.utils import views

router = APIRouter(prefix='/plans')
writer = allow(Role.ADMIN, Role.ANALYST)


@router.get('')
def index(db: Session = Depends(connection), actor: User = Depends(current)):
    borrow.refresh_drafts(db)
    db.commit()
    plans = db.scalars(select(Plan).order_by(Plan.id.desc()).limit(100)).all()
    grouped = {}
    if plans:
        rows = db.scalars(select(PlanEvent).where(PlanEvent.plan_id.in_([item.id for item in plans]))).all()
        for event in rows:
            grouped.setdefault(event.plan_id, []).append(event)
    return [views.plan(item, views.plan_counts(grouped.get(item.id, []))) for item in plans]


@router.post('', status_code=201)
def create(body: PlanRequest, db: Session = Depends(connection), actor: User = Depends(writer)):
    run = db.get(Run, body.run_id)
    if not run or run.status != Status.COMPLETE:
        raise HTTPException(404, '找不到已完成的盘点运行，请先执行期末盘点')
    item = Plan(name=body.name, run_id=run.id, author=actor.username)
    db.add(item)
    db.flush()
    record(db, actor.username, 'plan.created', item.id, run_id=run.id)
    db.commit()
    return views.plan(item, views.plan_counts([]))


@router.get('/{plan_id}')
def detail(plan_id: int, db: Session = Depends(connection), actor: User = Depends(current)):
    plan = db.get(Plan, plan_id)
    if not plan:
        raise HTTPException(404, '找不到该排借方案')
    if plan.status == 'draft':
        borrow.lock(db)
        borrow.recompute(db, plan)
        db.commit()
    return borrow.detail(db, plan)


@router.post('/{plan_id}/events', status_code=201)
def add_event(plan_id: int, body: EventRequest, db: Session = Depends(connection),
              actor: User = Depends(writer)):
    plan = borrow.get_editable(db, plan_id)
    if len(borrow.events_of(db, plan.id)) >= borrow.MAX_EVENTS:
        raise ValueError(f'每个方案最多登记 {borrow.MAX_EVENTS} 场活动')
    if body.start_date > body.end_date:
        raise ValueError('开始日期须早于或等于结束日期')
    event = PlanEvent(plan_id=plan.id, name=body.name, start_date=body.start_date,
                      end_date=body.end_date, priority=body.priority.value,
                      lines=borrow.clean_lines(body.lines))
    db.add(event)
    db.flush()
    borrow.recompute(db, plan)
    record(db, actor.username, 'plan.event.added', event.id, plan_id=plan.id)
    db.commit()
    return borrow.detail(db, plan)


@router.post('/{plan_id}/events/{event_id}/remove')
def remove_event(plan_id: int, event_id: int, db: Session = Depends(connection),
                 actor: User = Depends(writer)):
    plan = borrow.get_editable(db, plan_id)
    event = db.get(PlanEvent, event_id)
    if not event or event.plan_id != plan.id:
        raise HTTPException(404, '找不到该场次')
    db.delete(event)
    db.flush()
    borrow.recompute(db, plan)
    record(db, actor.username, 'plan.event.removed', event_id, plan_id=plan.id)
    db.commit()
    return borrow.detail(db, plan)


@router.post('/{plan_id}/confirm')
def confirm(plan_id: int, db: Session = Depends(connection), actor: User = Depends(writer)):
    plan = borrow.confirm(db, plan_id, actor.username)
    db.commit()
    return borrow.detail(db, plan)
