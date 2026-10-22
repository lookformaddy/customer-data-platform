import pytest

from conftest import BASE, frag
from customer_data_platform.errors import MergeError, SplitError
from customer_data_platform.identity import (IdentityConfig, IdentityResolver,
                                             deterministic_match, name_similarity,
                                             probabilistic_score)
from customer_data_platform.models import SourceType, UnifiedProfile


def test_name_similarity():
    assert name_similarity("Alex Rivera", "Alex Rivera") == 1.0
    assert name_similarity("Alex Rivera", "Bob Jones") < 0.5
    assert name_similarity(None, "x") == 0.0


def test_deterministic_email_match(store):
    p = store.apply_fragment(frag("f1", email="a@b.com"))
    assert deterministic_match(frag("f2", email="a@b.com"), p) is not None


def test_deterministic_no_match(store):
    p = store.apply_fragment(frag("f1", email="a@b.com"))
    assert deterministic_match(frag("f2", email="c@d.com"), p) is None


def test_stitching_across_sources(store):
    store.apply_fragment(frag("f1", anonymous_id="anon-1"))
    store.apply_fragment(frag("f2", source=SourceType.MOBILE, anonymous_id="anon-1",
                                email="a@b.com", observed_at=BASE + 1))
    # anonymous_id is not a strong key, but device/anon probabilistic path
    # may or may not merge; email profile must be findable either way.
    assert store.find_by_identifier("email", "a@b.com") is not None


def test_email_stitching_merges(store):
    store.apply_fragment(frag("f1", email="a@b.com", first_name="Alex"))
    store.apply_fragment(frag("f2", source=SourceType.CRM, email="a@b.com",
                              user_id="u1", observed_at=BASE + 1))
    assert store.count() == 1
    p = store.find_by_identifier("user_id", "u1")
    assert p is not None and p.first_name == "Alex"


def test_distinct_people_stay_separate(store):
    store.apply_fragment(frag("f1", email="a@b.com"))
    store.apply_fragment(frag("f2", email="c@d.com"))
    assert store.count() == 2


def test_probabilistic_score_shared_device():
    profile = UnifiedProfile(profile_id="p1", device_ids=["dev-1"], city="Austin",
                             first_name="Alex", last_name="Rivera")
    score, signals = probabilistic_score(
        frag("f1", device_id="dev-1", city="Austin", first_name="Alex", last_name="Rivera"),
        profile)
    assert score > 0.8 and signals


def test_probabilistic_score_no_signals():
    profile = UnifiedProfile(profile_id="p1")
    score, signals = probabilistic_score(frag("f1", email="a@b.com"), profile)
    assert score == 0.0


def test_review_threshold_creates_new_profile(store):
    # Weak probabilistic-only match must not auto-merge.
    store.apply_fragment(frag("f1", email="a@b.com", city="Austin",
                              first_name="Alex", last_name="Rivera"))
    store.apply_fragment(frag("f2", anonymous_id="zz", city="Austin",
                              first_name="Alex", last_name="Rivera", observed_at=BASE + 1))
    assert store.count() == 2


def test_merge_profiles(store):
    a = store.apply_fragment(frag("f1", email="a@b.com"))
    b = store.apply_fragment(frag("f2", email="c@d.com"))
    store.resolver.merge_profiles(a, b)
    assert a.emails == ["a@b.com", "c@d.com"]
    assert b.merged_into == a.profile_id
    assert store.count() == 1
    assert any(e.action == "merge" for e in store.resolver.audit)


def test_merge_self_raises(store):
    a = store.apply_fragment(frag("f1", email="a@b.com"))
    with pytest.raises(MergeError):
        store.resolver.merge_profiles(a, a)


def test_split_unmerged_raises(store):
    a = store.apply_fragment(frag("f1", email="a@b.com"))
    with pytest.raises(SplitError):
        store.resolver.split_profile(a)


def test_split_after_merge(store):
    a = store.apply_fragment(frag("f1", email="a@b.com"))
    b = store.apply_fragment(frag("f2", email="c@d.com"))
    store.resolver.merge_profiles(a, b)
    new = store.resolver.split_profile(b)
    assert new.profile_id != b.profile_id
    assert b.merged_into is None


def test_latest_fragment_wins_for_city(store):
    store.apply_fragment(frag("f1", email="a@b.com", city="Austin"))
    store.apply_fragment(frag("f2", email="a@b.com", city="Dallas", observed_at=BASE + 5))
    store.apply_fragment(frag("f3", email="a@b.com", city="Houston", observed_at=BASE + 2))
    assert store.find_by_identifier("email", "a@b.com").city == "Dallas"


def test_event_application_counts(store):
    from customer_data_platform.models import RawEvent
    store.apply_event(RawEvent("e1", SourceType.WEB, "page_view", BASE, email="a@b.com"))
    store.apply_event(RawEvent("e2", SourceType.WEB, "purchase", BASE, email="a@b.com"))
    p = store.find_by_identifier("email", "a@b.com")
    assert p.event_count == 2 and "purchase" in p.event_types


def test_custom_thresholds():
    cfg = IdentityConfig(auto_link_threshold=0.5, review_threshold=0.3)
    assert cfg.auto_link_threshold == 0.5
