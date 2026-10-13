#!/usr/bin/env python
import os
import sys
import tempfile

if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "smearsight_site.settings")
    if len(sys.argv) > 1 and sys.argv[1] == "test" and "SMEARSIGHT_DATA" not in os.environ:
        os.environ["SMEARSIGHT_DATA"] = tempfile.mkdtemp(prefix="smearsight_test_")   # never touch real data
    from django.core.management import execute_from_command_line
    execute_from_command_line(sys.argv)
