"""Typed domain models for the Customer Data Platform.

All models are plain dataclasses with ``to_dict`` / ``from_dict`` helpers
so they serialise cleanly for APIs, files and tests without any web
framework dependency.
"""
from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


def _now() -> float:
    return time.time()


def _uid(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:12]}"


def normalize_email(email: str | None) -> str | None:
    if not email:
        return None
    e = email.strip().lower()
    return e or None


def normalize_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    digits = "".join(c for c in phone if c.isdigit())
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits or None


def hash_identifier(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:16]


class SourceType(str, Enum):
    WEB = "web"
    MOBILE = "mobile"
    CRM = "crm"
    POS = "pos"
    SUPPORT = "support"
    IMPORT = "import"


class Purpose(str, Enum):
    MARKETING = "marketing"
    ANALYTICS = "analytics"
    PERSONALIZATION = "personalization"
    SUPPORT = "support"
    TRANSACTIONAL = "transactional"


class ConsentStatus(str, Enum):
    GRANTED = "granted"
    DENIED = "denied"
    UNKNOWN = "unknown"


@dataclass
class RawEvent:
    event_id: str
    source: SourceType
    event_type: str
    timestamp: float
    anonymous_id: str | None = None
    user_id: str | None = None
    email: str | None = None
    phone: str | None = None
    device_id: str | None = None
    properties: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.email = normalize_email(self.email)
        self.phone = normalize_phone(self.phone)
        if isinstance(self.source, str):
            self.source = SourceType(self.source)

    def identifiers(self) -> dict[str, str]:
        out: dict[str, str] = {}
        if self.user_id:
            out["user_id"] = self.user_id
        if self.email:
            out["email"] = self.email
        if self.phone:
            out["phone"] = self.phone
        if self.anonymous_id:
            out["anonymous_id"] = self.anonymous_id
        if self.device_id:
            out["device_id"] = self.device_id
        return out

    def to_dict(self) -> dict[str, Any]:
        return {"event_id": self.event_id, "source": self.source.value,
                "event_type": self.event_type, "timestamp": self.timestamp,
                "anonymous_id": self.anonymous_id, "user_id": self.user_id,
                "email": self.email, "phone": self.phone,
                "device_id": self.device_id, "properties": dict(self.properties)}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "RawEvent":
        return cls(event_id=d["event_id"], source=SourceType(d["source"]),
                   event_type=d["event_type"], timestamp=float(d["timestamp"]),
                   anonymous_id=d.get("anonymous_id"), user_id=d.get("user_id"),
                   email=d.get("email"), phone=d.get("phone"),
                   device_id=d.get("device_id"), properties=dict(d.get("properties") or {}))


