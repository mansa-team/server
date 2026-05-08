import logging
import subprocess
import os
import sys

logger = logging.getLogger(__name__)

def runMigrations():
    try:
        rootPath = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        
        if os.path.exists(os.path.join(rootPath, "alembic.ini")):
            os.chdir(rootPath)
        elif not os.path.exists("alembic.ini"):
            logger.error(f"alembic.ini not found in {os.getcwd()} or {rootPath}")
            return

        result = subprocess.run(
            ["alembic", "upgrade", "head"],
            capture_output=True,
            text=True,
            env=os.environ.copy()
        )
        
        if result.returncode == 0:
            logger.info("Successfully updated database to the latest version.")
            if result.stdout:
                logger.info(result.stdout.strip())
        else:
            logger.error("Error during migration:")
            logger.error(result.stdout)
            logger.error(result.stderr)
            
    except Exception as e:
        logger.error(f"Failed to execute migrations: {e}")

if __name__ == "__main__":
    runMigrations()