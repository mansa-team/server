from imports import *
from main.utils.util import log

import subprocess
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
 
from main.app.scraper_b3.scraper import b3_scraper

def runScraper():
    try:
        b3_scraper.scrapeData()
        log("scraper", f"Scraper execution completed. Time: {time.time() - b3_scraper.start_time:.0f}s")
    except Exception as e:
        log("scraper", f"Scraper Exception: {e}")
    
class ScraperService:
    @staticmethod
    def initialize():
        schedules = Config.SCRAPER['SCHEDULER'].split(';')
        scheduler = BackgroundScheduler()

        if not schedules:
            log("scraper", "No schedules configured in SCRAPER_SCHEDULER")
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

                log("scraper", f"Scheduled Hours: {schedule}")
            except ValueError:
                log("scraper", f"Invalid format: {schedule} (use HH:MM)")
        
        scheduler.start()