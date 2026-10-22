import pytest

from conftest import frag
from customer_data_platform.activation import Activator, FileSink, WebhookSink, profile_payload
from customer_data_platform.consent import ConsentManager
from customer_data_platform.errors import ConsentDeniedError, UnknownSegmentError, ValidationError
from customer_data_platform.models import ConsentStatus, Purpose
from customer_data_platform.segments import SegmentStore, evaluate_rule
from customer_data_platform.models import SegmentRule


@pytest.fixture()
def two_profiles(store):
    a = store.apply_fragment(frag("f1", email="a@b.com", city="Austin", traits={"plan": "pro"}))
    b = store.apply_fragment(frag("f2", email="c@d.com", city="Denver", traits={"plan": "free"}))
    return a, b


def test_consent_default_unknown_denied_for_marketing():
    cm = ConsentManager()
    assert not cm.is_allowed("p1", Purpose.MARKETING)


def test_consent_transactional_allowed_by_default():
    cm = ConsentManager()
    assert cm.is_allowed("p1", Purpose.TRANSACTIONAL)


def test_consent_transactional_denied_when_explicit():
    cm = ConsentManager()
    cm.set_consent("p1", Purpose.TRANSACTIONAL, ConsentStatus.DENIED)
    assert not cm.is_allowed("p1", Purpose.TRANSACTIONAL)


def test_consent_grant_and_revoke():
    cm = ConsentManager()
    cm.set_consent("p1", Purpose.MARKETING, ConsentStatus.GRANTED)
    assert cm.is_allowed("p1", Purpose.MARKETING)
    cm.set_consent("p1", Purpose.MARKETING, ConsentStatus.DENIED)
    assert not cm.is_allowed("p1", Purpose.MARKETING)


def test_consent_require_raises():
    cm = ConsentManager()
    with pytest.raises(ConsentDeniedError):
        cm.require("p1", Purpose.MARKETING)


def test_opt_out_all():
    cm = ConsentManager()
    cm.set_consent("p1", Purpose.MARKETING, ConsentStatus.GRANTED)
    cm.opt_out_all("p1")
    assert not cm.is_allowed("p1", Purpose.TRANSACTIONAL)
    assert len(cm.records_for("p1")) == len(list(Purpose))


def test_segment_trait_rule(two_profiles):
    a, b = two_profiles
    assert evaluate_rule(a, SegmentRule("trait.plan", "eq", "pro"))
    assert not evaluate_rule(b, SegmentRule("trait.plan", "eq", "pro"))


def test_segment_operators(two_profiles):
    a, _ = two_profiles
    assert evaluate_rule(a, SegmentRule("city", "in", ["Austin", "Dallas"]))
    assert evaluate_rule(a, SegmentRule("event_count", "gte", 0))
    assert evaluate_rule(a, SegmentRule("city", "exists"))
    assert evaluate_rule(a, SegmentRule("city", "ne", "Denver"))
    assert not evaluate_rule(a, SegmentRule("trait.missing", "exists"))


def test_segment_bad_operator():
    ss = SegmentStore()
    with pytest.raises(ValidationError):
        ss.create("bad", [SegmentRule("city", "regex", "x")])


def test_segment_members_and_or(two_profiles, store):
    ss = SegmentStore()
    seg = ss.create("either city", [SegmentRule("city", "eq", "Austin"),
                                    SegmentRule("city", "eq", "Denver")], combinator="OR")
    assert len(ss.members(seg, store.list_profiles())) == 2
    seg_and = ss.create("both", [SegmentRule("city", "eq", "Austin"),
                                 SegmentRule("city", "eq", "Denver")], combinator="AND")
    assert len(ss.members(seg_and, store.list_profiles())) == 0


def test_segment_unknown_raises():
    with pytest.raises(UnknownSegmentError):
        SegmentStore().get("seg_nope")


def test_activation_consent_gating(two_profiles, store):
    a, b = two_profiles
    cm = ConsentManager()
    cm.set_consent(a.profile_id, Purpose.MARKETING, ConsentStatus.GRANTED)
    ss = SegmentStore()
    seg = ss.create("all", [], purpose=Purpose.MARKETING)
    sink = WebhookSink()
    result = Activator(cm).activate(seg, ss.members(seg, store.list_profiles()), sink)
    assert result.delivered == 1 and result.skipped_no_consent == 1
    assert len(sink.calls) == 1


def test_file_sink_activation(two_profiles, store):
    a, _ = two_profiles
    cm = ConsentManager()
    cm.set_consent(a.profile_id, Purpose.ANALYTICS, ConsentStatus.GRANTED)
    ss = SegmentStore()
    seg = ss.create("austin", [SegmentRule("city", "eq", "Austin")], purpose=Purpose.ANALYTICS)
    sink = FileSink()
    result = Activator(cm).activate(seg, ss.members(seg, store.list_profiles()), sink)
    assert result.delivered == 1 and len(sink.lines) == 1


def test_profile_payload_shape(two_profiles):
    a, _ = two_profiles
    payload = profile_payload(a)
    assert payload["emails"] == ["a@b.com"] and payload["city"] == "Austin"
