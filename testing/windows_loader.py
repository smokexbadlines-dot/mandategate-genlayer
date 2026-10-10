"""Defer gltest's temp-file unlink until stdin is restored on Windows."""

import os


_delayed_unlinks = []
_installed = False


def install() -> None:
    global _installed
    if os.name != "nt" or _installed:
        return
    from gltest.direct import loader

    original_inject = loader._inject_message_to_fd0
    original_unlink = os.unlink

    def inject_on_windows(vm):
        def defer_locked_file(path, *args, **kwargs):
            try:
                original_unlink(path, *args, **kwargs)
            except PermissionError:
                _delayed_unlinks.append(path)

        os.unlink = defer_locked_file
        try:
            original_inject(vm)
        finally:
            os.unlink = original_unlink

    loader._inject_message_to_fd0 = inject_on_windows
    _installed = True


def cleanup() -> None:
    for path in _delayed_unlinks:
        try:
            os.unlink(path)
        except OSError:
            pass
    _delayed_unlinks.clear()
