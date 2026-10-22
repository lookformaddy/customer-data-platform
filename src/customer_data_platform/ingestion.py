"""Multi-source ingestion with validation and deduplication.

Events and profile fragments arrive from web, mobile, CRM, POS,
support and bulk imports. Ingestion normalises identifiers, rejects
malformed records with specific reasons, and deduplicates on
``event_id`` so retries never double-count.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from .errors import IngestionError, ValidationError
from .models import ProfileFragment, RawEvent, SourceType

ALLOWED_EVENT_TYPES = {
    "page_view", "click", "purchase", "add_to_cart", "signup",
    "login", "support_ticket", "email_open", "email_click",
    "app_open", "checkout", "refund", "identify",
}


@dataclass
class IngestReport:
    accepted: int = 0
    rejected: int = 0
    duplicates: int = 0
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"accepted": self.accepted, "rejected": self.rejected,
                "duplicates": self.duplicates, "reasons": list(self.reasons)}


def validate_event(event: RawEvent) -> list[str]:
    problems: list[str] = []
    if not event.event_id:
        problems.append("missing event_id")
    if not event.event_type:
        problems.append("missing event_type")
    if event.timestamp <= 0:
        problems.append("timestamp must be positive")
    if not event.identifiers():
        problems.append("event has no identifier (user_id/email/phone/anonymous_id/device_id)")
    if event.email and "@" not in event.email:
        problems.append(f"invalid email: {event.email}")
    return problems


def validate_fragment(frag: ProfileFragment) -> list[str]:
    problems: list[str] = []
    if not frag.fragment_id:
        problems.append("missing fragment_id")
    if frag.observed_at <= 0:
        problems.append("observed_at must be positive")
    if not frag.identifiers():
        problems.append("fragment has no identifier")
    if frag.email and "@" not in frag.email:
        problems.append(f"invalid email: {frag.email}")
    return problems


class Ingestor:
    """Stateful ingestor that tracks seen event ids for dedup."""

    def __init__(self) -> None:
        self._seen_event_ids: set[str] = set()
        self.events: list[RawEvent] = []
        self.fragments: list[ProfileFragment] = []

    def ingest_event(self, event: RawEvent) -> bool:
        problems = validate_event(event)
        if problems:
            raise ValidationError("; ".join(problems))
        if event.event_id in self._seen_event_ids:
            return False
        self._seen_event_ids.add(event.event_id)
        self.events.append(event)
        return True

    def ingest_events(self, events: Iterable[RawEvent], *, strict: bool = False) -> IngestReport:
        report = IngestReport()
        for ev in events:
            try:
                ok = self.ingest_event(ev)
            except ValidationError as exc:
                if strict:
                    raise IngestionError(str(exc)) from exc
                report.rejected += 1
                report.reasons.append(str(exc))
                continue
            if ok:
                report.accepted += 1
            else:
                report.duplicates += 1
        return report

    def ingest_fragment(self, frag: ProfileFragment) -> bool:
        problems = validate_fragment(frag)
        if problems:
            raise ValidationError("; ".join(problems))
        self.fragments.append(frag)
        return True

    def ingest_fragments(self, frags: Iterable[ProfileFragment]) -> IngestReport:
        report = IngestReport()
        for f in frags:
            try:
                self.ingest_fragment(f)
                report.accepted += 1
            except ValidationError as exc:
                report.rejected += 1
                report.reasons.append(str(exc))
        return report

    def event_counts_by_source(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for ev in self.events:
            counts[ev.source.value] = counts.get(ev.source.value, 0) + 1
        return counts

    def event_counts_by_type(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for ev in self.events:
            counts[ev.event_type] = counts.get(ev.event_type, 0) + 1
        return counts
