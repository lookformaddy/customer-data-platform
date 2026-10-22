"""Segment builder: rule-based audiences over unified profiles.

Rules address profile fields directly (``city``, ``country``,
``event_count``) or traits via ``trait.<key>``, and event history via
``event_types`` (contains). Segments combine rules with AND/OR and
carry the purpose they will be activated for, so consent filtering
happens at activation time with the right purpose.
"""
from __future__ import annotations

import uuid
from typing import Any

from .errors import UnknownSegmentError, ValidationError
from .models import Purpose, Segment, SegmentRule, UnifiedProfile

OPERATORS = {"eq", "ne", "gt", "gte", "lt", "lte", "in", "contains", "exists"}


def _uid(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:12]}"


def field_value(profile: UnifiedProfile, field_name: str) -> Any:
    if field_name.startswith("trait."):
        return profile.traits.get(field_name[len("trait."):])
    if field_name == "email_count":
        return len(profile.emails)
    if field_name == "source_count":
        return len(profile.sources)
    return getattr(profile, field_name, None)


def evaluate_rule(profile: UnifiedProfile, rule: SegmentRule) -> bool:
    if rule.operator not in OPERATORS:
        raise ValidationError(f"unknown operator: {rule.operator}")
    actual = field_value(profile, rule.field)
    expected = rule.value
    if rule.operator == "exists":
        return actual is not None and actual != [] and actual != ""
    if actual is None:
        return False
    if rule.operator == "eq":
        return actual == expected
    if rule.operator == "ne":
        return actual != expected
    if rule.operator == "gt":
        return actual > expected
    if rule.operator == "gte":
        return actual >= expected
    if rule.operator == "lt":
        return actual < expected
    if rule.operator == "lte":
        return actual <= expected
    if rule.operator == "in":
        return actual in (expected or [])
    if rule.operator == "contains":
        return expected in actual
    return False


def evaluate_segment(profile: UnifiedProfile, segment: Segment) -> bool:
    if not segment.rules:
        return True
    results = [evaluate_rule(profile, r) for r in segment.rules]
    if segment.combinator.upper() == "OR":
        return any(results)
    return all(results)


class SegmentStore:
    def __init__(self) -> None:
        self._segments: dict[str, Segment] = {}

    def create(self, name: str, rules: list[SegmentRule], combinator: str = "AND",
               purpose: Purpose | str = Purpose.ANALYTICS) -> Segment:
        for r in rules:
            if r.operator not in OPERATORS:
                raise ValidationError(f"unknown operator: {r.operator}")
        seg = Segment(segment_id=_uid("seg_"), name=name, rules=list(rules),
                      combinator=combinator.upper(),
                      purpose=Purpose(purpose) if isinstance(purpose, str) else purpose)
        self._segments[seg.segment_id] = seg
        return seg

    def get(self, segment_id: str) -> Segment:
        try:
            return self._segments[segment_id]
        except KeyError:
            raise UnknownSegmentError(f"unknown segment: {segment_id}") from None

    def list_segments(self) -> list[Segment]:
        return list(self._segments.values())

    def members(self, segment: Segment, profiles: list[UnifiedProfile]) -> list[UnifiedProfile]:
        return [p for p in profiles if p.is_active and evaluate_segment(p, segment)]
