import logging
import os

from alembic import command
from alembic.config import Config

logger = logging.getLogger(__name__)


def runMigrations():
    try:
        rootPath = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

        if os.path.exists(os.path.join(rootPath, "alembic.ini")):
            migrationRoot = rootPath
        elif os.path.exists("alembic.ini"):
            migrationRoot = os.getcwd()
        else:
            logger.error(f"alembic.ini not found in {os.getcwd()} or {rootPath}")
            return

        config = Config()
        config.set_main_option("script_location", os.path.join(migrationRoot, "migrations"))
        command.upgrade(config, "head")
        logger.info("Successfully updated database to the latest version.")

    except Exception as e:
        logger.error(f"Failed to execute migrations: {e}")
