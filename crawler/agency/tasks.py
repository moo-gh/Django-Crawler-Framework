from __future__ import absolute_import, unicode_literals
import re
import json
import time
import redis
import socket
import telegram
import importlib
import traceback
from typing import Optional
from datetime import timedelta
from telegram.error import RetryAfter, TelegramError

from django.conf import settings
from django.utils import timezone
from celery.utils.log import get_task_logger

from . import utils, models
from crawler.celery import crawler
from notification import utils as not_utils
from notification import models as not_models
from reusable.other import only_one_concurrency


MINUTE = 60
# caveat: at most the redis-exporter task should take 30 minutes
# otherwise, we would have duplication of messages
TASKS_TIMEOUT = 30 * MINUTE

# Telegram rate limiting configuration
TELEGRAM_MAX_RETRIES = 3
TELEGRAM_BASE_DELAY = 1.0  # Base delay between messages in seconds
TELEGRAM_RETRY_BUFFER = 2  # Extra seconds to add to Telegram's retry_after

logger = get_task_logger(__name__)
redis_news = redis.StrictRedis(host="crawler-redis", port=6379, db=0)


@crawler.task(name="remove_old_reports")
def remove_old_reports():
    before_time = timezone.localtime() - timezone.timedelta(days=7)
    models.Report.objects.filter(created_at__lte=before_time).delete()[0]


@crawler.task(name="remove_old_logs")
def remove_old_logs():
    before_time = timezone.localtime() - timezone.timedelta(days=7)
    models.Log.objects.filter(created_at__lte=before_time).delete()
    models.DBLogEntry.objects.filter(time__lte=before_time).delete()


@crawler.task(name="reset_page_locks")
def reset_page_locks():
    models.Page.objects.update(lock=False)


@crawler.task(name="send_log_to_telegram")
def send_log_to_telegram(message):
    bot_model = not_models.TelegramBot.objects.first()
    account = not_models.TelegramAccount.objects.first()
    if not (bot_model and account):
        return

    # Use the same rate limiting approach for log messages
    bot = telegram.Bot(token=bot_model.telegram_token)
    success = send_telegram_message_with_retry(bot, account.chat_id, message)
    if not success:
        logger.error("Failed to send log message to Telegram after retries")


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

    # Get all pages with active schedules matching the current day and time range
    schedules = models.CrawlScheduling.objects.all()

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
    description: str, error: str, page: models.Page, url: str, log_level: str = "error"
):
    if log_level == "error":
        logger.error("desc: %s\ntrace: %s", description, traceback.format_exc())
    elif log_level == "info":
        logger.info("desc: %s\ntrace: %s", description, traceback.format_exc())
    elif log_level == "debug":
        logger.debug("desc: %s\ntrace: %s", description, traceback.format_exc())
    else:
        logger.warning("desc: %s\ntrace: %s", description, traceback.format_exc())

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


def send_telegram_message_with_retry(
    bot: telegram.Bot,
    chat_id: str,
    message: str,
    max_retries: int = TELEGRAM_MAX_RETRIES,
    formatter: Optional[models.Formatter] = None,
) -> bool:
    """
    Send a Telegram message with proper rate limiting and retry logic.

    Args:
        bot: Telegram bot instance
        chat_id: Telegram chat/channel ID
        message: Message text to send
        max_retries: Maximum number of retry attempts
        formatter: Formatter instance

    Returns:
        bool: True if message was sent successfully, False otherwise
    """
    if formatter:
        message = formatter.format(message)
    for attempt in range(max_retries + 1):
        try:
            bot.send_message(chat_id=chat_id, text=message)
            logger.debug(
                f"Message sent successfully to {chat_id} on attempt {attempt + 1}"
            )
            return True

        except RetryAfter as e:
            retry_after = e.retry_after
            logger.warning(
                f"Rate limit hit. Telegram requires retry after {retry_after} seconds. Attempt {attempt + 1}/{max_retries + 1}"
            )

            if attempt < max_retries:
                # Add some buffer time to the required wait time
                sleep_time = retry_after + TELEGRAM_RETRY_BUFFER
                logger.info(f"Waiting {sleep_time} seconds before retry...")
                time.sleep(sleep_time)
            else:
                logger.error(
                    f"Failed to send message after {max_retries + 1} attempts due to rate limiting"
                )
                return False

        except TelegramError as e:
            if attempt < max_retries:
                # Use exponential backoff for other Telegram errors
                sleep_time = (2**attempt) + 1
                logger.warning(
                    f"Telegram error on attempt {attempt + 1}: {e}, retrying in {sleep_time} seconds..."
                )
                time.sleep(sleep_time)
            else:
                logger.error(
                    f"Failed to send message after {max_retries + 1} attempts due to Telegram error: {e}"
                )
                return False

        except Exception as e:
            logger.error(f"Unexpected error sending Telegram message: {e}")
            return False

    return False


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

    bot = telegram.Bot(token=settings.BOT_API_KEY)
    pages = models.Page.objects.all()
    for key in redis_news.scan_iter("links_*"):
        data = redis_news.get(key)
        if data is None:
            redis_news.delete(key)
            continue

        data = data.decode("utf-8")
        page = None
        try:
            data = json.loads(data)

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
                # prepare the message
                exec(temp_code, globals(), local_vars)  # pylint: disable=exec-used
                # Retrieve the updated 'message' from local_vars
                message = local_vars.get("message", "")
                if checking_ignore_tags(page, message, ignoring_tokens[page.id]):
                    continue
                # Check if message is empty or contains only whitespace
                if not message or not message.strip():
                    register_log(
                        f"Empty message generated, skipping telegram send for {page.name} and url {data['link']}",
                        "empty message",
                        page,
                        data["link"],
                        "debug",
                    )
                    continue

                # Send message with proper rate limiting
                # todo: use formatter to send message
                success = send_telegram_message_with_retry(
                    bot, page.telegram_channel, message
                )
                if not success:
                    register_log(
                        "Failed to send message to Telegram after retries",
                        "telegram send failed",
                        page,
                        data["link"],
                        "error",
                    )
                    continue

                # Add a small delay between messages to be respectful to Telegram's API
                time.sleep(TELEGRAM_BASE_DELAY)
            except KeyError as error:
                message = f"redis-exporter, key-error, code was: {temp_code}"
                register_log(message, error, page, data["link"])
            except Exception as error:  # pylint: disable=broad-except
                message = f"redis-exporter, general-error, code was: {temp_code}"
                register_log(message, error, page, data["link"])
        except Exception as error:  # pylint: disable=broad-except
            message = f"redis-exporter, general-error, key was: {key.decode('utf-8')}"
            register_log(message, error, page, data["link"])
        finally:
            redis_news.delete(key)


@crawler.task()
def test_error():
    """
    This function is useful to check whether the sentry module, registers
    errors correctly or not?
    """
    logger.error("Test Error!")
    raise Exception("hi")


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
        recent_reports = models.Report.objects.filter(
            page=page, created_at__gte=time_threshold
        ).order_by("-created_at")[:warning_threshold]

        if len(recent_reports) == warning_threshold:
            all_zero = all(report.new_links == 0 for report in recent_reports)
            if not (all_zero and page.telegram_channel):
                continue

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
