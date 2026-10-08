"""Evidence-linked assessment with an offline, explicit-policy default."""

from .verifier import (
    Evidence,
    OpenAICompatibleAdapter,
    QuoteResult,
    VerificationPolicy,
    VerificationRequest,
    VerificationResult,
    Verifier,
    check_quote,
)

__all__ = [
    "Evidence", "OpenAICompatibleAdapter", "QuoteResult", "VerificationPolicy",
    "VerificationRequest", "VerificationResult", "Verifier", "check_quote",
]
