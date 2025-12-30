from rest_framework import serializers
from rest_framework.fields import CharField

from . import models


class AgencySerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Agency
        fields = [
            "id",
            "name",
            "status",
            "country",
            "website",
            "created_at",
            "updated_at",
            "deleted_at",
            "crawl_headers",
        ]


class CrawlReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Report
        fields = [
            "id",
            "page",
            "new_links",
            "created_at",
            "updated_at",
            "fetched_links",
            "last_crawl_status",
        ]


class PageSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Page
        fields = [
            "id",
            "url",
            "agency",
            "status",
            "use_proxy",
            "structure",
            "last_crawl",
            "created_at",
            "updated_at",
            "deleted_at",
            "crawl_interval",
        ]


class ReportListSerializer(serializers.ModelSerializer):
    page = CharField(read_only=True, source="page.url")
    agency = CharField(read_only=True, source="page.agency.name")
    duration = serializers.SerializerMethodField("is_named_bar")

    def is_named_bar(self, obj):
        """
        Calculates the duration of the crawl report in seconds.
        """
        seconds = round((obj.updated_at - obj.created_at).total_seconds())
        return f"{seconds} sec"

    class Meta:
        model = models.Report
        fields = [
            "id",
            "log",
            "page",
            "agency",
            "status",
            "duration",
            "new_links",
            "created_at",
            "updated_at",
            "fetched_links",
        ]
