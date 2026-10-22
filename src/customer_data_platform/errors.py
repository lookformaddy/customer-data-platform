"""Typed errors for the customer data platform."""
from __future__ import annotations


class CDPError(Exception):
    """Base class for all CDP errors."""


class ValidationError(CDPError):
    """Input failed validation."""


class UnknownProfileError(CDPError):
    """Referenced profile does not exist."""


class UnknownSegmentError(CDPError):
    """Referenced segment does not exist."""


class ConsentDeniedError(CDPError):
    """Access denied by consent / purpose policy."""


class IdentityError(CDPError):
    """Identity resolution operation failed."""


class MergeError(IdentityError):
    """Merge operation failed."""


class SplitError(IdentityError):
    """Split operation failed."""


class IngestionError(CDPError):
    """Ingestion failed."""


class ActivationError(CDPError):
    """Activation to a sink failed."""


class QualityError(CDPError):
    """Data quality check configuration is invalid."""
