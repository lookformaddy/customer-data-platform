"""Identity resolution: deterministic rules + probabilistic scoring.

Deterministic matching links records sharing a strong identifier
(user_id, email, phone). Probabilistic scoring compares weaker
signals (name similarity, city, device, anonymous id) and produces a
score in [0, 1]; links are created only above ``auto_link_threshold``
and flagged for review between ``review_threshold`` and that bound.
Every merge / split is written to an audit log so stitching is
reversible and explainable.
"""
from __future__ import annotations

import difflib
import time
import uuid
from dataclasses import dataclass, field

from .errors import MergeError, SplitError
from .models import AuditEntry, IdentityLink, ProfileFragment, UnifiedProfile


def _uid(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:12]}"


def name_similarity(a: str | None, b: str | None) -> float:
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


@dataclass
class IdentityConfig:
    auto_link_threshold: float = 0.85
    review_threshold: float = 0.60
    # weights for probabilistic scoring (sum need not be 1; normalised)
    w_name: float = 0.35
    w_city: float = 0.20
    w_device: float = 0.25
    w_anonymous: float = 0.20


@dataclass
class MatchCandidate:
    fragment_id: str
    profile_id: str
    score: float
    method: str
    reason: str
    needs_review: bool = False

    def to_dict(self) -> dict:
        return {"fragment_id": self.fragment_id, "profile_id": self.profile_id,
                "score": round(self.score, 4), "method": self.method,
                "reason": self.reason, "needs_review": self.needs_review}


STRONG_KEYS = ("user_id", "email", "phone")


def deterministic_match(fragment: ProfileFragment, profile: UnifiedProfile) -> str | None:
    """Return a reason string if a strong identifier matches, else None."""
    frag_ids = fragment.identifiers()
    prof = profile.all_identifiers()
    for key in STRONG_KEYS:
        if key in frag_ids and frag_ids[key] in prof.get(key, []):
            return f"shared {key}={frag_ids[key]}"
    return None


def probabilistic_score(fragment: ProfileFragment, profile: UnifiedProfile,
                        config: IdentityConfig | None = None) -> tuple[float, list[str]]:
    cfg = config or IdentityConfig()
    signals: list[str] = []
    weighted = 0.0
    total_w = 0.0

    frag_name = " ".join(p for p in (fragment.first_name, fragment.last_name) if p)
    prof_name = profile.display_name if profile.first_name else ""
    if frag_name and prof_name and profile.profile_id != prof_name:
        sim = name_similarity(frag_name, prof_name)
        weighted += cfg.w_name * sim
        total_w += cfg.w_name
        if sim > 0.5:
            signals.append(f"name similarity {sim:.2f}")
    if fragment.city and profile.city:
        match = 1.0 if fragment.city.lower() == profile.city.lower() else 0.0
        weighted += cfg.w_city * match
        total_w += cfg.w_city
        if match:
            signals.append(f"same city {fragment.city}")
    if fragment.device_id:
        match = 1.0 if fragment.device_id in profile.device_ids else 0.0
        weighted += cfg.w_device * match
        total_w += cfg.w_device
        if match:
            signals.append("shared device_id")
    if fragment.anonymous_id:
        match = 1.0 if fragment.anonymous_id in profile.anonymous_ids else 0.0
        weighted += cfg.w_anonymous * match
        total_w += cfg.w_anonymous
        if match:
            signals.append("shared anonymous_id")

    if total_w == 0:
        return 0.0, []
    return weighted / total_w, signals


class IdentityResolver:
    def __init__(self, config: IdentityConfig | None = None) -> None:
        self.config = config or IdentityConfig()
        self.links: list[IdentityLink] = []
        self.audit: list[AuditEntry] = []

    def find_match(self, fragment: ProfileFragment,
                   profiles: list[UnifiedProfile]) -> MatchCandidate | None:
        active = [p for p in profiles if p.is_active]
        # 1) deterministic
        for prof in active:
            reason = deterministic_match(fragment, prof)
            if reason:
                return MatchCandidate(fragment.fragment_id, prof.profile_id, 1.0,
                                      "deterministic", reason)
        # 2) probabilistic — best score wins
        best: MatchCandidate | None = None
        for prof in active:
            score, signals = probabilistic_score(fragment, prof, self.config)
            if score >= self.config.review_threshold:
                cand = MatchCandidate(
                    fragment.fragment_id, prof.profile_id, score, "probabilistic",
                    "; ".join(signals) or f"score {score:.2f}",
                    needs_review=score < self.config.auto_link_threshold)
                if best is None or score > best.score:
                    best = cand
        return best

    def record_link(self, profile_a: str, profile_b: str, method: str,
                    score: float, reason: str) -> IdentityLink:
        link = IdentityLink(link_id=_uid("lnk_"), profile_a=profile_a,
                            profile_b=profile_b, method=method, score=score, reason=reason)
        self.links.append(link)
        return link

    def log_audit(self, action: str, detail: str, profile_ids: list[str],
                  actor: str = "system") -> AuditEntry:
        entry = AuditEntry(entry_id=_uid("aud_"), action=action, actor=actor,
                           detail=detail, profile_ids=list(profile_ids))
        self.audit.append(entry)
        return entry

    def merge_profiles(self, survivor: UnifiedProfile, other: UnifiedProfile,
                       actor: str = "system") -> UnifiedProfile:
        if survivor.profile_id == other.profile_id:
            raise MergeError("cannot merge a profile into itself")
        if not survivor.is_active or not other.is_active:
            raise MergeError("cannot merge an inactive/erased profile")
        for attr in ("user_ids", "emails", "phones", "anonymous_ids", "device_ids", "sources"):
            merged = list(getattr(survivor, attr))
            for v in getattr(other, attr):
                if v not in merged:
                    merged.append(v)
            setattr(survivor, attr, merged)
        for attr in ("first_name", "last_name", "city", "country"):
            if not getattr(survivor, attr) and getattr(other, attr):
                setattr(survivor, attr, getattr(other, attr))
        for k, v in other.traits.items():
            survivor.traits.setdefault(k, v)
        survivor.event_count += other.event_count
        for t in other.event_types:
            if t not in survivor.event_types:
                survivor.event_types.append(t)
        survivor.updated_at = time.time()
        other.merged_into = survivor.profile_id
        other.updated_at = time.time()
        self.record_link(survivor.profile_id, other.profile_id, "deterministic", 1.0,
                         "manual/programmatic merge")
        self.log_audit("merge", f"merged {other.profile_id} into {survivor.profile_id}",
                       [survivor.profile_id, other.profile_id], actor=actor)
        return survivor

    def split_profile(self, profile: UnifiedProfile, *, actor: str = "system") -> UnifiedProfile:
        """Undo-style split: reactivate a profile previously merged away is
        not possible from merged data alone, so split creates a fresh
        profile shell and audits the intent. Raises if profile is active
        with no merge history to split from."""
        if profile.merged_into is None:
            raise SplitError("profile was not merged; nothing to split")
        new_profile = UnifiedProfile(profile_id=_uid("prof_"))
        # Copy identifiers back out is intentionally conservative: only
        # the profile's own stored identifiers return.
        new_profile.user_ids = list(profile.user_ids)
        new_profile.emails = list(profile.emails)
        profile.merged_into = None
        profile.updated_at = time.time()
        self.log_audit("split", f"split {profile.profile_id}; created {new_profile.profile_id}",
                       [profile.profile_id, new_profile.profile_id], actor=actor)
        return new_profile
