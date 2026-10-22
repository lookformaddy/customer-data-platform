import pytest

from conftest import frag
from customer_data_platform.demo import run_demo
from customer_data_platform.errors import UnknownProfileError
from customer_data_platform.models import UnifiedProfile
from customer_data_platform.quality import (check_no_duplicate_emails, check_no_erased_data,
                                            quality_summary, run_all_checks)
from customer_data_platform.service import CDPService


def test_erasure_wipes_pii(store):
    p = store.apply_fragment(frag("f1", email="a@b.com", first_name="Alex", traits={"x": 1}))
    store.erase(p.profile_id)
    erased = store.get(p.profile_id)
    assert erased.erased and erased.emails == [] and erased.first_name is None
    assert erased.traits == {}
    assert store.count() == 0  # erased profiles are not active


def test_get_unknown_profile_raises(store):
    with pytest.raises(UnknownProfileError):
        store.get("prof_nope")


def test_find_by_identifier_unknown_kind(store):
    assert store.find_by_identifier("shoe_size", "10") is None


def test_quality_all_pass_on_demo_data(store):
    store.apply_fragment(frag("f1", email="a@b.com"))
    store.apply_fragment(frag("f2", email="c@d.com"))
    summary = quality_summary(store.list_profiles(active_only=False))
    assert summary["all_passed"] and summary["total"] == 5


def test_quality_duplicate_email_detected():
    a = UnifiedProfile(profile_id="p1", emails=["x@y.com"])
    b = UnifiedProfile(profile_id="p2", emails=["x@y.com"])
    assert not check_no_duplicate_emails([a, b]).passed


def test_quality_erased_leak_detected():
    p = UnifiedProfile(profile_id="p1", emails=["x@y.com"], erased=True)
    assert not check_no_erased_data([p]).passed


def test_quality_empty_store():
    results = run_all_checks([])
    assert len(results) == 5


def test_service_flow():
    svc = CDPService()
    out = svc.ingest_fragment({"fragment_id": "f1", "source": "web", "observed_at": 1700000000.0,
                               "email": "a@b.com", "first_name": "Alex"})
    pid = out["profile_id"]
    assert svc.get_profile(pid)["profile"]["emails"] == ["a@b.com"]
    svc.set_consent(pid, "marketing", "granted")
    seg = svc.create_segment({"name": "all", "rules": [], "purpose": "marketing"})
    members = svc.segment_members(seg["segment_id"])
    assert members["count"] == 1
    act = svc.activate(seg["segment_id"], "webhook")
    assert act["delivered"] == 1
    assert svc.quality()["total"] == 5
    svc.erase(pid)
    assert svc.get_profile(pid)["profile"]["erased"] is True


def test_service_event_ingest():
    svc = CDPService()
    out = svc.ingest_event({"event_id": "e1", "source": "web", "event_type": "page_view",
                            "timestamp": 1700000000.0, "anonymous_id": "anon-1"})
    assert out["accepted"] is True and out["profile_id"]


def test_demo_ok():
    report = run_demo()
    assert report["demo_ok"] is True
    assert report["events_duplicates"] == 1
    assert report["activation"]["delivered"] == 1
    assert report["activation"]["skipped_no_consent"] == 1
    assert report["sam_erased"] is True
    assert report["quality_after_erasure"]["all_passed"] is True


def test_demo_alex_unified():
    report = run_demo()
    ids = report["alex_identifiers"]
    assert "u-100" in ids["user_id"] and "alex@example.com" in ids["email"]
    assert "anon-1" in ids["anonymous_id"]


def test_create_app_requires_fastapi_or_works():
    # If fastapi is installed the app builds; otherwise a clear RuntimeError.
    try:
        from customer_data_platform.service import create_app
        app = create_app()
        assert app is not None
    except RuntimeError as exc:
        assert "api extra" in str(exc)
