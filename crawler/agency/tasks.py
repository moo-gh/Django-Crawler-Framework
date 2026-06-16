from __future__ import absolute_import, unicode_literals
import re
import json
import asyncio
import time
import redis
import socket
import telegram
import importlib
import traceback
from dataclasses import dataclass
from typing import Literal, Optional
from datetime import timedelta
from telegram.error import NetworkError, RetryAfter, TelegramError, TimedOut
from telegram.request import HTTPXRequest

from django.conf import settings
from django.utils import timezone
from celery.utils.log import get_task_logger

from . import utils, models
from crawler.celery import crawler
from notification import utils as not_utils
from notification import models as not_models
from ai import models as ai_models
from reusable.other import REDIS_CLIENT, only_one_concurrency


MINUTE = 60
# caveat: at most the redis-exporter task should take 30 minutes
# otherwise, we would have duplication of messages
TASKS_TIMEOUT = 30 * MINUTE

# Telegram rate limiting configuration
TELEGRAM_MAX_RETRIES = 3
TELEGRAM_MIN_INTERVAL = 0.5  # Minimum seconds between any Telegram API call
TELEGRAM_RETRY_BUFFER = 2  # Extra seconds to add to Telegram's retry_after
TELEGRAM_LAST_SEND_KEY = "telegram:last_send_at"
TELEGRAM_RATE_LIMIT_LOCK_KEY = "telegram:rate_limit_lock"
TELEGRAM_DEFER_SECONDS = 600  # 10 minutes before redis_exporter retries a failed send
TELEGRAM_MAX_DEFER_ATTEMPTS = 6  # ~1 hour of deferred retries before giving up
TELEGRAM_HTTP_TIMEOUT = 30.0
TELEGRAM_MESSAGE_PREVIEW_LENGTH = 150

TELEGRAM_HTTP_REQUEST = HTTPXRequest(
    connect_timeout=TELEGRAM_HTTP_TIMEOUT,
    read_timeout=TELEGRAM_HTTP_TIMEOUT,
    write_timeout=TELEGRAM_HTTP_TIMEOUT,
    pool_timeout=TELEGRAM_HTTP_TIMEOUT,
)

logger = get_task_logger(__name__)
redis_news = redis.StrictRedis(host="crawler-redis", port=6379, db=0)


@crawler.task(name="remove_old_reports")
def remove_old_reports():
    """
    Deletes report records that are older than 7 days.
    """
    before_time = timezone.localtime() - timezone.timedelta(days=7)
    models.Report.objects.filter(created_at__lte=before_time).delete()[0]


@crawler.task(name="remove_old_logs")
def remove_old_logs():
    """
    Deletes log entries and DB log entries that are older than 7 days.
    """
    before_time = timezone.localtime() - timezone.timedelta(days=7)
    models.Log.objects.filter(created_at__lte=before_time).delete()
    models.DBLogEntry.objects.filter(time__lte=before_time).delete()


@crawler.task(name="reset_page_locks")
def reset_page_locks():
    """
    Resets the lock status of all Page objects to False.
    Useful for recovering from tasks that might have crashed while holding a lock.
    """
    models.Page.objects.update(lock=False)


@crawler.task(name="send_log_to_telegram")
def send_log_to_telegram(message):
    """
    Sends a log message to a Telegram account using a configured bot.

    Args:
        message (str): The log message to be sent.
    """
    bot_model = not_models.TelegramBot.objects.first()
    account = not_models.TelegramAccount.objects.first()
    if not (bot_model and account):
        return

    # Use the same rate limiting approach for log messages
    result = send_telegram_message_with_retry(
        bot_model.telegram_token, account.chat_id, message
    )
    if not result.success:
        logger.error(
            "Failed to send log message to Telegram after retries: %s",
            result.error,
        )


def check_must_crawl(page: models.Page):
    now = timezone.localtime()
    reports = models.Report.objects.filter(page=page.id, status=models.Report.PENDING)
    if reports.count() == 0:
        crawl(page)
    else:
        last_report = reports.last()
        diff_in_secs = (now - last_report.created_at).total_seconds()
        diff_in_min = int(diff_in_secs / (60))
        if diff_in_min >= page.crawl_interval:
            if last_report.status == models.Report.PENDING:
                last_report.status = models.Report.FAILED
            crawl(page)


