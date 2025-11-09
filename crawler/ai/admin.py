from django.contrib import admin

from reusable.admins import ReadOnlyAdminDateFieldsMIXIN
from ai.models import LLMModel, LLMUsage


@admin.register(LLMModel)
class LLMModelAdmin(ReadOnlyAdminDateFieldsMIXIN):
    list_display = ("pk", "name", "provider", "input_token_price", "output_token_price")
    list_filter = ("provider",)
    search_fields = ("name",)


@admin.register(LLMUsage)
class LLMUsageAdmin(ReadOnlyAdminDateFieldsMIXIN):
    list_display = (
        "pk",
        "model",
        "usage_type",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "input_cost",
        "output_cost",
        "total_cost",
        "request_id",
        "model_version",
        "response_time_ms",
        "success",
        "error_message",
    )
    list_filter = ("model", "usage_type")
    search_fields = ("model", "usage_type")
