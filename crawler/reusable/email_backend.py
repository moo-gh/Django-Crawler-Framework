import ssl

from django.core.mail.backends.smtp import EmailBackend as DjangoEmailBackend
from django.utils.functional import cached_property


class EmailBackend(DjangoEmailBackend):
    """
    SMTP backend compatible with Python 3.12+.

    Django 4.1 passes keyfile/certfile to starttls(), which were removed in
    Python 3.12. This backend uses ssl.SSLContext instead.
    """

    @cached_property
    def ssl_context(self):
        ssl_context = ssl.create_default_context()
        if self.ssl_certfile or self.ssl_keyfile:
            ssl_context.load_cert_chain(self.ssl_certfile, self.ssl_keyfile)
        return ssl_context

    def open(self):
        if self.connection:
            return False

        connection_params = {"local_hostname": self._get_local_hostname()}
        if self.timeout is not None:
            connection_params["timeout"] = self.timeout
        if self.use_ssl:
            connection_params["context"] = self.ssl_context

        try:
            self.connection = self.connection_class(
                self.host, self.port, **connection_params
            )

            if not self.use_ssl and self.use_tls:
                self.connection.starttls(context=self.ssl_context)
            if self.username and self.password:
                self.connection.login(self.username, self.password)
            return True
        except OSError:
            if not self.fail_silently:
                raise

    def _get_local_hostname(self):
        from django.core.mail.utils import DNS_NAME

        return DNS_NAME.get_fqdn()
