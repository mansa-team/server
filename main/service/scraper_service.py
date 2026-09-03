import logging
from config import Config

import time
from apscheduler.triggers.cron import CronTrigger

from main.app.scraper_b3.scraper import B3Scraper

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
    """P5: register the scraper cron jobs on the shared scheduler.

    Kept in this service file so per-service management grouping is
    preserved — only the scheduler *instance* is shared. Same cron times
    and stable job ids as before; jitter staggers firings off the other
    services' jobs. Returns the registered job ids.
    """
    from main.utils.scheduler import SCRAPER_JITTER_SECONDS, registerJob

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
                CronTrigger(hour=hour, minute=minute, jitter=SCRAPER_JITTER_SECONDS),
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
