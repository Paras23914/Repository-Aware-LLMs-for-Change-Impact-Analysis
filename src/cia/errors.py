"""Domain-specific errors with messages suitable for CLI reporting."""


class CIAError(Exception):
    """Base exception for expected analysis and input errors."""


class ManifestError(CIAError):
    """Raised when a manifest row is malformed or inconsistent."""


class RepositoryError(CIAError):
    """Raised when a requested Git repository object cannot be read."""


class PredictionError(CIAError):
    """Raised when ranked predictions are invalid for the repository view."""

