import pytest

from conftest import BASE, frag
from customer_data_platform.errors import ValidationError
from customer_data_platform.ingestion import Ingestor, validate_event, validate_fragment
from customer_data_platform.models import RawEvent, SourceType, normalize_email, normalize_phone


def test_normalize_email():
    assert normalize_email("  Alex@Example.COM ") == "alex@example.com"
    assert normalize_email("") is None
    assert normalize_email(None) is None


def test_normalize_phone_us_country_code():
    assert normalize_phone("+1 (512) 555-0142") == "5125550142"
    assert normalize_phone("512-555-0142") == "5125550142"


def test_event_identifiers():
    ev = RawEvent("e1", SourceType.WEB, "page_view", BASE, anonymous_id="a1", email="A@B.com")
    assert ev.identifiers()["email"] == "a@b.com"
    assert ev.identifiers()["anonymous_id"] == "a1"


def test_event_roundtrip():
    ev = RawEvent("e1", SourceType.MOBILE, "purchase", BASE, user_id="u1")
    assert RawEvent.from_dict(ev.to_dict()) == ev


def test_validate_event_no_identifier():
    ev = RawEvent("e1", SourceType.WEB, "page_view", BASE)
    assert any("no identifier" in p for p in validate_event(ev))


def test_validate_event_bad_email():
    ev = RawEvent("e1", SourceType.WEB, "page_view", BASE, email="not-an-email")
    assert any("invalid email" in p for p in validate_event(ev))


def test_validate_fragment_ok():
    assert validate_fragment(frag("f1", email="a@b.com")) == []


def test_ingest_dedup():
    ing = Ingestor()
    ev = RawEvent("e1", SourceType.WEB, "page_view", BASE, anonymous_id="a1")
    report = ing.ingest_events([ev, ev, ev])
    assert report.accepted == 1 and report.duplicates == 2


def test_ingest_rejects_invalid_non_strict():
    ing = Ingestor()
    bad = RawEvent("e1", SourceType.WEB, "page_view", BASE)
    report = ing.ingest_events([bad])
    assert report.rejected == 1 and report.accepted == 0


def test_ingest_strict_raises():
    ing = Ingestor()
    bad = RawEvent("e1", SourceType.WEB, "page_view", BASE)
    with pytest.raises(Exception):
        ing.ingest_events([bad], strict=True)


def test_ingest_single_invalid_raises():
    ing = Ingestor()
    with pytest.raises(ValidationError):
        ing.ingest_event(RawEvent("e1", SourceType.WEB, "page_view", -5, anonymous_id="a"))


def test_ingest_counts_by_source():
    ing = Ingestor()
    ing.ingest_events([
        RawEvent("e1", SourceType.WEB, "page_view", BASE, anonymous_id="a"),
        RawEvent("e2", SourceType.MOBILE, "app_open", BASE, anonymous_id="a"),
        RawEvent("e3", SourceType.WEB, "click", BASE, anonymous_id="a"),
    ])
    assert ing.event_counts_by_source() == {"web": 2, "mobile": 1}
    assert ing.event_counts_by_type()["page_view"] == 1


def test_ingest_fragments_report():
    ing = Ingestor()
    report = ing.ingest_fragments([frag("f1", email="a@b.com"), frag("f2")])
    assert report.accepted == 1 and report.rejected == 1
