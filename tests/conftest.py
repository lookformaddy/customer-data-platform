import pytest

from customer_data_platform.identity import IdentityResolver
from customer_data_platform.models import ProfileFragment, SourceType
from customer_data_platform.profiles import ProfileStore

BASE = 1_700_000_000.0


@pytest.fixture()
def store():
    return ProfileStore(IdentityResolver())


def frag(fid, **kw):
    kw.setdefault("source", SourceType.WEB)
    kw.setdefault("observed_at", BASE)
    return ProfileFragment(fid, **kw)
