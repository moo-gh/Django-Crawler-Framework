import importlib
import logging
from django.db import models
from django.utils import timezone
from django.template.defaultfilters import truncatechars


from reusable.models import BaseModel
from notification.models import MessageTemplate
from . import utils


logger = logging.getLogger(__name__)


class Agency(BaseModel):
    name = models.CharField(max_length=20, null=False, unique=True)
    country = models.CharField(max_length=20, default="NA")
    website = models.CharField(max_length=100, null=False, unique=True)
    crawl_headers = models.JSONField(null=True, blank=True, default=dict)
    status = models.BooleanField(default=1)
    load_timeout = models.PositiveIntegerField(
        default=5,
        help_text="how many seconds to wait for page to load",
    )
    link_keep_days = models.PositiveIntegerField(
        default=1,
        null=True,
        blank=True,
        help_text="how many days to keep the links of crawled page in redis",
    )

    class Meta:
        verbose_name_plural = "agencies"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.pages.update(status=self.status)

    def __str__(self):
        return f"({self.pk} - {self.name})"

    @property
    def pages_count(self):
        return self.pages.count()


class Structure(BaseModel):
    name = models.CharField(max_length=20, null=True)
    news_links_structure = models.JSONField()
    news_links_code = models.TextField(
        null=True,
        blank=True,
        help_text='like: for el in elements: try: links.append(el["href"]) except: continue',
    )
    news_meta_structure = models.JSONField(null=True, blank=True)

    def __str__(self):
        return f"({self.pk} - {self.name})"


class Cookie(BaseModel):
    key_values = models.JSONField()


