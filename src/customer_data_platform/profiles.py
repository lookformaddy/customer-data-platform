"""Unified profile store.

Applies fragments and events to profiles, resolving identity on the
way in. Latest non-null value wins for descriptive fields (by
``observed_at``); identifiers accumulate. Erased profiles keep only a
tombstone so downstream systems can honour deletion.
"""
from __future__ import annotations

import time
import uuid

from .errors import UnknownProfileError
from .identity import IdentityResolver
from .models import ProfileFragment, RawEvent, UnifiedProfile


def _uid(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:12]}"


class ProfileStore:
    def __init__(self, resolver: IdentityResolver | None = None) -> None:
        self.resolver = resolver or IdentityResolver()
        self._profiles: dict[str, UnifiedProfile] = {}
        self._fragment_ts: dict[str, float] = {}  # profile_id -> last fragment ts

    # -- creation / application -------------------------------------------
    def _new_profile(self) -> UnifiedProfile:
        p = UnifiedProfile(profile_id=_uid("prof_"))
        self._profiles[p.profile_id] = p
        return p

    @staticmethod
    def _add_unique(lst: list[str], value: str | None) -> None:
        if value and value not in lst:
            lst.append(value)

    def apply_fragment(self, frag: ProfileFragment) -> UnifiedProfile:
        profiles = list(self._profiles.values())
        cand = self.resolver.find_match(frag, profiles)
        if cand and not cand.needs_review:
            profile = self._profiles[cand.profile_id]
            self.resolver.record_link(frag.fragment_id, profile.profile_id,
                                      cand.method, cand.score, cand.reason)
        else:
            profile = self._new_profile()
            if cand and cand.needs_review:
                self.resolver.log_audit(
                    "link", f"fragment {frag.fragment_id} scored {cand.score:.2f} "
                    f"vs {cand.profile_id} — below auto-link, created new profile",
                    [profile.profile_id, cand.profile_id])
        self._merge_fragment(profile, frag)
        return profile

    def _merge_fragment(self, profile: UnifiedProfile, frag: ProfileFragment) -> None:
        self._add_unique(profile.user_ids, frag.user_id)
        self._add_unique(profile.emails, frag.email)
        self._add_unique(profile.phones, frag.phone)
        self._add_unique(profile.anonymous_ids, frag.anonymous_id)
        self._add_unique(profile.device_ids, frag.device_id)
        self._add_unique(profile.sources, frag.source.value)
        last = self._fragment_ts.get(profile.profile_id, 0.0)
        if frag.observed_at >= last:
            for attr in ("first_name", "last_name", "city", "country"):
                v = getattr(frag, attr)
                if v:
                    setattr(profile, attr, v)
            profile.traits.update(frag.traits)
            self._fragment_ts[profile.profile_id] = frag.observed_at
        profile.updated_at = time.time()

    def apply_event(self, event: RawEvent) -> UnifiedProfile:
        # Build a lightweight fragment view for matching.
        frag = ProfileFragment(
            fragment_id=f"evt:{event.event_id}", source=event.source,
            observed_at=event.timestamp, user_id=event.user_id, email=event.email,
            phone=event.phone, anonymous_id=event.anonymous_id, device_id=event.device_id)
        profiles = list(self._profiles.values())
        cand = self.resolver.find_match(frag, profiles)
        if cand and not cand.needs_review:
            profile = self._profiles[cand.profile_id]
        else:
            profile = self._new_profile()
            self._merge_fragment(profile, frag)
        self._add_unique(profile.sources, event.source.value)
        profile.event_count += 1
        if event.event_type not in profile.event_types:
            profile.event_types.append(event.event_type)
        profile.updated_at = time.time()
        return profile

    # -- reads --------------------------------------------------------------
    def get(self, profile_id: str) -> UnifiedProfile:
        try:
            return self._profiles[profile_id]
        except KeyError:
            raise UnknownProfileError(f"unknown profile: {profile_id}") from None

    def list_profiles(self, *, active_only: bool = True) -> list[UnifiedProfile]:
        out = list(self._profiles.values())
        if active_only:
            out = [p for p in out if p.is_active]
        return out

    def find_by_identifier(self, kind: str, value: str) -> UnifiedProfile | None:
        attr = {"user_id": "user_ids", "email": "emails", "phone": "phones",
                "anonymous_id": "anonymous_ids", "device_id": "device_ids"}.get(kind)
        if attr is None:
            return None
        for p in self._profiles.values():
            if p.is_active and value in getattr(p, attr):
                return p
        return None

    def count(self, *, active_only: bool = True) -> int:
        return len(self.list_profiles(active_only=active_only))

    # -- erasure ------------------------------------------------------------
    def erase(self, profile_id: str, actor: str = "system") -> UnifiedProfile:
        profile = self.get(profile_id)
        profile.emails = []
        profile.phones = []
        profile.user_ids = []
        profile.anonymous_ids = []
        profile.device_ids = []
        profile.first_name = None
        profile.last_name = None
        profile.city = None
        profile.country = None
        profile.traits = {}
        profile.erased = True
        profile.updated_at = time.time()
        self.resolver.log_audit("erase", f"erased profile {profile_id}",
                                [profile_id], actor=actor)
        return profile
