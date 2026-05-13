"""DKM Origin — preferentiële oorsprong validator en lookup."""

from .validator import (
    OriginValidator,
    ValidationResult,
    Severity,
    TARIC_CODE_TO_PROOF,
)

__all__ = [
    "OriginValidator",
    "ValidationResult",
    "Severity",
    "TARIC_CODE_TO_PROOF",
]
__version__ = "0.1.0"
