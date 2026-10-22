"""Service layer and FastAPI app factory.

``CDPService`` holds the framework-free logic so it is testable
without a web stack. ``create_app`` wraps it in FastAPI, imported
lazily inside the factory — importing this module never requires
FastAPI to be installed.

    GET  /health               liveness
    GET  /profiles             unified profiles
    GET  /profiles/{id}        one profile (+ consent records)
    POST /events               ingest one event
    POST /fragments            ingest one profile fragment
    POST /consent              set consent for a profile + purpose
    GET  /segments             segments
    POST /segments             create a segment
    GET  /segments/{id}/members  segment members
    POST /activate             activate a segment to a mock sink
    POST /profiles/{id}/erase  erase (right-to-deletion)
    GET  /quality              data quality summary
    GET  /audit                identity audit log
"""
from __future__ import annotations

from typing import Any

from .activation import Activator, FileSink, WebhookSink
from .consent import ConsentManager
from .identity import IdentityResolver
from .ingestion import Ingestor
from .models import ConsentStatus, ProfileFragment, Purpose, RawEvent, SegmentRule, SourceType
from .profiles import ProfileStore
from .quality import quality_summary
from .segments import SegmentStore


class CDPService:
    def __init__(self) -> None:
        self.ingestor = Ingestor()
        self.store = ProfileStore(IdentityResolver())
        self.consent = ConsentManager()
        self.segments = SegmentStore()
        self.activator = Activator(self.consent)

    def ingest_event(self, data: dict[str, Any]) -> dict:
        event = RawEvent.from_dict(data)
        accepted = self.ingestor.ingest_event(event)
        profile = self.store.apply_event(event) if accepted else None
        return {"accepted": accepted, "profile_id": profile.profile_id if profile else None}

    def ingest_fragment(self, data: dict[str, Any]) -> dict:
        frag = ProfileFragment(
            fragment_id=data["fragment_id"], source=SourceType(data["source"]),
            observed_at=float(data["observed_at"]), user_id=data.get("user_id"),
            email=data.get("email"), phone=data.get("phone"),
            anonymous_id=data.get("anonymous_id"), device_id=data.get("device_id"),
            first_name=data.get("first_name"), last_name=data.get("last_name"),
            city=data.get("city"), country=data.get("country"),
            traits=dict(data.get("traits") or {}))
        self.ingestor.ingest_fragment(frag)
        profile = self.store.apply_fragment(frag)
        return {"profile_id": profile.profile_id}

    def list_profiles(self) -> list[dict]:
        return [p.to_dict() for p in self.store.list_profiles()]

    def get_profile(self, profile_id: str) -> dict:
        profile = self.store.get(profile_id)
        return {"profile": profile.to_dict(),
                "consent": [r.to_dict() for r in self.consent.records_for(profile_id)]}

    def set_consent(self, profile_id: str, purpose: str, status: str) -> dict:
        rec = self.consent.set_consent(profile_id, Purpose(purpose), ConsentStatus(status))
        return rec.to_dict()

    def create_segment(self, data: dict[str, Any]) -> dict:
        rules = [SegmentRule.from_dict(r) for r in data.get("rules", [])]
        seg = self.segments.create(data["name"], rules,
                                   combinator=data.get("combinator", "AND"),
                                   purpose=data.get("purpose", "analytics"))
        return seg.to_dict()

    def segment_members(self, segment_id: str) -> dict:
        seg = self.segments.get(segment_id)
        members = self.segments.members(seg, self.store.list_profiles())
        return {"segment_id": segment_id, "count": len(members),
                "members": [p.to_dict() for p in members]}

    def activate(self, segment_id: str, sink_name: str = "webhook") -> dict:
        seg = self.segments.get(segment_id)
        members = self.segments.members(seg, self.store.list_profiles())
        sink = WebhookSink() if sink_name == "webhook" else FileSink()
        return self.activator.activate(seg, members, sink).to_dict()

    def erase(self, profile_id: str) -> dict:
        return self.store.erase(profile_id).to_dict()

    def quality(self) -> dict:
        return quality_summary(self.store.list_profiles(active_only=False))

    def audit(self) -> list[dict]:
        return [a.to_dict() for a in self.store.resolver.audit]


def create_app(service: CDPService | None = None):  # type: ignore[no-untyped-def]
    try:
        from fastapi import FastAPI, HTTPException
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("install the api extra: pip install -e '.[api]'") from exc

    from .errors import CDPError

    svc = service or CDPService()
    app = FastAPI(title="Customer Data Platform", version="0.1.0")

    def _handle(fn):  # type: ignore[no-untyped-def]
        try:
            return fn()
        except CDPError as exc:
            status = 404 if "unknown" in str(exc) else 422
            raise HTTPException(status_code=status, detail=str(exc)) from exc

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/profiles")
    def profiles() -> dict:
        return {"profiles": svc.list_profiles()}

    @app.get("/profiles/{profile_id}")
    def one_profile(profile_id: str) -> dict:
        return _handle(lambda: svc.get_profile(profile_id))

    @app.post("/events")
    def events(data: dict) -> dict:
        return _handle(lambda: svc.ingest_event(data))

    @app.post("/fragments")
    def fragments(data: dict) -> dict:
        return _handle(lambda: svc.ingest_fragment(data))

    @app.post("/consent")
    def consent(data: dict) -> dict:
        return _handle(lambda: svc.set_consent(data["profile_id"], data["purpose"], data["status"]))

    @app.get("/segments")
    def segments() -> dict:
        return {"segments": [s.to_dict() for s in svc.segments.list_segments()]}

    @app.post("/segments")
    def create_segment(data: dict) -> dict:
        return _handle(lambda: svc.create_segment(data))

    @app.get("/segments/{segment_id}/members")
    def members(segment_id: str) -> dict:
        return _handle(lambda: svc.segment_members(segment_id))

    @app.post("/activate")
    def activate(data: dict) -> dict:
        return _handle(lambda: svc.activate(data["segment_id"], data.get("sink", "webhook")))

    @app.post("/profiles/{profile_id}/erase")
    def erase(profile_id: str) -> dict:
        return _handle(lambda: svc.erase(profile_id))

    @app.get("/quality")
    def quality() -> dict:
        return svc.quality()

    @app.get("/audit")
    def audit() -> dict:
        return {"audit": svc.audit()}

    return app
