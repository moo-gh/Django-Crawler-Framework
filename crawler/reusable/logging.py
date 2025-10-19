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
        Removes: Django Version, Python info, Installed Applications, Middleware, and Settings.
        """
        full_traceback = super().get_traceback_text()
        
        # Remove all the verbose configuration sections
        # Split at "Django Version:" which comes before all the unwanted sections
        sections_to_remove = [
            "\nDjango Version:",
            "\n\nDjango Version:",
            "Django Version:",
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
    
    def emit(self, record):
        """
        Override emit to filter out Django configuration from all error emails.
        """
        try:
            # Call the parent emit to send the email
            super().emit(record)
        except Exception:
            self.handleError(record)
    
    def format_subject(self, subject):
        """
        Override to customize the subject line.
        """
        return super().format_subject(subject)
    
    def send_mail(self, subject, message, *args, **kwargs):
        """
        Override send_mail to filter out Django configuration from the message.
        """
        # Filter out the verbose Django configuration sections
        sections_to_remove = [
            "\nDjango Version:",
            "\n\nDjango Version:",
            "Django Version:",
        ]
        
        # Find the earliest section to remove
        earliest_index = len(message)
        for section in sections_to_remove:
            index = message.find(section)
            if index != -1 and index < earliest_index:
                earliest_index = index
        
        # Trim the message to exclude unwanted sections
        if earliest_index < len(message):
            message = message[:earliest_index].rstrip()
        
        # Call the parent send_mail with the filtered message
        return super().send_mail(subject, message, *args, **kwargs)
