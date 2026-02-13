from imports import *

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

def runScraper():
    projectRoot = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    scraperPath = os.path.join(projectRoot, "main", "app", "scraper_b3", "scraper.py")
    
    env = os.environ.copy()
    env["PYTHONPATH"] = projectRoot

    if not os.path.exists(scraperPath):
        print(f"Error: Scraper file not found at {scraperPath}")
        return

    subprocess.run([sys.executable, scraperPath], env=env, check=True)
    
class ScraperService:
    @staticmethod
    def initialize():
        schedules = Config.SCRAPER['SCHEDULER'].split(';')
        scheduler = BackgroundScheduler()

        if not schedules:
            if Config.DEBUG_MODE == "TRUE":
                print("No schedules configured in SCRAPER_SCHEDULER")
            return
        
        for idx, schedule in enumerate(schedules):
            try:
                hour, minute = map(int, schedule.strip().split(':'))
                scheduler.add_job(
                    runScraper,
                    CronTrigger(hour=hour, minute=minute),
                    id=f'scraper_{idx}',
                    name=f'Scraper ({schedule})'
                )

                if Config.DEBUG_MODE == "TRUE":
                    print(f"Scheduled Hours: {schedule}")
            except ValueError:
                if Config.DEBUG_MODE == "TRUE":
                    print(f"Invalid format: {schedule} (use HH:MM)")
        
        scheduler.start()