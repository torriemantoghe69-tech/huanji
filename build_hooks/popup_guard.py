"""PyInstaller runtime hook to suppress stray blank popup windows.

This runs before main.py in the frozen build and installs a global event
filter that hides tiny, untitled top-level windows while leaving dialogs and
menus alone.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QEvent, QTimer
from PySide6.QtWidgets import QApplication, QWidget, QMenu, QDialog


class _BlankPopupGuard(QObject):
    _CHECK_EVENTS = {
        QEvent.Type.Show,
        QEvent.Type.Polish,
        QEvent.Type.PolishRequest,
        QEvent.Type.Resize,
        QEvent.Type.Move,
        QEvent.Type.ParentChange,
        QEvent.Type.UpdateRequest,
        QEvent.Type.WindowActivate,
    }

    def _is_blank_top_level(self, watched: QWidget) -> bool:
        if isinstance(watched, (QMenu, QDialog)):
            return False
        if watched.parentWidget() is not None:
            return False

        title = watched.windowTitle().strip()
        size = watched.size()
        return not title and size.width() <= 420 and size.height() <= 260

    def _hide_if_blank(self, watched: QWidget) -> None:
        try:
            if self._is_blank_top_level(watched):
                watched.hide()
        except RuntimeError:
            # Widget may already be gone by the time the deferred check runs.
            return

    def eventFilter(self, watched, event):
        if not isinstance(watched, QWidget):
            return False

        if event.type() in self._CHECK_EVENTS:
            if self._is_blank_top_level(watched):
                # Defer one tick so size/flags settle before we judge it.
                QTimer.singleShot(0, lambda w=watched: self._hide_if_blank(w))

        if event.type() == QEvent.Type.Show and self._is_blank_top_level(watched):
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
