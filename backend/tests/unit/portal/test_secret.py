"""Secret hides its value from repr/str but reveals it on request."""

from app.portal.secret import Secret


def test_reveal_and_masking() -> None:
    s = Secret("hunter2")
    assert s.reveal() == "hunter2"
    assert repr(s) == str(s) == "Secret('***')"
    assert "hunter2" not in f"{s!r} {s} {s!s}"


def test_equality_and_hash() -> None:
    assert Secret("a") == Secret("a")
    assert Secret("a") != Secret("b")
    assert Secret("a") != "a"
    assert len({Secret("a"), Secret("a")}) == 1