@crawler.task(name="check_agencies")
def check_agencies():
    if settings.DEBUG:
        logger.info("check_agencies is disabled in debug mode")
        return

    logger.info("check_agencies started")
    now = timezone.localtime()
    task_interval_minutes = 5  # Adjust based on your Celery schedule
    time_window_start = now - timezone.timedelta(minutes=task_interval_minutes)

    # Get current day abbreviation (e.g., "MON")
    current_day = now.strftime("%a").upper()
    # Generate a range of times to check
    current_time_range = [
        (time_window_start + timezone.timedelta(minutes=i)).strftime("%H:%M")
        for i in range(task_interval_minutes)
    ]

    schedules = models.CrawlScheduling.objects.filter(
        page__status=True,
        page__agency__status=True,
    ).select_related("page")

    for schedule in schedules:
        days = schedule.get_days()  # Split days into a list
        times = schedule.get_start_times()  # Split times into a list

        if current_day in days and any(time in current_time_range for time in times):
            logger.debug("Crawling page %s because of schedule", schedule.page.url)
            crawl(schedule.page)

    # Filter pages based on the matched page IDs
    agencies = models.Agency.objects.filter(status=True).values_list("id", flat=True)
    pages = (
        models.Page.objects.filter(agency__in=agencies)
        .filter(lock=False)
        .filter(status=True)
    )

    for page in pages:
        logger.debug(
            "Checking page %s, is_off_time: %s, last_crawl: %s, crawl_interval: %s",
            page.url,
            page.is_off_time,
            page.last_crawl,
            page.crawl_interval,
        )
        if page.is_off_time:
            continue
        if page.last_crawl is None:
            check_must_crawl(page)
        else:
            diff_minute = int((now - page.last_crawl).total_seconds() / 60)
            if diff_minute >= page.crawl_interval:
                check_must_crawl(page)


def register_log(
    description: str,
    error: str,
    page: models.Page,
    url: str,
    log_level: str = "error",
    include_traceback: bool = False,
):
    detail = traceback.format_exc() if include_traceback else error
    if log_level == "error":
        logger.error("desc: %s\ndetail: %s", description, detail)
    elif log_level == "info":
        logger.info("desc: %s\ndetail: %s", description, detail)
    elif log_level == "debug":
        logger.debug("desc: %s\ndetail: %s", description, detail)
    else:
        logger.warning("desc: %s\ndetail: %s", description, detail)

    models.Log.objects.create(
        page=page,
        description=description,
        url=url,
        phase=models.Log.SENDING,
        error=error,
        level=log_level,
    )


def crawl(page: models.Page):
    serializer = importlib.import_module("agency.serializer")
    page_crawl.delay(serializer.PageSerializer(page).data)


@crawler.task(name="page_crawl")
@only_one_concurrency(key="page_crawl", timeout=TASKS_TIMEOUT)
def page_crawl(page):
    crawler_module = importlib.import_module("agency.crawler_engine")
    crawler_engine = crawler_module.CrawlerEngine
    crawler_engine(page)


@crawler.task(name="page_crawl_repetitive")
@only_one_concurrency(key="page_crawl_repetitive", timeout=TASKS_TIMEOUT)
def page_crawl_repetitive(page):
    crawler_module = importlib.import_module("agency.crawler_engine")
    crawler_engine = crawler_module.CrawlerEngine
    crawler_engine(page, repetitive=True)


def find_page(pages, data, key):
    page = pages.filter(pk=data["page_id"], status=True).first()
    if page:
        return page

    desc = f"data is: {data}"
    error = "page is None or is not active"
    register_log(desc, error, page, data["link"])
    redis_news.delete(key)
    return False


# Don't remove this, it's used dynamically in
# the page code section
# get info from data (gin)
def gin(key: str, data: dict):
    """Get info from data with improved error handling and default values."""
    if key not in data:
        return "Unknown " + key
    value = data[key]
    if value is None or value == "":
        return "Unknown " + key
    # remove extra spaces and new lines
    return str(value).strip().replace("\n", "")


# Don't remove this, it's used dynamically in
# the page code section
# can be used for removing extra new lines
def limit_newlines(text: str) -> str:
    # Replace any sequence of more than two '\n' with exactly two '\n'
    return re.sub(r"\n{3,}", "\n\n", text)


def clear_all_redis_locks():
    REDIS_CLIENT = redis.Redis(host="crawler-redis", port=6379, db=5)
    REDIS_CLIENT.delete("redis_exporter")
    REDIS_CLIENT.delete("page_crawl")
    REDIS_CLIENT.delete("page_crawl_repetitive")


