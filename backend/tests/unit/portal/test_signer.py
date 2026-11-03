"""HmacSha256Signer test vectors."""

import hashlib
import hmac

from app.portal.signer import HmacSha256Signer


def test_matches_hmac_computed_directly() -> None:
    headers = HmacSha256Signer().sign(
        "GET", "/portal/export", "page=1", "test-signing-secret", 1793697409
    )
    message = "GET\n/portal/export\npage=1\n1793697409"
    expected = hmac.new(b"test-signing-secret", message.encode(), hashlib.sha256).hexdigest()
    assert headers == {"x-timestamp": "1793697409", "x-signature": expected}


def test_pinned_vector_catches_message_format_changes() -> None:
    headers = HmacSha256Signer().sign("GET", "/portal/export", "page=1", "another-secret", 1000)
    assert headers == {
        "x-timestamp": "1000",
        "x-signature": "4022a9cb3f3e1f8121eb95fb02ff1a34aec6eaf4db4a72fd313606992b0767a8",
    }
