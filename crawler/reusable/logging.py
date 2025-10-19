from logging import Handler

from django.utils.log import AdminEmailHandler
from django.views.debug import ExceptionReporter

from agency.models import DBLogEntry


class DBHandler(Handler):
    def __init__(self):
        super().__init__()

    def emit(self, record):
        log_entry = DBLogEntry(level=record.levelname, message=self.format(record))
        log_entry.save()


class CustomExceptionReporter(ExceptionReporter):
    """
    Custom exception reporter that excludes verbose Django configuration
    from error emails (Installed Applications, Middleware, Settings).
    """

    def get_traceback_data(self):
        """
        Override to exclude settings, installed apps, and middleware
        from the error email.
        """
        data = super().get_traceback_data()

        # Remove the verbose configuration sections from error emails
        # This removes: Installed Applications, Installed Middleware, and Settings
        data["settings"] = {}  # Empty dict to avoid template errors

        return data


class CustomAdminEmailHandler(AdminEmailHandler):
    """
    Custom admin email handler that excludes verbose Django configuration
    from error emails.
    """

    def get_exception_reporter_class(self, request):
        """
        Return our custom exception reporter.
        """
        return CustomExceptionReporter
