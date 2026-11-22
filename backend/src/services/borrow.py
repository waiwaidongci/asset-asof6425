"""排借方案的落库编排：整案重算、确认串行化与源数据刷新。"""

from fastapi import HTTPException
from sqlalchemy import select, text
from src.constants.enums import Arrange, PlanStatus
from src.domain.analysis import register_at
from src.domain.borrow import allocate, pool_summary
from src.models.borrow import Plan, PlanEvent
from src.models.jobs import Run
from src.models.source import Dataset
from src.services.audit import record
from src.utils import views
from src.utils.time import now

_LOCK_KEY = 20261121
_STATUS_LABELS = {'in_custody': '在管', 'checked_out': '借出', 'retired': '退役'}
MAX_EVENTS = 100


def lock(db):
    """排借写操作的事务级咨询锁，确认与刷新据此串行。"""
    db.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': _LOCK_KEY})


def clean_lines(lines):
    """整理需求行：替用品去空去重，且不得与主工具同名。"""
    cleaned = []
    for index, line in enumerate(lines, 1):
        substitutes = []
        for name in line.substitutes:
            if name == line.tool or name in substitutes:
                raise ValueError(f'第 {index} 项需求的替用品「{name}」与主工具相同或重复')
            substitutes.append(name)
        cleaned.append({'tool': line.tool, 'quantity': line.quantity, 'substitutes': substitutes})
    return cleaned


def register_of(db, run_id):
    run = db.get(Run, run_id)
    dataset = db.get(Dataset, run.dataset_id)
    return run, register_at(dataset.rows, run.params['as_of_date'])


def events_of(db, plan_id):
    return db.scalars(select(PlanEvent).where(PlanEvent.plan_id == plan_id)
                      .order_by(PlanEvent.id)).all()


def _claims(rows):
    return [{'asset_id': item['asset_id'], 'start': event.start_date, 'end': event.end_date}
            for event in rows for item in event.assignments]


def _occupied_elsewhere(db, plan_id):
    rows = db.scalars(select(PlanEvent).join(Plan, PlanEvent.plan_id == Plan.id)
                      .where(Plan.status == PlanStatus.CONFIRMED, Plan.id != plan_id,
                             PlanEvent.status.in_([Arrange.SCHEDULED, Arrange.CONFLICT]))).all()
    return _claims(rows)


def _inputs(events):
    return [{'key': event.id, 'start': event.start_date, 'end': event.end_date,
             'priority': event.priority, 'lines': event.lines} for event in events]


def _apply(events, results):
    for event in events:
        outcome = results[event.id]
        event.status = outcome['status']
        event.assignments = outcome['assignments']
        event.reason = outcome['reason'][:500] if outcome['reason'] else None


def recompute(db, plan, register=None):
    """整案重算：拟定中方案的编辑与确认前重算。"""
    if register is None:
        _, register = register_of(db, plan.run_id)
    events = events_of(db, plan.id)
    _apply(events, allocate(_inputs(events), register, _occupied_elsewhere(db, plan.id)))
    return events


def get_editable(db, plan_id):
    lock(db)
    plan = db.get(Plan, plan_id)
    if not plan:
        raise HTTPException(404, '找不到该排借方案')
    if plan.status != PlanStatus.DRAFT:
        raise HTTPException(409, '方案已确认，场次与安排已锁定')
    return plan


def confirm(db, plan_id, actor):
    """确认方案：持锁后按其他已确认方案的占用整案重算，再锁定场次。"""
    lock(db)
    plan = db.get(Plan, plan_id)
    if not plan:
        raise HTTPException(404, '找不到该排借方案')
    if plan.status != PlanStatus.DRAFT:
        raise HTTPException(409, '方案已确认，请勿重复操作')
    events = events_of(db, plan.id)
    if not events:
        raise HTTPException(409, '请先登记至少一场活动再确认')
    _apply(events, allocate(_inputs(events), register_of(db, plan.run_id)[1],
                            _occupied_elsewhere(db, plan.id)))
    plan.status = PlanStatus.CONFIRMED
    plan.confirmed_at = now()
    record(db, actor, 'plan.confirmed', plan.id,
           scheduled=sum(1 for event in events if event.status == Arrange.SCHEDULED),
           pending=sum(1 for event in events if event.status == Arrange.PENDING))
    return plan


def refresh_plans(db, run):
    """新盘点完成后刷新全部方案：待排重算，已确认安排遇新借出标冲突。"""
    plans = db.scalars(select(Plan).order_by(Plan.id)).all()
    if not plans:
        return
    lock(db)
    as_of = run.params['as_of_date']
    register = register_at(db.get(Dataset, run.dataset_id).rows, as_of)
    for plan in plans:
        source = db.get(Run, plan.run_id)
        if source and source.params['as_of_date'] > as_of:
            continue
        plan.run_id = run.id
        if plan.status == PlanStatus.CONFIRMED:
            _refresh_confirmed(db, plan, register)
        else:
            recompute(db, plan, register)
        record(db, 'worker', 'plan.refreshed', plan.id, run_id=run.id)


def _refresh_confirmed(db, plan, register):
    labels = {item['asset_id']: _STATUS_LABELS.get(item['status'], item['status']) for item in register}
    events = events_of(db, plan.id)
    kept = []
    for event in events:
        if event.status == Arrange.PENDING:
            continue
        gone = sorted({item['asset_id'] for item in event.assignments
                       if labels.get(item['asset_id']) != '在管'})
        if gone and event.status != Arrange.CONFLICT:
            event.status = Arrange.CONFLICT
            event.reason = ('、'.join(f'「{asset}」最新盘点为{labels.get(asset, "已不在册")}'
                                      for asset in gone) + '，原安排保留')[:500]
            record(db, 'worker', 'plan.event.conflict', event.id, plan_id=plan.id)
        elif not gone and event.status == Arrange.CONFLICT:
            event.status = Arrange.SCHEDULED
            event.reason = None
            record(db, 'worker', 'plan.event.recovered', event.id, plan_id=plan.id)
        kept.append(event)
    pending = [event for event in events if event.status == Arrange.PENDING]
    if pending:
        occupied = _occupied_elsewhere(db, plan.id) + _claims(kept)
        _apply(pending, allocate(_inputs(pending), register, occupied))


def refresh_drafts(db):
    """查询前重算全部拟定中方案，让列表与详情展示最新的占用情况。"""
    drafts = db.scalars(select(Plan).where(Plan.status == PlanStatus.DRAFT)).all()
    if not drafts:
        return
    lock(db)
    registers = {}
    for plan in drafts:
        if plan.run_id not in registers:
            registers[plan.run_id] = register_of(db, plan.run_id)[1]
        recompute(db, plan, registers[plan.run_id])


def detail(db, plan):
    run, register = register_of(db, plan.run_id)
    events = events_of(db, plan.id)
    return {**views.plan(plan, views.plan_counts(events)), 'run_name': run.name,
            'as_of_date': run.params['as_of_date'], 'pool': pool_summary(register),
            'events': [views.plan_event(event) for event in events]}
