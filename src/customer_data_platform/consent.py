"""Consent & privacy enforcement.

Consent is stored per profile per purpose. Access is purpose-based:
a profile's data may be used for a purpose only when consent for that
purpose is GRANTED — except TRANSACTIONAL, which is permitted by
default (contract necessity) unless explicitly DENIED. Erasure is
delegated to the profile store and audited here as well.
"""
from __future__ import annotations

import time

from .errors import ConsentDeniedError
from .models import ConsentRecord, ConsentStatus, Purpose, UnifiedProfile


class ConsentManager:
    def __init__(self) -> None:
        self._records: dict[tuple[str, str], ConsentRecord] = {}

    def set_consent(self, profile_id: str, purpose: Purpose | str,
                    status: ConsentStatus | str, source: str = "api") -> ConsentRecord:
        p = Purpose(purpose) if isinstance(purpose, str) else purpose
        s = ConsentStatus(status) if isinstance(status, str) else status
        rec = ConsentRecord(profile_id=profile_id, purpose=p, status=s,
                            updated_at=time.time(), source=source)
        self._records[(profile_id, p.value)] = rec
        return rec

    def get_consent(self, profile_id: str, purpose: Purpose | str) -> ConsentRecord | None:
        p = Purpose(purpose) if isinstance(purpose, str) else purpose
        return self._records.get((profile_id, p.value))

    def status_for(self, profile_id: str, purpose: Purpose | str) -> ConsentStatus:
        rec = self.get_consent(profile_id, purpose)
        return rec.status if rec else ConsentStatus.UNKNOWN

    def is_allowed(self, profile_id: str, purpose: Purpose | str) -> bool:
        p = Purpose(purpose) if isinstance(purpose, str) else purpose
        status = self.status_for(profile_id, p)
        if status == ConsentStatus.GRANTED:
            return True
        if status == ConsentStatus.DENIED:
            return False
        # UNKNOWN: only transactional use is allowed by default.
        return p == Purpose.TRANSACTIONAL

    def require(self, profile_id: str, purpose: Purpose | str) -> None:
        if not self.is_allowed(profile_id, purpose):
            raise ConsentDeniedError(
                f"profile {profile_id} has not granted consent for purpose {purpose}")

    def filter_allowed(self, profiles: list[UnifiedProfile],
                       purpose: Purpose | str) -> list[UnifiedProfile]:
        return [p for p in profiles if self.is_allowed(p.profile_id, purpose)]

    def records_for(self, profile_id: str) -> list[ConsentRecord]:
        return [r for (pid, _), r in sorted(self._records.items()) if pid == profile_id]

    def opt_out_all(self, profile_id: str, source: str = "api") -> list[ConsentRecord]:
        return [self.set_consent(profile_id, p, ConsentStatus.DENIED, source=source)
                for p in Purpose]