def checking_ignore_tags(
    page: models.Page, message: str, ig_tokens: Optional[list[str]]
) -> bool:
    for token in ig_tokens:
        if token in message:
            message = f"message contains {token}"
            register_log(message, "ignored content", page, "", "debug")
            return True
    return False


def get_page_ignoring_tokens(page: models.Page) -> list["str"]:
    tags_with_tokens = page.filtering_tags.prefetch_related("filteringtoken_set")
    return list(
        {
            token.token
            for tag in tags_with_tokens
            for token in tag.filteringtoken_set.all()
        }
    )


@dataclass
class TelegramSendResult:
    success: bool
    failure_kind: Optional[Literal["transient", "permanent"]] = None
    error: Optional[str] = None


def _message_preview(message: str, max_length: int = TELEGRAM_MESSAGE_PREVIEW_LENGTH) -> str:
    preview = message.strip().replace("\n", " ")
    if len(preview) <= max_length:
        return preview
    return preview[: max_length - 3] + "..."


def _telegram_retry_pending(data: dict) -> bool:
    retry_after = data.get("telegram_retry_after")
    if retry_after is None:
        return False
    return time.time() < float(retry_after)


def _schedule_telegram_retry(key, data: dict) -> bool:
    attempt = data.get("telegram_retry_count", 0) + 1
    if attempt >= TELEGRAM_MAX_DEFER_ATTEMPTS:
        return False

    data["telegram_retry_count"] = attempt
    data["telegram_retry_after"] = time.time() + TELEGRAM_DEFER_SECONDS
    redis_news.set(key, json.dumps(data))
    return True


def _classify_telegram_error(exc: Exception) -> Literal["transient", "permanent"]:
    if isinstance(exc, (TimedOut, NetworkError, RetryAfter)):
        return "transient"
    if isinstance(exc, TelegramError):
        return "permanent"
    return "transient"


async def _send_telegram_message(token: str, chat_id: str, message: str):
    async with telegram.Bot(token=token, request=TELEGRAM_HTTP_REQUEST) as bot:
        await bot.send_message(chat_id=chat_id, text=message)


def _wait_for_telegram_rate_limit():
    """Enforce a minimum interval between Telegram sends across all workers."""
    lock = REDIS_CLIENT.lock(
        TELEGRAM_RATE_LIMIT_LOCK_KEY, timeout=30, blocking_timeout=120
    )
    if not lock.acquire(blocking=True):
        logger.warning("Could not acquire Telegram rate limit lock, proceeding anyway")
        return

    try:
        last_raw = REDIS_CLIENT.get(TELEGRAM_LAST_SEND_KEY)
        if last_raw is not None:
            wait = TELEGRAM_MIN_INTERVAL - (time.time() - float(last_raw))
            if wait > 0:
                time.sleep(wait)
        REDIS_CLIENT.set(TELEGRAM_LAST_SEND_KEY, time.time())
    finally:
        try:
            lock.release()
        except redis.exceptions.LockError:
            logger.warning("Failed to release Telegram rate limit lock")


