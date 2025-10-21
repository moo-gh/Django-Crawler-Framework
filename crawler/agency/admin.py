import importlib
from typing import Optional
from datetime import datetime
from prettyjson import PrettyJSONWidget
from rangefilter.filter import DateTimeRangeFilter

from django import forms
from django.contrib import admin
from django.contrib import messages
from django.utils.html import format_html
from django.utils.translation import ngettext
from django.template.defaultfilters import truncatechars
from django.urls import reverse
from django.http import HttpResponseRedirect
from djangoeditorwidgets.widgets import MonacoEditorWidget

from reusable.admins import ReadOnlyAdminDateFieldsMIXIN
from agency.serializer import PageSerializer
from agency.models import (
    Agency,
    Page,
    Report,
    Structure,
    Log,
    DBLogEntry,
    OffTime,
    Day,
    CrawlScheduling,
)


@admin.register(Report)
class ReportAdmin(ReadOnlyAdminDateFieldsMIXIN):
    """Admin interface for Report model."""

    list_per_page = 30
    search_fields = ("page__url",)
    list_display = (
        "id",
        "page_name",
        "url",
        "status",
        "agency",
        "duration",
        "fetched_links",
        "new_links",
        "image_tag",
        "started_at",
    )
    readonly_fields = (
        "log",
        "page",
        "status",
        "picture",
        "new_links",
        "fetched_links",
    )
    list_filter = ["status", "page__agency", ("created_at", DateTimeRangeFilter)]

    def url(self, obj: Report) -> str:
        """Generate a clickable URL link."""
        return format_html('<a href="{url}">Link</a>', url=obj.page.url)

    def agency(self, obj: Report) -> str:
        """Get the agency name for the report."""
        return obj.page.agency.name

    def started_at(self, obj: Report) -> datetime:
        """Get the creation time of the report."""
        return obj.created_at

    def duration(self, obj: Report) -> str:
        """Calculate the duration of the report execution."""
        elapsed_seconds = round((obj.updated_at - obj.created_at).total_seconds())
        return f"{elapsed_seconds} sec"

    def image_tag(self, obj: Report) -> Optional[str]:
        """Generate a clickable image link if available."""
        if obj.picture:
            url = "https://www.mo-ghorbani.ir/static/" + obj.picture.path.split("/")[-1]
            return format_html('<a href="{url}">Link</a>', url=url)
        return None

    image_tag.short_description = "Image"


@admin.register(Agency)
class AgencyAdmin(ReadOnlyAdminDateFieldsMIXIN):
    """Admin interface for Agency model."""

    list_filter = ("status",)
    list_editable = ("status", "link_keep_days", "load_timeout")
    list_display = (
        "id",
        "name",
        "country",
        "website",
        "status",
        "link_keep_days",
        "load_timeout",
        "pages_count",
        "created_at",
        "updated_at",
    )


class StructureForm(forms.ModelForm):
    """Form for Structure model with custom widgets."""

    class Meta:
        model = Structure
        fields = "__all__"
        widgets = {
            "news_meta_structure": PrettyJSONWidget(),
            "news_links_structure": PrettyJSONWidget(),
            "news_links_code": MonacoEditorWidget(
                attrs={"data-wordwrap": "on", "data-language": "python"}
            ),
        }


@admin.register(Structure)
class StructureAdmin(ReadOnlyAdminDateFieldsMIXIN):
    """Admin interface for Structure model."""

    list_display = ("id", "name", "created_at", "updated_at")
    form = StructureForm
    ordering = ("-updated_at",)
    search_fields = ("name",)


