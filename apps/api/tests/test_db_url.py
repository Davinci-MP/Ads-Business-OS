import pytest

from app.core.db_url import normalize_database_url


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("postgresql://u:p@h:5432/d", "postgresql+psycopg://u:p@h:5432/d"),
        ("postgres://u:p@h/d", "postgresql+psycopg://u:p@h/d"),
        ("postgresql+psycopg://u:p@h/d", "postgresql+psycopg://u:p@h/d"),
        ('  "postgresql://u:p@h/d"\n', "postgresql+psycopg://u:p@h/d"),
        ("sqlite:///./adsos.db", "sqlite:///./adsos.db"),
    ],
)
def test_normalize_database_url(raw, expected):
    assert normalize_database_url(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", None, '""', "${{Postgres.DATABASE_URL}}"])
def test_normalize_database_url_rejects_unusable_values(raw):
    with pytest.raises(RuntimeError) as exc:
        normalize_database_url(raw)
    assert "ADSOS_DATABASE_URL" in str(exc.value)
