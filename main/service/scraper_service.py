from config import Config
from main.utils.util import log

import time
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from pytz import timezone
  
from main.app.scraper_b3.scraper import B3Scraper

_scraper_start_time = None

def runScraper():
    global _scraper_start_time
    _scraper_start_time = time.time()
    try:
        scraper = B3Scraper()
        scraper.scrapeStocks()
        elapsed = time.time() - _scraper_start_time if _scraper_start_time else 0
        log("scraper", f"Scraper execution completed. Time: {elapsed:.0f}s")
    except Exception as e:
        log("scraper", f"Scraper Exception: {e}")
    
class ScraperService:
    @staticmethod
    def initialize():
        schedules = Config.SCRAPER['SCHEDULER'].split(';')
        scheduler = BackgroundScheduler(timezone=timezone('America/Sao_Paulo'))

        if not schedules:
            log("scraper", "No schedules configured in SCRAPER_SCHEDULER")
            return
        
        for idx, schedule in enumerate(schedules):
            try:
                hour, minute = map(int, schedule.strip().split(':'))
                scheduler.add_job(
                    runScraper,
                    CronTrigger(hour=hour, minute=minute, timezone=timezone('America/Sao_Paulo')),
                    id=f'scraper_{idx}',
                    name=f'Scraper ({schedule})'
                )

                log("scraper", f"Scheduled Hours: {schedule}")
            except ValueError:
                log("scraper", f"Invalid format: {schedule} (use HH:MM)")
        
        scheduler.start()