class PageAdminForm(forms.ModelForm):
    """Form for Page model with custom widgets."""

    class Meta:
        model = Page
        fields = "__all__"
        widgets = {
            "message_code": MonacoEditorWidget(
                attrs={"data-wordwrap": "on", "data-language": "python"}
            ),
            "url": forms.URLInput(attrs={"style": "width: 80%;"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.url:
            self.fields["url"].help_text = format_html(
                '<a href="{url}" target="_blank" style="margin-left: 0px;">Link</a>',
                url=self.instance.url,
            )


@admin.register(Page)
class PageAdmin(ReadOnlyAdminDateFieldsMIXIN):
    """Admin interface for Page model."""

    form = PageAdminForm
    list_filter = ("lock", "status", "agency")
    list_editable = ("load_sleep", "links_sleep", "status", "crawl_interval")
    readonly_fields = (
        "last_crawl",
        "created_at",
        "updated_at",
        "deleted_at",
        "crawl_buttons",
    )
    list_display = (
        "get_masked_name",
        "agency",
        "page_url",
        "crawl_interval",
        "links_sleep",
        "load_sleep",
        "last_crawl",
        "get_last_crawl_count",
        "status",
        "today_crawl_count",
        "use_proxy",
        "lock",
        "fetch_content",
        "take_picture",
    )
    fields = (
        "name",
        "agency",
        "url",
        "structure",
        ("crawl_interval", "load_sleep", "links_sleep", "scroll"),
        ("status", "fetch_content", "take_picture", "lock", "use_proxy"),
        ("telegram_channel", "iv_code"),
        "message_code",
        ("filtering_tags", "off_times"),
        "message_template",
        "last_crawl",
        "crawl_buttons",
        ("created_at", "updated_at", "deleted_at"),
    )

    def get_queryset(self, request):
        """Filter queryset to only show pages from active agencies."""
        qs = super().get_queryset(request)
        return qs.filter(agency__status=True)

    def get_ordering(self, request):
        """Order pages by last crawl time."""
        return ["-last_crawl"]

    def page_url(self, obj):
        """Generate a clickable URL link."""
        return format_html('<a href="{url}">Link</a>', url=obj.url)

    @admin.display(description="NAME")
    def get_masked_name(self, instance):
        """Get the masked name of the page."""
        return instance.masked_name

    @admin.display(description="L. Crawl")
    def get_last_crawl(self, instance):
        """Get the last crawl time."""
        return instance.get_last_crawl_at

    @admin.display(description="L. Count")
    def get_last_crawl_count(self, instance):
        """Get the last crawl count if available."""
        if instance.last_crawl_count:
            return instance.last_crawl_count
        return None

    @admin.display(description="Crawl Actions")
    def crawl_buttons(self, obj):
        """Display action buttons for crawling."""
        if obj.pk:  # Only show buttons if object exists
            return format_html(
                '''
                <div style="display: flex; gap: 10px; margin: 10px 0;">
                    <a href="?action=crawl" class="button" style="padding: 10px 15px; background-color: #417690; color: white; text-decoration: none; border-radius: 4px;">
                        Crawl Page
                    </a>
                    <a href="?action=crawl_repetitive" class="button" style="padding: 10px 15px; background-color: #417690; color: white; text-decoration: none; border-radius: 4px;">
                        Crawl Page (Repetitive)
                    </a>
                </div>
                '''
            )
        return "-"

    def change_view(self, request, object_id, form_url="", extra_context=None):
        """Override change view to handle custom actions."""
        action = request.GET.get("action")
        if action in ["crawl", "crawl_repetitive"]:
            obj = self.get_object(request, object_id)
            if obj:
                tasks_module = importlib.import_module("agency.tasks")
                if action == "crawl":
                    tasks_module.page_crawl.delay(PageSerializer(obj).data)
                    self.message_user(
                        request,
                        f"Page '{obj.masked_name}' is in queue to crawl.",
                        messages.SUCCESS,
                    )
                elif action == "crawl_repetitive":
                    tasks_module.page_crawl_repetitive.delay(PageSerializer(obj).data)
                    self.message_user(
                        request,
                        f"Page '{obj.masked_name}' is in queue to crawl. (repetitive)",
                        messages.SUCCESS,
                    )
                # Redirect to remove action parameter from URL
                return HttpResponseRedirect(
                    reverse(
                        "admin:agency_page_change",
                        args=[object_id],
                    )
                )
        return super().change_view(request, object_id, form_url, extra_context)

    # actions
    def crawl_action(self, request, queryset):
        """Action to queue selected pages for crawling."""
        tasks_module = importlib.import_module("agency.tasks")

        for page in queryset:
            tasks_module.page_crawl.delay(PageSerializer(page).data)

        self.message_user(
            request,
            ngettext(
                "%d page is in queue to crawl.",
                "%d pages are in queue to crawl.",
                len(queryset),
            )
            % len(queryset),
            messages.SUCCESS,
        )

    crawl_action.short_description = "Crawl page"

    def crawl_and_ignore_repetitive_action(self, request, queryset):
        """Action to queue selected pages for crawling with repetitive links."""
        tasks_module = importlib.import_module("agency.tasks")

        for page in queryset:
            tasks_module.page_crawl_repetitive.delay(PageSerializer(page).data)

        self.message_user(
            request,
            ngettext(
                "%d page is in queue to crawl. (repetitive)",
                "%d pages are in queue to crawl. (repetitive)",
                len(queryset),
            )
            % len(queryset),
            messages.SUCCESS,
        )

    crawl_and_ignore_repetitive_action.short_description = "Crawl page with repetitive"
    actions = (crawl_action, crawl_and_ignore_repetitive_action)


@admin.register(Log)
class LogAdmin(ReadOnlyAdminDateFieldsMIXIN):
    """Admin interface for Log model."""

    list_display = (
        "pk",
        "base",
        "phase",
        "error",
        "agency",
        "source",
        "created_at",
        "short_description",
    )
    list_filter = ("phase", "page__agency")
    readonly_fields = ("created_at", "updated_at", "deleted_at")

    def source(self, obj):
        """Generate a clickable source link if available."""
        if obj.page is not None:
            return format_html('<a href="{url}">Link</a>', url=obj.page.url)
        return None

    def created_at(self, obj):
        """Format the creation time."""
        return obj.created_at.strftime("%h. %d %H:%M %p")

    def base(self, obj):
        """Generate a clickable URL link if available."""
        if obj.url is not None:
            return format_html('<a href="{url}">Link</a>', url=obj.url)
        return None

    def agency(self, obj):
        """Get the agency name if available."""
        if obj.page is not None:
            return obj.page.agency.name
        return None

    def short_description(self, obj):
        """Get a truncated description."""
        return truncatechars(obj.description, 50)

    def has_change_permission(self, _request, _obj=None):
        """Disable editing logs."""
        return False


@admin.register(DBLogEntry)
class DBLogEntryAdmin(admin.ModelAdmin):
    """Admin interface for DBLogEntry model."""

    list_filter = ("level",)
    readonly_fields = ("level", "message", "time")
    list_display = ("pk", "level", "short_message", "time")

    def delete_all_logs(self, _request, _queryset):
        """Action to delete all log entries."""
        DBLogEntry.objects.all().delete()

    actions = (delete_all_logs,)


@admin.register(OffTime)
class OffTimeAdmin(ReadOnlyAdminDateFieldsMIXIN):
    """Admin interface for OffTime model."""

    list_display = (
        "id",
        "day_of_week",
        "start_time",
        "end_time",
        "get_page_names",
        "updated_at",
    )
    list_editable = ("start_time", "end_time")

    def get_page_names(self, obj):
        """Return the names of pages related to this OffTime, separated by comma."""
        page_names = [page.masked_name for page in obj.pages.all()]
        return ", ".join(page_names) if page_names else "-"

    get_page_names.short_description = "Pages"


@admin.register(Day)
class DayAdmin(ReadOnlyAdminDateFieldsMIXIN):
    """Admin interface for Day model."""

    list_display = ("id", "name", "abbreviation", "created_at")


@admin.register(CrawlScheduling)
class CrawlSchedulingAdmin(ReadOnlyAdminDateFieldsMIXIN):
    """Admin interface for CrawlScheduling model."""

    list_display = ("id", "page", "start_times", "days", "created_at")
    search_fields = ("page__name", "page__url")
