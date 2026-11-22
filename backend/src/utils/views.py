from src.constants.enums import Arrange
from src.utils.time import iso


def dataset(item):
    return {'id': item.id, 'name': item.name, 'filename': item.filename, 'row_count': item.row_count,
            'checksum': item.checksum, 'author': item.author, 'created_at': iso(item.created_at)}


def run(item, detail=False):
    item_view = {'id': item.id, 'dataset_id': item.dataset_id, 'name': item.name, 'status': item.status,
                 'author': item.author, 'review': item.review, 'decision': item.decision,
                 'created_at': iso(item.created_at), 'finished_at': iso(item.finished_at),
                 'scheduled_at': iso(item.scheduled_at), 'schedule_id': item.schedule_id,
                 'has_export': bool(item.export_file), 'error': item.error}
    if detail:
        item_view.update(params=item.params, result=item.result, review_note=item.review_note)
    return item_view


def schedule(item):
    from src.domain.spec import SPEC
    return {'id': item.id, 'name': item.name, 'dataset_id': item.dataset_id, 'recipient': item.recipient,
            'next_at': iso(item.next_at), 'repeat_daily': item.repeat_daily, 'enabled': item.enabled,
            'next_report_day': item.params.get(SPEC['schedule_date_param']) if item.enabled else None}


def delivery(item):
    return {'id': item.id, 'run_id': item.run_id, 'recipient': item.recipient,
            'state': item.state, 'detail': item.detail, 'created_at': iso(item.created_at)}


def plan_counts(events):
    return {'scheduled': sum(1 for event in events if event.status == Arrange.SCHEDULED),
            'pending': sum(1 for event in events if event.status == Arrange.PENDING),
            'conflict': sum(1 for event in events if event.status == Arrange.CONFLICT),
            'first_pending_reason': next((event.reason for event in events
                                          if event.status == Arrange.PENDING and event.reason), None)}


def plan(item, counts):
    return {'id': item.id, 'name': item.name, 'status': item.status, 'run_id': item.run_id,
            'author': item.author, 'created_at': iso(item.created_at),
            'confirmed_at': iso(item.confirmed_at), **counts}


def plan_event(item):
    return {'id': item.id, 'name': item.name, 'start_date': item.start_date.isoformat(),
            'end_date': item.end_date.isoformat(), 'priority': item.priority, 'lines': item.lines,
            'status': item.status, 'assignments': item.assignments, 'reason': item.reason}
