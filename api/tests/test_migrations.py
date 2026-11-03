from alembic.config import Config
from alembic.script import ScriptDirectory
from conftest import API_DIR


def test_migrations_form_one_line():
    """Two branches that each add the next number must not both land: `alembic upgrade head` then fails."""
    script = ScriptDirectory.from_config(Config(str(API_DIR / "alembic.ini")))
    files = sorted(path.name for path in (API_DIR / "migrations" / "versions").glob("*.py"))
    revisions = [revision.revision for revision in script.walk_revisions()]

    assert len(revisions) == len(files), "two migrations share a revision id"
    assert script.get_heads() == [revisions[0]]
