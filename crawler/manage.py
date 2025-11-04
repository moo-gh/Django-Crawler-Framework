#!/usr/bin/env python
import os
import sys
import importlib


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "crawler.settings")
    execute_from_command_line = None
    try:
        management_module = importlib.import_module("django.core.management")
        execute_from_command_line = management_module.execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
