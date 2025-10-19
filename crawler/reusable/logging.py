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
        data["settings"] = []  # Empty list since Django expects a list of tuples

        return data
    
    def get_traceback_text(self):
        """
        Override to provide cleaner text output without verbose settings.
        Removes: Installed Applications, Installed Middleware, and Settings sections.
        """
        full_traceback = super().get_traceback_text()
        
        # Remove the verbose configuration sections
        sections_to_remove = [
            "Installed Applications:",
            "Installed Middleware:",
            "Settings:",
        ]
        
        # Find the earliest section to remove
        earliest_index = len(full_traceback)
        for section in sections_to_remove:
            index = full_traceback.find(section)
            if index != -1 and index < earliest_index:
                earliest_index = index
        
        # Return everything before the first unwanted section
        if earliest_index < len(full_traceback):
            return full_traceback[:earliest_index].rstrip()
        
        return full_traceback


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
