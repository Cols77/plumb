"""The merge boundary, ``plumb merge-check`` (sub-project 3, ``docs/specs/sp3-merge-boundary.md``).

``merge_report`` gathers every section as data, ``render`` prints it on one screen and
``exit_code`` gives the one exit (1 integrity, claims or links; 5 verification; 4 the owner's
confirmation; 0 green). ``plumb validate --merge BASE`` is ``merge_report(run_full=False)``
plus ``render``, so the two never disagree. Kept import-light: the heavy work loads inside
the functions.
"""

from __future__ import annotations

from plumb.boundary.prepush import install_pre_push_hook, uninstall_pre_push_hook
from plumb.boundary.report import MergeReport, as_dict, exit_code, merge_report, render

__all__ = ["MergeReport", "as_dict", "exit_code", "install_pre_push_hook", "merge_report",
           "render", "uninstall_pre_push_hook"]
