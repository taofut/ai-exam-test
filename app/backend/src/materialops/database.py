from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import NullPool, StaticPool

from materialops.config import BACKEND_ROOT


class Base(DeclarativeBase):
    pass


class Database:
    def __init__(self, url: str):
        self.url = url
        kwargs = {}
        if url.startswith("sqlite:"):
            filename = make_url(url).database
            if filename and filename != ":memory:" and not filename.startswith("file:"):
                Path(filename).parent.mkdir(parents=True, exist_ok=True)
            kwargs["connect_args"] = {"check_same_thread": False, "timeout": 15}
            kwargs["poolclass"] = StaticPool if url.endswith(":memory:") else NullPool
        self.engine = create_engine(url, **kwargs)
        if url.startswith("sqlite:"):
            @event.listens_for(self.engine, "connect")
            def configure_sqlite(connection, _):
                connection.execute("PRAGMA foreign_keys=ON")
        self.sessions = sessionmaker(bind=self.engine, expire_on_commit=False)

    def migrate(self):
        config = Config(str(BACKEND_ROOT / "alembic.ini"))
        config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
        config.set_main_option("sqlalchemy.url", self.url.replace("%", "%%"))
        with self.engine.connect() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        # The timed baseline supplies the issue schema. Backfill legacy fixture
        # history once, without reapplying inventory deltas or resetting data.
        from materialops.seed import backfill_fixture_history
        with self.engine.begin() as connection:
            if connection.dialect.name == "sqlite":
                connection.exec_driver_sql("BEGIN IMMEDIATE")
            backfill_fixture_history(connection)


def get_session(request):
    with request.app.state.database.sessions() as session:
        yield session

