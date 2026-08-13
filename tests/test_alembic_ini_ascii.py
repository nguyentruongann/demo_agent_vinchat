"""alembic.ini phải thuần ASCII.

Alembic đọc file này bằng encoding locale của hệ điều hành (cp1252 trên Windows),
không phải UTF-8. Một chú thích tiếng Việt có dấu là đủ làm mọi lệnh alembic chết
với UnicodeDecodeError — đã dính một lần khi dựng migration đầu tiên.

alembic/env.py là file Python nên luôn đọc bằng UTF-8, viết tiếng Việt thoải mái.
"""

from pathlib import Path

INI = Path(__file__).resolve().parents[1] / "alembic.ini"


def test_alembic_ini_is_pure_ascii() -> None:
    raw = INI.read_bytes()
    non_ascii = [
        (i, byte) for i, byte in enumerate(raw) if byte > 0x7F
    ]
    assert not non_ascii, (
        f"alembic.ini có {len(non_ascii)} byte ngoài ASCII "
        f"(byte đầu ở vị trí {non_ascii[0][0]}). "
        "Alembic đọc file này bằng encoding locale nên sẽ hỏng — "
        "viết chú thích bằng tiếng Anh."
    )
