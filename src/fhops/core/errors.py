"""Common FHOPS-specific exceptions."""

class FHOPSValueError(ValueError):
    """Raised when FHOPS detects invalid user-provided data."""


__all__ = ["FHOPSValueError"]
