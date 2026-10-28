from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

from reels_api.config import database_url
from reels_api.models import Base

config = context.config
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)

# Tests pass the test database URL explicitly; everything else uses DATABASE_URL.
url = config.get_main_option("sqlalchemy.url") or database_url()

with create_engine(url).connect() as connection:
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()
