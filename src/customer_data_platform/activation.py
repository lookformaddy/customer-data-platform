"""Activation: deliver segment audiences to downstream sinks.

Two mock sinks ship in the box — a webhook sink that records payloads
in memory (standing in for an HTTP POST) and a file sink that writes
JSON lines to a buffer/path. Activation is consent-gated: profiles
without consent for the segment's purpose are skipped and counted,
never silently included.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from .consent import ConsentManager
from .errors import ActivationError
from .models import ActivationResult, Segment, UnifiedProfile


def _uid(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:12]}"


def profile_payload(profile: UnifiedProfile) -> dict[str, Any]:
    """Minimal activation payload — identifiers + segmentation traits only."""
    return {"profile_id": profile.profile_id,
            "emails": list(profile.emails),
            "user_ids": list(profile.user_ids),
            "first_name": profile.first_name,
            "last_name": profile.last_name,
            "city": profile.city, "country": profile.country,
            "traits": dict(profile.traits)}


class WebhookSink:
    name = "webhook"

    def __init__(self, url: str = "https://example.invalid/hook") -> None:
        self.url = url
        self.calls: list[dict[str, Any]] = []

    def deliver(self, payloads: list[dict[str, Any]]) -> int:
        if not self.url:
            raise ActivationError("webhook url is empty")
        self.calls.append({"url": self.url, "count": len(payloads), "payloads": payloads})
        return len(payloads)


class FileSink:
    name = "file"

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else None
        self.lines: list[str] = []

    def deliver(self, payloads: list[dict[str, Any]]) -> int:
        for p in payloads:
            self.lines.append(json.dumps(p, default=str))
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text("\n".join(self.lines) + ("\n" if self.lines else ""))
        return len(payloads)


SINKS = {"webhook": WebhookSink, "file": FileSink}


class Activator:
    def __init__(self, consent: ConsentManager) -> None:
        self.consent = consent
        self.history: list[ActivationResult] = []

    def activate(self, segment: Segment, members: list[UnifiedProfile],
                 sink: WebhookSink | FileSink) -> ActivationResult:
        allowed = self.consent.filter_allowed(members, segment.purpose)
        skipped = len(members) - len(allowed)
        payloads = [profile_payload(p) for p in allowed]
        delivered = sink.deliver(payloads)
        result = ActivationResult(
            activation_id=_uid("act_"), segment_id=segment.segment_id,
            sink=sink.name, profile_count=len(members), delivered=delivered,
            skipped_no_consent=skipped, payload_preview=payloads[:5])
        self.history.append(result)
        return result
