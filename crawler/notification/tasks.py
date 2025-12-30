from django.db.models import Sum
from django.utils import timezone
from celery.utils.log import get_task_logger

from agency import models as age_models
from crawler.celery import crawler
from . import models, utils

logger = get_task_logger(__name__)


@crawler.task(name="count_daily_news")
def count_daily_news():
    """
    Counts the number of new links crawled in the last 24 hours and sends a notification
    via Telegram using the configured bot and account.
    """
    yesterday = timezone.localtime() - timezone.timedelta(days=1)
    new_links = (
        age_models.Report.objects.filter(created_at__gt=yesterday).aggregate(
            Sum("new_links")
        )["new_links__sum"]
        or 0
    )
    message = f"Today we crawled {new_links} new links in the Crawler project."
    bot = models.TelegramBot.objects.first()
    account = models.TelegramAccount.objects.first()
    utils.telegram_bot_send_text(bot.telegram_token, account.chat_id, message)
