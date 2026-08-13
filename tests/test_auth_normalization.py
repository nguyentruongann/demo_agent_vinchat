from src.backend.services.auth import normalize_email, normalize_phone


def test_normalize_email_case_and_whitespace() -> None:
    assert normalize_email("  Test01@GMAIL.com  ") == "test01@gmail.com"


def test_normalize_phone_vietnam_formats() -> None:
    assert normalize_phone("0901 234 567") == "0901234567"
    assert normalize_phone("+84 901 234 567") == "0901234567"
    assert normalize_phone("0901.234.567") == "0901234567"