@dataclass
class ProfileFragment:
    """A partial profile observed from one source."""
    fragment_id: str
    source: SourceType
    observed_at: float
    user_id: str | None = None
    email: str | None = None
    phone: str | None = None
    anonymous_id: str | None = None
    device_id: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    city: str | None = None
    country: str | None = None
    traits: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.email = normalize_email(self.email)
        self.phone = normalize_phone(self.phone)
        if isinstance(self.source, str):
            self.source = SourceType(self.source)

    def identifiers(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for k in ("user_id", "email", "phone", "anonymous_id", "device_id"):
            v = getattr(self, k)
            if v:
                out[k] = v
        return out

    def to_dict(self) -> dict[str, Any]:
        return {"fragment_id": self.fragment_id, "source": self.source.value,
                "observed_at": self.observed_at, "user_id": self.user_id,
                "email": self.email, "phone": self.phone,
                "anonymous_id": self.anonymous_id, "device_id": self.device_id,
                "first_name": self.first_name, "last_name": self.last_name,
                "city": self.city, "country": self.country, "traits": dict(self.traits)}


@dataclass
class IdentityLink:
    link_id: str
    profile_a: str
    profile_b: str
    method: str  # deterministic | probabilistic
    score: float
    reason: str
    created_at: float = field(default_factory=_now)
    active: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {"link_id": self.link_id, "profile_a": self.profile_a,
                "profile_b": self.profile_b, "method": self.method,
                "score": self.score, "reason": self.reason,
                "created_at": self.created_at, "active": self.active}


@dataclass
class AuditEntry:
    entry_id: str
    action: str  # merge | split | link | unlink | erase
    actor: str
    detail: str
    profile_ids: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return {"entry_id": self.entry_id, "action": self.action, "actor": self.actor,
                "detail": self.detail, "profile_ids": list(self.profile_ids),
                "created_at": self.created_at}


@dataclass
class UnifiedProfile:
    profile_id: str
    created_at: float = field(default_factory=_now)
    updated_at: float = field(default_factory=_now)
    user_ids: list[str] = field(default_factory=list)
    emails: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)
    anonymous_ids: list[str] = field(default_factory=list)
    device_ids: list[str] = field(default_factory=list)
    first_name: str | None = None
    last_name: str | None = None
    city: str | None = None
    country: str | None = None
    traits: dict[str, Any] = field(default_factory=dict)
    sources: list[str] = field(default_factory=list)
    event_count: int = 0
    event_types: list[str] = field(default_factory=list)
    merged_into: str | None = None
    erased: bool = False

    @property
    def is_active(self) -> bool:
        return self.merged_into is None and not self.erased

    @property
    def display_name(self) -> str:
        parts = [p for p in (self.first_name, self.last_name) if p]
        return " ".join(parts) if parts else self.profile_id

    def all_identifiers(self) -> dict[str, list[str]]:
        return {"user_id": list(self.user_ids), "email": list(self.emails),
                "phone": list(self.phones), "anonymous_id": list(self.anonymous_ids),
                "device_id": list(self.device_ids)}

    def to_dict(self) -> dict[str, Any]:
        return {"profile_id": self.profile_id, "created_at": self.created_at,
                "updated_at": self.updated_at, "user_ids": list(self.user_ids),
                "emails": list(self.emails), "phones": list(self.phones),
                "anonymous_ids": list(self.anonymous_ids), "device_ids": list(self.device_ids),
                "first_name": self.first_name, "last_name": self.last_name,
                "city": self.city, "country": self.country, "traits": dict(self.traits),
                "sources": list(self.sources), "event_count": self.event_count,
                "event_types": list(self.event_types), "merged_into": self.merged_into,
                "erased": self.erased, "display_name": self.display_name}


@dataclass
class ConsentRecord:
    profile_id: str
    purpose: Purpose
    status: ConsentStatus
    updated_at: float = field(default_factory=_now)
    source: str = "unknown"

    def __post_init__(self) -> None:
        if isinstance(self.purpose, str):
            self.purpose = Purpose(self.purpose)
        if isinstance(self.status, str):
            self.status = ConsentStatus(self.status)

    def to_dict(self) -> dict[str, Any]:
        return {"profile_id": self.profile_id, "purpose": self.purpose.value,
                "status": self.status.value, "updated_at": self.updated_at,
                "source": self.source}


@dataclass
class SegmentRule:
    field: str
    operator: str  # eq, ne, gt, gte, lt, lte, in, contains, exists
    value: Any = None

    def to_dict(self) -> dict[str, Any]:
        return {"field": self.field, "operator": self.operator, "value": self.value}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SegmentRule":
        return cls(field=d["field"], operator=d["operator"], value=d.get("value"))


@dataclass
class Segment:
    segment_id: str
    name: str
    rules: list[SegmentRule] = field(default_factory=list)
    combinator: str = "AND"  # AND | OR
    purpose: Purpose = Purpose.ANALYTICS
    created_at: float = field(default_factory=_now)

    def __post_init__(self) -> None:
        if isinstance(self.purpose, str):
            self.purpose = Purpose(self.purpose)

    def to_dict(self) -> dict[str, Any]:
        return {"segment_id": self.segment_id, "name": self.name,
                "rules": [r.to_dict() for r in self.rules],
                "combinator": self.combinator, "purpose": self.purpose.value,
                "created_at": self.created_at}


@dataclass
class ActivationResult:
    activation_id: str
    segment_id: str
    sink: str
    profile_count: int
    delivered: int
    skipped_no_consent: int = 0
    payload_preview: list[dict[str, Any]] = field(default_factory=list)
    created_at: float = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return {"activation_id": self.activation_id, "segment_id": self.segment_id,
                "sink": self.sink, "profile_count": self.profile_count,
                "delivered": self.delivered, "skipped_no_consent": self.skipped_no_consent,
                "payload_preview": list(self.payload_preview), "created_at": self.created_at}


@dataclass
class QualityCheckResult:
    check_name: str
    passed: bool
    detail: str
    metric: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"check_name": self.check_name, "passed": self.passed,
                "detail": self.detail, "metric": self.metric}
