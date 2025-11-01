from django.contrib import admin

from reusable.admins import ReadOnlyAdminDateFieldsMIXIN
from ai.models import LLMModel


@admin.register(LLMModel)
class LLMModelAdmin(ReadOnlyAdminDateFieldsMIXIN):
    list_display = ("name", "provider", "input_token_price", "output_token_price")
    list_filter = ("provider",)
    search_fields = ("name",)
