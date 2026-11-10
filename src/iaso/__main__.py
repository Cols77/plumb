"""Allow ``python -m iaso``."""

import sys

from iaso.cli import main

sys.exit(main())
