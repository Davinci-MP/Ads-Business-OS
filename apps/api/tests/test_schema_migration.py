from pathlib import Path

from sqlalchemy import create_engine, inspect

import alembic.command
import alembic.config

from app.models import Base


def test_migration_creates_all_tables(engine):
    inspector = inspect(engine)
    reflected = set(inspector.get_table_names())
    expected = set(Base.metadata.tables.keys())
    missing = expected - reflected
    assert not missing, f"Missing tables: {sorted(missing)}"


def test_migration_is_reversible(tmp_path):
    api_dir = Path(__file__).resolve().parents[1]
    url = f"sqlite:///{tmp_path / 'revers.db'}"
    alembic_cfg = alembic.config.Config(str(api_dir / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(api_dir / "alembic"))
    alembic_cfg.set_main_option("sqlalchemy.url", url)
    alembic.command.upgrade(alembic_cfg, "head")
    engine = create_engine(url, future=True)
    tables = set(inspect(engine).get_table_names())
    assert set(Base.metadata.tables.keys()) <= tables
    alembic.command.downgrade(alembic_cfg, "base")
    tables_after = set(inspect(engine).get_table_names())
    assert not (set(Base.metadata.tables.keys()) & tables_after)
    engine.dispose()
