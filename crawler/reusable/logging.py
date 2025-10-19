from logging import Handler

from django.utils.log import AdminEmailHandler

from agency.models import DBLogEntry


class DBHandler(Handler):
    def __init__(self):
        super().__init__()

    def emit(self, record):
        log_entry = DBLogEntry(level=record.levelname, message=self.format(record))
        log_entry.save()


class CustomAdminEmailHandler(AdminEmailHandler):
    """
    Custom admin email handler that excludes verbose Django configuration
    from error emails (Django Version, Python info, Installed Applications,
    Middleware, and Settings sections).
    """

    def format_subject(self, subject):
        """
        Override to add 'Crawler Project' to the beginning of the subject.
        """
        formatted = super().format_subject(subject)
        # Remove '[Django] ' and add 'Crawler Project - [Django] '
        if formatted.startswith("[Django] "):
            formatted = "Crawler Project - " + formatted
        return formatted

    def send_mail(self, subject, message, *args, **kwargs):
        """
        Override send_mail to filter out Django configuration from the message.
        """
        # Filter out the verbose Django configuration sections
        # Split at "Django Version:" to remove everything after it
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
