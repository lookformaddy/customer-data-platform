"""End-to-end demo over fully synthetic data.

Scenario: the same person appears as an anonymous web visitor, a
mobile signup, and a CRM record. Deterministic stitching unifies
them; a second person stays separate. Consent gates a marketing
segment activation, erasure wipes a profile, and quality checks run
over the final store.
"""
from __future__ import annotations

import time

from .activation import Activator, WebhookSink
from .consent import ConsentManager
from .identity import IdentityResolver
from .ingestion import Ingestor
from .models import ConsentStatus, ProfileFragment, Purpose, RawEvent, SegmentRule, SourceType
from .profiles import ProfileStore
from .quality import quality_summary
from .segments import SegmentStore

BASE = 1_700_000_000.0


def build_demo_platform() -> dict:
    ingestor = Ingestor()
    store = ProfileStore(IdentityResolver())
    consent = ConsentManager()
    segments = SegmentStore()
    activator = Activator(consent)

    frags = [
        ProfileFragment("f-web", SourceType.WEB, BASE, anonymous_id="anon-1",
                        device_id="dev-1", city="Austin", traits={"plan": "free"}),
        ProfileFragment("f-mobile", SourceType.MOBILE, BASE + 10, anonymous_id="anon-1",
                        email="alex@example.com", first_name="Alex", last_name="Rivera",
                        city="Austin", traits={"plan": "pro"}),
        ProfileFragment("f-crm", SourceType.CRM, BASE + 20, user_id="u-100",
                        email="alex@example.com", phone="+1 (512) 555-0142",
                        first_name="Alex", last_name="Rivera", city="Austin",
                        country="US", traits={"lifetime_value": 420}),
        ProfileFragment("f-other", SourceType.WEB, BASE + 30, anonymous_id="anon-9",
                        email="sam@example.com", first_name="Sam", last_name="Chen",
                        city="Denver", country="US", traits={"plan": "pro"}),
    ]
    events = [
        RawEvent("e1", SourceType.WEB, "page_view", BASE + 1, anonymous_id="anon-1"),
        RawEvent("e2", SourceType.MOBILE, "purchase", BASE + 11, email="alex@example.com"),
        RawEvent("e3", SourceType.WEB, "page_view", BASE + 31, email="sam@example.com"),
    ]
    frag_report = ingestor.ingest_fragments(frags)
    event_report = ingestor.ingest_events(events + [events[0]])  # duplicate e1

    profiles_by_frag = {}
    for f in frags:
        p = store.apply_fragment(f)
        profiles_by_frag[f.fragment_id] = p.profile_id
    for ev in events:
        store.apply_event(ev)

    alex = store.find_by_identifier("email", "alex@example.com")
    sam = store.find_by_identifier("email", "sam@example.com")
    assert alex is not None and sam is not None

    # Consent: Alex opts into marketing, Sam does not.
    consent.set_consent(alex.profile_id, Purpose.MARKETING, ConsentStatus.GRANTED, source="demo")
    consent.set_consent(sam.profile_id, Purpose.MARKETING, ConsentStatus.DENIED, source="demo")
    consent.set_consent(alex.profile_id, Purpose.ANALYTICS, ConsentStatus.GRANTED, source="demo")
    consent.set_consent(sam.profile_id, Purpose.ANALYTICS, ConsentStatus.GRANTED, source="demo")

    seg = segments.create("Pro plan customers",
                          [SegmentRule("trait.plan", "eq", "pro")],
                          purpose=Purpose.MARKETING)
    members = segments.members(seg, store.list_profiles())
    sink = WebhookSink()
    activation = activator.activate(seg, members, sink)

    quality_before = quality_summary(store.list_profiles(active_only=False))

    # Erasure for Sam.
    store.erase(sam.profile_id, actor="demo")
    quality_after = quality_summary(store.list_profiles(active_only=False))

    return {
        "fragments_accepted": frag_report.accepted,
        "events_accepted": event_report.accepted,
        "events_duplicates": event_report.duplicates,
        "active_profiles": store.count(),
        "alex_profile_id": alex.profile_id,
        "alex_identifiers": alex.all_identifiers(),
        "alex_event_count": alex.event_count,
        "identity_links": len(store.resolver.links),
        "audit_entries": [a.to_dict() for a in store.resolver.audit],
        "segment_members": len(members),
        "activation": activation.to_dict(),
        "webhook_calls": len(sink.calls),
        "quality_before_erasure": quality_before,
        "sam_erased": store.get(sam.profile_id).erased,
        "quality_after_erasure": quality_after,
        "demo_ok": (store.count() == 1 and activation.delivered == 1
                    and activation.skipped_no_consent == 1 and quality_after["all_passed"]),
        "generated_at": time.time(),
    }


def run_demo() -> dict:
    return build_demo_platform()
