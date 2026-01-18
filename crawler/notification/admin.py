from django.contrib import admin

from . import models
from reusable.admins import ReadOnlyAdminDateFieldsMIXIN


@admin.register(models.TelegramBot)
class TelegramBotAdmin(ReadOnlyAdminDateFieldsMIXIN):
    list_display = ("pk", "name")


@admin.register(models.TelegramAccount)
class TelegramAccountAdmin(ReadOnlyAdminDateFieldsMIXIN):
    list_display = ("pk", "name", "chat_id")


@admin.register(models.MessageTemplate)
class MessageTemplateAdmin(ReadOnlyAdminDateFieldsMIXIN):
    list_display = ("pk", "name", "created_at", "updated_at")


@admin.register(models.FilteringTag)
class FilteringTagAdmin(ReadOnlyAdminDateFieldsMIXIN):
    list_display = ("pk", "name")


@admin.register(models.FilteringToken)
class FilteringTokenAdmin(ReadOnlyAdminDateFieldsMIXIN):
    list_display = ("pk", "token", "tag", "created_at")
    search_fields = ("token",)
    list_filter = ("tag",)
    list_per_page = 20
