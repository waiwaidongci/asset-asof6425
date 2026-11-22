from enum import StrEnum

class Role(StrEnum):
    ADMIN = 'admin'
    ANALYST = 'analyst'
    VIEWER = 'viewer'

class Status(StrEnum):
    QUEUED = 'queued'
    RUNNING = 'running'
    COMPLETE = 'complete'
    FAILED = 'failed'

class Review(StrEnum):
    PENDING = 'pending'
    ACCEPTED = 'accepted'
    RETURNED = 'returned'

class PlanStatus(StrEnum):
    DRAFT = 'draft'
    CONFIRMED = 'confirmed'

class Arrange(StrEnum):
    SCHEDULED = 'scheduled'
    PENDING = 'pending'
    CONFLICT = 'conflict'

class Priority(StrEnum):
    KEY = 'key'
    NORMAL = 'normal'
