"""Keep genlayer-test direct mode usable on Windows until its temp-file fix ships."""

import os


_delayed_unlinks = []


def pytest_configure():
    if os.name != "nt":
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


def pytest_sessionfinish():
    for path in _delayed_unlinks:
        try:
            os.unlink(path)
        except OSError:
            pass
