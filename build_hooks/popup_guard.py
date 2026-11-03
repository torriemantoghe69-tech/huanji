"""PyInstaller runtime hook to suppress stray blank popup windows.

This runs before main.py in the frozen build and installs a global event
filter that hides tiny, untitled top-level windows while leaving dialogs and
menus alone.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QEvent
from PySide6.QtWidgets import QApplication, QWidget, QMenu, QDialog


class _BlankPopupGuard(QObject):
    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Show and isinstance(watched, QWidget):
            # Keep normal dialogs and menus working.
            if isinstance(watched, (QMenu, QDialog)):
                return False

            if watched.parentWidget() is None:
                title = watched.windowTitle().strip()
                size = watched.size()
                if not title and size.width() <= 260 and size.height() <= 180:
                    watched.hide()
                    return True

        return False


# Patch QApplication so the guard is installed as soon as the app is created.
_orig_init = QApplication.__init__
_orig_set_parent = QWidget.setParent


def _patched_set_parent(self, *args, **kwargs):
    parent = args[0] if args else kwargs.get("parent", None)
    if parent is None and self.objectName() == "WallpaperCard":
        # Keep wallpaper cards attached so they do not flash as blank top-level windows.
        return
    return _orig_set_parent(self, *args, **kwargs)


def _patched_init(self, *args, **kwargs):
    _orig_init(self, *args, **kwargs)
    guard = _BlankPopupGuard(self)
    self._blank_popup_guard = guard
    self.installEventFilter(guard)


QApplication.__init__ = _patched_init
QWidget.setParent = _patched_set_parent
