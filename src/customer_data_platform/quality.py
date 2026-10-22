"""Data quality checks over the unified profile store.

Checks are pure functions returning ``QualityCheckResult`` so they
can run in CI, in the demo, or on a schedule against a live store.
Thresholds are parameters, not constants buried in the checks.
"""
from __future__ import annotations

from .models import QualityCheckResult, UnifiedProfile


def check_email_coverage(profiles: list[UnifiedProfile], min_ratio: float = 0.5) -> QualityCheckResult:
    active = [p for p in profiles if p.is_active]
    if not active:
        return QualityCheckResult("email_coverage", False, "no active profiles", 0.0)
    ratio = sum(1 for p in active if p.emails) / len(active)
    return QualityCheckResult("email_coverage", ratio >= min_ratio,
                              f"{ratio:.0%} of active profiles have an email (min {min_ratio:.0%})", ratio)


def check_no_orphan_events(profiles: list[UnifiedProfile]) -> QualityCheckResult:
    active = [p for p in profiles if p.is_active]
    orphans = [p for p in active if p.event_count > 0 and not (
        p.emails or p.user_ids or p.anonymous_ids or p.device_ids)]
    return QualityCheckResult("no_orphan_events", not orphans,
                              f"{len(orphans)} profiles have events but no identifier",
                              float(len(orphans)))


def check_no_duplicate_emails(profiles: list[UnifiedProfile]) -> QualityCheckResult:
    seen: dict[str, str] = {}
    dupes: list[str] = []
    for p in profiles:
        if not p.is_active:
            continue
        for e in p.emails:
            if e in seen and seen[e] != p.profile_id:
                dupes.append(e)
            seen[e] = p.profile_id
    return QualityCheckResult("no_duplicate_emails", not dupes,
                              f"duplicate emails across profiles: {sorted(set(dupes))}",
                              float(len(set(dupes))))


def check_no_erased_data(profiles: list[UnifiedProfile]) -> QualityCheckResult:
    leaks = [p.profile_id for p in profiles if p.erased and (p.emails or p.first_name or p.traits)]
    return QualityCheckResult("no_erased_data", not leaks,
                              f"erased profiles still holding PII: {leaks}", float(len(leaks)))


def check_identifier_completeness(profiles: list[UnifiedProfile], min_ratio: float = 0.8) -> QualityCheckResult:
    active = [p for p in profiles if p.is_active]
    if not active:
        return QualityCheckResult("identifier_completeness", False, "no active profiles", 0.0)
    ok = sum(1 for p in active if p.emails or p.user_ids or p.phones)
    ratio = ok / len(active)
    return QualityCheckResult("identifier_completeness", ratio >= min_ratio,
                              f"{ratio:.0%} of profiles have a strong identifier (min {min_ratio:.0%})", ratio)


def run_all_checks(profiles: list[UnifiedProfile]) -> list[QualityCheckResult]:
    return [check_email_coverage(profiles), check_no_orphan_events(profiles),
            check_no_duplicate_emails(profiles), check_no_erased_data(profiles),
            check_identifier_completeness(profiles)]


def quality_summary(profiles: list[UnifiedProfile]) -> dict:
    results = run_all_checks(profiles)
    return {"passed": sum(1 for r in results if r.passed), "total": len(results),
            "all_passed": all(r.passed for r in results),
            "checks": [r.to_dict() for r in results]}
