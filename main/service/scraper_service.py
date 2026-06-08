import logging
import time
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from pytz import timezone

from config import Config
from main.app.scraper_b3.scraper import B3Scraper

logger = logging.getLogger(__name__)

scraperStartTime = None


def runScraper():
    global scraperStartTime
    scraperStartTime = time.time()
    try:
        scraper = B3Scraper()
        scraper.scrapeStocks()
        elapsed = time.time() - scraperStartTime if scraperStartTime else 0
        logger.info(f"Scraper execution completed. Time: {elapsed:.0f}s")
    except Exception as e:
        logger.error(f"Scraper Exception: {e}")


class ScraperService:
    @staticmethod
    def initialize():
        schedules = Config.SCRAPER["SCHEDULER"].split(";")
        scheduler = BackgroundScheduler(timezone=timezone("America/Sao_Paulo"))

        if not schedules:
            logger.warning("No schedules configured in SCRAPER_SCHEDULER")
            return

        for idx, schedule in enumerate(schedules):
            try:
                hour, minute = map(int, schedule.strip().split(":"))
                scheduler.add_job(
                    runScraper,
                    CronTrigger(hour=hour, minute=minute, timezone=timezone("America/Sao_Paulo")),
                    id=f"scraper_{idx}",
                    name=f"Scraper ({schedule})",
                )

                logger.info(f"Scheduled Hours: {schedule}")
            except ValueError:
                logger.warning(f"Invalid format: {schedule} (use HH:MM)")

        scheduler.start()
