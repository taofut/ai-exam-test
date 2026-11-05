from logging.config import fileConfig

from alembic import context

from materialops import models  # noqa: F401
from materialops.config import settings
from materialops.database import Base, Database

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)
target_metadata = Base.metadata


def run(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    context.configure(url=settings.database_url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
elif config.attributes.get("connection") is not None:
    run(config.attributes["connection"])
else:
    database = Database(settings.database_url)
    try:
        with database.engine.connect() as connection:
            run(connection)
    finally:
        database.engine.dispose()

