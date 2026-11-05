from sqlalchemy.engine import make_url

from materialops.config import EXAM_ROOT, Settings


def test_local_exam_starts_without_environment_file(monkeypatch):
    monkeypatch.delenv("ALLOW_EXAM_RESET", raising=False)
    configuration = Settings(_env_file=None)
    assert configuration.allow_exam_reset is True


def test_explicit_development_gate_remains_available(monkeypatch):
    monkeypatch.setenv("ALLOW_EXAM_RESET", "false")
    assert Settings(_env_file=None).allow_exam_reset is False


def test_default_database_is_shared_regardless_of_working_directory(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.chdir(tmp_path)
    configuration = Settings(_env_file=None)
    assert make_url(configuration.database_url).database == (EXAM_ROOT / "runtime/data/materialops.db").as_posix()


def test_explicit_database_url_still_wins(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///chosen.db")
    assert Settings(_env_file=None).database_url == "sqlite:///chosen.db"
