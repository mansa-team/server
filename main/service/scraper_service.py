import logging
from config import Config

import time
from apscheduler.triggers.cron import CronTrigger

from main.app.scraper_b3.scraper import B3Scraper
from main.utils.scheduler import registerJob

logger = logging.getLogger(__name__)


def runScraper():
    start = time.time()
    try:
        scraper = B3Scraper()
        scraper.scrapeStocks()
        logger.info(f"Scraper execution completed. Time: {time.time() - start:.0f}s")
    except Exception as e:
        logger.error(f"Scraper Exception: {e}")


def registerScraperJobs() -> list:
    schedules = Config.SCRAPER.SCHEDULER.split(";")

    if not schedules:
        logger.warning("No schedules configured in SCRAPER_SCHEDULER")
        return []

    registered = []
    for idx, schedule in enumerate(schedules):
        try:
            hour, minute = map(int, schedule.strip().split(":"))
            registerJob(
                runScraper,
                CronTrigger(hour=hour, minute=minute),
                jobId=f"scraper_{idx}",
                jobName=f"Scraper ({schedule})",
            )
            registered.append(f"scraper_{idx}")

            logger.info(f"Scheduled Hours: {schedule}")
        except ValueError:
            logger.warning(f"Invalid format: {schedule} (use HH:MM)")

    return registered


class ScraperService:
    @staticmethod
    def initialize():
        registerScraperJobs()
