"""Standalone terminal UI.

``aitutor tui`` opens the full-screen interface when the optional ``textual``
package is installed and this is a real terminal; otherwise it runs the
guided line-mode flow, which needs only the Python standard library.
Both do the same thing: check requirements → pick a file/folder → build the
course with the local model → lesson / practice / check / review.
"""

from __future__ import annotations

import sys


def full_available() -> bool:
    try:
        import textual  # noqa: F401
    except ImportError:
        return False
    return True


def launch(*, full: bool = False, plain: bool = False) -> int:
    interactive = sys.stdin.isatty() and sys.stdout.isatty()
    if plain or (not full and not (interactive and full_available())):
        from aitutor.tui.guided import run as run_guided

        return run_guided()
    if not full_available():
        print('The full-screen interface needs: pip install "aitutor[tui]"\n'
              "Using the guided interface instead.", flush=True)
        from aitutor.tui.guided import run as run_guided

        return run_guided()
    from aitutor.tui.full import run as run_full

    return run_full()
