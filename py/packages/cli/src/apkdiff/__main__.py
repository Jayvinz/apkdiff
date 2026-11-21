"""Allow running the tool as `python -m apkdiff ...`.

Python runs __main__.py for `python -m package`. It calls cli.main() and uses
the returned integer as the exit code:
0 success, 1 size regression, 2 argument/data error.
"""

from .cli import main

raise SystemExit(main())
