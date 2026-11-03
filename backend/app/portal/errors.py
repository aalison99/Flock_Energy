"""Portal-internal signals that the session layer catches; they are never domain errors."""


class SessionExpired(Exception):
    """The portal says our session is missing or expired; log in again and replay."""


class SignatureRejected(Exception):
    """The portal rejected the HMAC signature of a signed request."""
