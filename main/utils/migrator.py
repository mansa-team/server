import subprocess
import os
import sys

from util import log

def runMigrations():
    try:
        rootPath = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        
        if os.path.exists(os.path.join(rootPath, "alembic.ini")):
            os.chdir(rootPath)
        elif not os.path.exists("alembic.ini"):
            log("alembic", f"Error: alembic.ini not found in {os.getcwd()} or {rootPath}")
            return

        result = subprocess.run(
            ["alembic", "upgrade", "head"],
            capture_output=True,
            text=True,
            env=os.environ.copy()
        )
        
        if result.returncode == 0:
            log("alembic", "Successfully updated database to the latest version.")
            if result.stdout:
                print(result.stdout.strip())
        else:
            log("alembic", "Error during migration:")
            print(result.stdout)
            print(result.stderr)
            
    except Exception as e:
        log("alembic", "Failed to execute migrations: {e}")

if __name__ == "__main__":
    runMigrations()