def send_telegram_message_with_retry(
    bot_token: str,
    chat_id: str,
    message: str,
    max_retries: int = TELEGRAM_MAX_RETRIES,
    formatter: Optional[ai_models.Formatter] = None,
) -> TelegramSendResult:
    """
    Send a Telegram message with proper rate limiting and retry logic.

    Args:
        bot_token: Telegram bot token
        chat_id: Telegram chat/channel ID
        message: Message text to send
        max_retries: Maximum number of retry attempts
        formatter: Formatter instance

    Returns:
        TelegramSendResult with success flag, failure kind, and error detail
    """
    if formatter:
        message = formatter.format(message)
    for attempt in range(max_retries + 1):
        try:
            _wait_for_telegram_rate_limit()
            asyncio.run(_send_telegram_message(bot_token, chat_id, message))
            logger.debug(
                f"Message sent successfully to {chat_id} on attempt {attempt + 1}"
            )
            return TelegramSendResult(success=True)

        except RetryAfter as e:
            retry_after = e.retry_after
            logger.warning(
                f"Rate limit hit. Telegram requires retry after {retry_after} seconds. Attempt {attempt + 1}/{max_retries + 1}"
            )

            if attempt < max_retries:
                sleep_time = retry_after + TELEGRAM_RETRY_BUFFER
                logger.info(f"Waiting {sleep_time} seconds before retry...")
                time.sleep(sleep_time)
            else:
                error = f"rate limiting after {max_retries + 1} attempts: {e}"
                logger.error("Failed to send message after retries due to %s", error)
                return TelegramSendResult(
                    success=False,
                    failure_kind="transient",
                    error=error,
                )

        except (TimedOut, NetworkError) as e:
            if attempt < max_retries:
                sleep_time = (2**attempt) + 1
                logger.warning(
                    f"Telegram network error on attempt {attempt + 1}: {e}, retrying in {sleep_time} seconds..."
                )
                time.sleep(sleep_time)
            else:
                error = f"{type(e).__name__}: {e}"
                logger.error(
                    "Failed to send message after %s attempts due to Telegram error: %s",
                    max_retries + 1,
                    error,
                )
                return TelegramSendResult(
                    success=False,
                    failure_kind="transient",
                    error=error,
                )

        except TelegramError as e:
            failure_kind = _classify_telegram_error(e)
            if attempt < max_retries and failure_kind == "transient":
                sleep_time = (2**attempt) + 1
                logger.warning(
                    f"Telegram error on attempt {attempt + 1}: {e}, retrying in {sleep_time} seconds..."
                )
                time.sleep(sleep_time)
            else:
                error = f"{type(e).__name__}: {e}"
                logger.error(
                    "Failed to send message after %s attempts due to Telegram error: %s",
                    max_retries + 1,
                    error,
                )
                return TelegramSendResult(
                    success=False,
                    failure_kind=failure_kind,
                    error=error,
                )

        except Exception as e:
            error = f"{type(e).__name__}: {e}"
            logger.error("Unexpected error sending Telegram message: %s", error)
            return TelegramSendResult(
                success=False,
                failure_kind="transient",
                error=error,
            )

    return TelegramSendResult(
        success=False,
        failure_kind="transient",
        error="unknown telegram send failure",
    )


@crawler.task(name="cleanup_stale_redis_links")
def cleanup_stale_redis_links():
    """
    Hourly sweep of links_* keys for pages that no longer exist or are inactive.
    """
    if settings.DEBUG:
        logger.info("cleanup_stale_redis_links is disabled in debug mode")
        return 0

    pages = models.Page.objects.all()
    removed = 0
    for key in redis_news.scan_iter("links_*"):
        raw = redis_news.get(key)
        if raw is None:
            continue
        try:
            data = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            redis_news.delete(key)
            removed += 1
            continue

        page_id = data.get("page_id")
        if page_id is None or not pages.filter(pk=page_id, status=True).exists():
            redis_news.delete(key)
            removed += 1

    logger.info("cleanup_stale_redis_links finished: %s redis keys deleted", removed)
    return removed


