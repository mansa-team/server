import logging

from apscheduler.schedulers.background import BackgroundScheduler

logger = logging.getLogger(__name__)

sharedScheduler: BackgroundScheduler | None = None

STOCKS_REFRESH_JITTER_SECONDS = 600
SESSION_CLEANUP_JITTER_SECONDS = 300
MEMORY_MAINTENANCE_JITTER_SECONDS = 600
SCRAPER_JITTER_SECONDS = 120


def getSharedScheduler() -> BackgroundScheduler:
    global sharedScheduler
    if sharedScheduler is None:
        sharedScheduler = BackgroundScheduler()
        sharedScheduler.start()
        logger.info("Shared background scheduler started")
    return sharedScheduler


def registerJob(func, trigger, *, jobId: str, jobName: str | None = None, **triggerKwargs):
    scheduler = getSharedScheduler()
    job = scheduler.add_job(
        func,
        trigger,
        id=jobId,
        name=jobName or jobId,
        replace_existing=True,
        **triggerKwargs,
    )
    logger.info(f"Registered background job '{jobId}' on shared scheduler")
    return job
