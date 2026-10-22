"""Customer Data Platform.

Multi-source event/profile ingestion, identity resolution and
stitching (deterministic rules + probabilistic scoring with merge /
split audit), a unified profile store with consent and privacy
enforcement, a segment builder, consent-gated activation to mock
sinks, and data quality checks — over fully synthetic data.
"""

from .activation import Activator, FileSink, WebhookSink
from .consent import ConsentManager
from .identity import IdentityConfig, IdentityResolver
from .ingestion import Ingestor
from .models import (ConsentStatus, ProfileFragment, Purpose, RawEvent,
                     Segment, SegmentRule, SourceType, UnifiedProfile)
from .profiles import ProfileStore
from .quality import quality_summary, run_all_checks
from .segments import SegmentStore

__version__ = "0.1.0"

__all__ = [
    "Activator", "ConsentManager", "ConsentStatus", "FileSink", "IdentityConfig",
    "IdentityResolver", "Ingestor", "ProfileFragment", "ProfileStore", "Purpose",
    "RawEvent", "Segment", "SegmentRule", "SegmentStore", "SourceType",
    "UnifiedProfile", "WebhookSink", "quality_summary", "run_all_checks",
]