@crawler.task(name="redis_exporter")
@only_one_concurrency(key="redis_exporter", timeout=TASKS_TIMEOUT)
def redis_exporter():
    """
    It will be used to extract news in the redis,
    and send them to the telegram bot.
    """
    logger.info("redis-exporter started with container id: %s", socket.gethostname())

    if settings.DEBUG:
        logger.info("redis-exporter is disabled in debug mode")
        return

    ignoring_tokens = {}

    pages = models.Page.objects.all()
    for key in redis_news.scan_iter("links_*"):
        data = redis_news.get(key)
        if data is None:
            redis_news.delete(key)
            continue

        delete_key = True
        data = data.decode("utf-8")
        page = None
        try:
            data = json.loads(data)

            if _telegram_retry_pending(data):
                delete_key = False
                continue

            page = find_page(pages, data, key)
            if not page:
                continue

            if page.id not in ignoring_tokens:
                ignoring_tokens[page.id] = get_page_ignoring_tokens(page)

            data["iv_link"] = f"https://t.me/iv?url={data['link']}&rhash={page.iv_code}"
            temp_code = utils.CODE.format(page.message_code)
            message = ""
            try:
                local_vars = {"data": data, "page": page}
                exec(temp_code, globals(), local_vars)  # pylint: disable=exec-used
                message = local_vars.get("message", "")
                if checking_ignore_tags(page, message, ignoring_tokens[page.id]):
                    continue
                if not message or not message.strip():
                    register_log(
                        f"Empty message generated, skipping telegram send for {page.name} and url {data['link']}",
                        "empty message",
                        page,
                        data["link"],
                        "debug",
                    )
                    continue

                send_result = send_telegram_message_with_retry(
                    settings.BOT_API_KEY, page.telegram_channel, message
                )
                if send_result.success:
                    logger.info(
                        "Sent message to Telegram: %s, channel: %s",
                        message,
                        page.telegram_channel,
                    )
                    continue

                preview = _message_preview(message)
                if send_result.failure_kind == "transient":
                    if _schedule_telegram_retry(key, data):
                        delete_key = False
                        register_log(
                            (
                                f"Telegram send deferred for {page.name} "
                                f"(channel: {page.telegram_channel}), "
                                f"attempt {data['telegram_retry_count']}/{TELEGRAM_MAX_DEFER_ATTEMPTS}, "
                                f"retry in {TELEGRAM_DEFER_SECONDS // 60} minutes. "
                                f"Preview: {preview}"
                            ),
                            send_result.error or "transient telegram error",
                            page,
                            data["link"],
                            "info",
                        )
                    else:
                        register_log(
                            (
                                f"Failed to send message to Telegram after "
                                f"{TELEGRAM_MAX_DEFER_ATTEMPTS} deferred attempts. "
                                f"Channel: {page.telegram_channel}. Preview: {preview}"
                            ),
                            send_result.error or "telegram send failed",
                            page,
                            data["link"],
                            "error",
                        )
                else:
                    register_log(
                        (
                            f"Permanent Telegram send failure for {page.name} "
                            f"(channel: {page.telegram_channel}). Preview: {preview}"
                        ),
                        send_result.error or "telegram send failed",
                        page,
                        data["link"],
                        "error",
                    )
            except KeyError as error:
                message = f"redis-exporter, key-error, code was: {temp_code}"
                register_log(
                    message,
                    str(error),
                    page,
                    data["link"],
                    include_traceback=True,
                )
            except Exception as error:  # pylint: disable=broad-except
                message = f"redis-exporter, general-error, code was: {temp_code}"
                register_log(
                    message,
                    str(error),
                    page,
                    data["link"],
                    include_traceback=True,
                )
        except Exception as error:  # pylint: disable=broad-except
            message = f"redis-exporter, general-error, key was: {key.decode('utf-8')}"
            register_log(
                message,
                str(error),
                page,
                data.get("link") if isinstance(data, dict) else None,
                include_traceback=True,
            )
        finally:
            if delete_key:
                redis_news.delete(key)


@crawler.task()
def test_error():
    """
    This function is useful to check whether the sentry module, registers
    errors correctly or not?
    """
    logger.error("Test Error!")
    raise Exception("hi")


def check_page_reports(page, warning_threshold, time_threshold):
    """
    Check reports for a specific page and send a warning if there are consecutive zero counts.
    """
    recent_reports = models.Report.objects.filter(
        page=page, created_at__gte=time_threshold
    ).order_by("-created_at")[:warning_threshold]

    if len(recent_reports) == warning_threshold:
        all_zero = all(report.new_links == 0 for report in recent_reports)
        if not (all_zero and page.telegram_channel):
            return

        warning_message = (
            f"⚠️ Warning: Page '{page.name or page.url}' has had zero new links "
            f"for {warning_threshold} consecutive crawls. Please check the crawling configuration.\n\n"
            f"Last {warning_threshold} crawl results:\n"
        )

        # Add details of each report
        for i, report in enumerate(recent_reports, 1):
            warning_message += (
                f"{i}. Crawl at {report.created_at.strftime('%Y-%m-%d %H:%M:%S')} - "
                f"Fetched: {report.fetched_links}, New: {report.new_links}\n"
            )

        # Send warning using the existing send_log_to_telegram task
        send_log_to_telegram.delay(warning_message)


@crawler.task(name="monitor_page_reports")
@only_one_concurrency(key="monitor_page_reports", timeout=TASKS_TIMEOUT)
def monitor_page_reports():
    """
    Monitor reports for all active pages and send warnings if there are consecutive zero counts.
    """
    if settings.DEBUG:
        logger.info("monitor_page_reports is disabled in debug mode")
        return

    logger.info("monitor_page_reports started")
    warning_threshold = 5  # Number of consecutive zero counts to trigger warning
    time_threshold = timezone.localtime() - timedelta(
        days=1
    )  # Look at reports from last 24 hours

    for page in models.Page.objects.filter(status=True):  # Only check active pages
        check_page_reports(page, warning_threshold, time_threshold)