class Page(BaseModel):
    name = models.CharField(max_length=50, null=True, blank=True)
    agency = models.ForeignKey(Agency, related_name="pages", on_delete=models.CASCADE)
    scroll = models.PositiveIntegerField(
        default=0, help_text="how many times to scroll"
    )
    url = models.CharField(max_length=2000, null=False, unique=True)
    crawl_interval = models.PositiveIntegerField(default=60, help_text="minute")
    load_sleep = models.PositiveIntegerField(
        default=4, blank=True, help_text="each link sleep"
    )
    links_sleep = models.PositiveIntegerField(
        default=1, blank=True, help_text="all links sleep"
    )
    last_crawl = models.DateTimeField(null=True)
    last_crawl_count = models.PositiveIntegerField(null=True, blank=True)
    last_crawl_new_count = models.PositiveIntegerField(null=True, blank=True)
    status = models.BooleanField(default=1)
    fetch_content = models.BooleanField(default=1)
    structure = models.ForeignKey(
        Structure, on_delete=models.SET_NULL, null=True, blank=True
    )
    telegram_channel = models.CharField(
        max_length=100, null=True, blank=True, help_text="like: @jobinja"
    )
    iv_code = models.CharField(max_length=100, null=True, blank=True)
    message_code = models.TextField(
        default=None,
        null=True,
        help_text='message=data["link"] or data["iv_link"]',
        blank=True,
    )
    message_template = models.ForeignKey(
        MessageTemplate, on_delete=models.SET_NULL, null=True, blank=True
    )
    take_picture = models.BooleanField(default=False)
    cookie = models.ForeignKey(
        Cookie, related_name="pages", on_delete=models.CASCADE, null=True
    )
    lock = models.BooleanField(default=False)
    use_proxy = models.BooleanField(default=False)
    filtering_tags = models.ManyToManyField(
        "notification.FilteringTag", related_name="pages", blank=True
    )
    off_times = models.ManyToManyField("OffTime", related_name="pages", blank=True)
    formatter = models.ForeignKey("ai.formatter", related_name="pages", on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"({self.pk} - {self.name})"

    @property
    def days_to_keep(self):
        return self.agency.link_keep_days

    @property
    def masked_name(self):
        if self.name is None:
            return "NA"
        return self.name

    @property
    def today_crawl_count(self):
        today = timezone.localtime().replace(hour=0)
        return self.report.filter(created_at__gte=today).count()

    @property
    def is_off_time(self, current_time=None) -> bool:
        """
        Check if the current time is within any off-time period for this page.
        """
        if not current_time:
            current_time = timezone.localtime()

        current_day = current_time.weekday()  # Monday is 0 and Sunday is 6
        current_time_only = current_time.time()

        # Filter off times for the current day
        todays_off_times = self.off_times.filter(day_of_week=current_day)

        for off_time in todays_off_times:
            if off_time.start_time <= current_time_only <= off_time.end_time:
                return True
        return False


class Report(BaseModel):
    page = models.ForeignKey(Page, on_delete=models.CASCADE, related_name="report")
    fetched_links = models.IntegerField(default=0)
    new_links = models.IntegerField(default=0)
    picture = models.ImageField(
        upload_to=utils.report_image_path, blank=True, null=True
    )
    log = models.TextField(blank=True)

    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    STATUS_CHOICES = (
        (PENDING, "Pending"),
        (COMPLETED, "Completed"),
        (FAILED, "Failed"),
    )
    status = models.CharField(max_length=300, choices=STATUS_CHOICES, null=True)

    def __str__(self):
        return f"({self.pk} - {self.page.url})"

    @property
    def is_completed(self):
        return self.status == Report.COMPLETED

    @property
    def is_failed(self):
        return self.status == Report.FAILED

    @property
    def is_pending(self):
        return self.status == Report.PENDING

    @property
    def page_name(self):
        if self.page:
            return self.page.masked_name
        return None


class Log(BaseModel):
    page = models.ForeignKey(
        Page, on_delete=models.CASCADE, related_name="logs", null=True
    )
    url = models.CharField(max_length=2000, null=True)
    description = models.TextField(default="")
    error = models.TextField(null=True)
    level = models.CharField(max_length=10, null=True)

    CRAWLING = "cra"
    SENDING = "sen"
    PHASE_CHOICES = (
        (CRAWLING, "کرال"),
        (SENDING, "ارسال به تلگرام"),
    )
    phase = models.CharField(choices=PHASE_CHOICES, null=True, blank=True, max_length=3)

    def __str__(self):
        return f"({self.pk} - {self.page})"

    @property
    def log_message(self):
        return f"(id: {self.pk}\ndesc:\n{self.description}\n\nerror:\n{self.error})"

    def save(self, *args, **kwargs):
        tasks_module = importlib.import_module("agency.tasks")
        super().save(*args, **kwargs)
        if self.level in ["error", "warning"]:
            # no need to send log to telegram for debug logs
            tasks_module.send_log_to_telegram.delay(self.log_message)


class Option(BaseModel):
    key = models.CharField(max_length=70)
    value = models.CharField(max_length=70)

    def __str__(self):
        return f"({self.pk} - {self.key})"


class DBLogEntry(models.Model):
    time = models.DateTimeField(auto_now_add=True)
    level = models.CharField(max_length=10)
    message = models.TextField()

    @property
    def short_message(self):
        return truncatechars(self.message, 50)


class OffTime(BaseModel):
    DAYS_OF_WEEK = [
        (0, "Monday"),
        (1, "Tuesday"),
        (2, "Wednesday"),
        (3, "Thursday"),
        (4, "Friday"),
        (5, "Saturday"),
        (6, "Sunday"),
    ]

    day_of_week = models.IntegerField(choices=DAYS_OF_WEEK)
    start_time = models.TimeField()
    end_time = models.TimeField()

    class Meta:
        ordering = ["day_of_week", "start_time"]
        verbose_name = "Off Time"
        verbose_name_plural = "Off Times"

    def __str__(self):
        day = dict(self.DAYS_OF_WEEK).get(self.day_of_week, "Unknown")
        return f"{day}: {self.start_time.strftime('%H:%M')} - {self.end_time.strftime('%H:%M')}"


class Day(BaseModel):
    name = models.CharField(max_length=10)  # e.g., "Monday"
    abbreviation = models.CharField(max_length=3)  # e.g., "MON"

    def __str__(self):
        return f"({self.pk} - {self.name})"


class CrawlScheduling(BaseModel):
    page = models.ForeignKey(Page, on_delete=models.CASCADE, related_name="schedules")
    days = models.CharField(
        max_length=50,
        help_text="MON,TUE,WED,THU,FRI,SAT,SUN. You should use comma to separate.",
    )
    start_times = models.TextField(
        help_text="e.g., 08:00,12:00,18:00. You should use comma to separate."
    )

    def __str__(self):
        return f"({self.pk} - {self.page})"

    def get_days(self) -> list["str"]:
        return [day.strip() for day in self.days.split(",")]

    def get_start_times(self) -> list["str"]:
        return [time.strip() for time in self.start_times.split(",")]
