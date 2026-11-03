"""PyInstaller runtime hook to suppress stray blank popup windows.

This runs before main.py in the frozen build and installs a global event
filter that hides tiny, untitled top-level windows while leaving dialogs and
menus alone.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QEvent, QTimer
from PySide6.QtWidgets import QApplication, QWidget, QMenu, QDialog, QPushButton, QMainWindow, QScrollArea

TARGET_BUTTON_TEXTS = {"批量选择", "全选当前列表"}
MAIN_WINDOW_TITLE = "幻境壁纸馆"
PREVIEW_WINDOW_TITLE = "图片预览"


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

    def __init__(self, parent=None):
        super().__init__(parent)
        self._toolbar_buttons_pruned = False
        self._saved_scroll_value = None

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

    def _main_scroll_bar(self):
        app = QApplication.instance()
        if app is None:
            return None
        for widget in app.topLevelWidgets():
            if isinstance(widget, QMainWindow) and widget.windowTitle().strip() == MAIN_WINDOW_TITLE:
                for area in widget.findChildren(QScrollArea):
                    bar = area.verticalScrollBar()
                    if bar is not None:
                        return bar
        return None

    def _capture_main_scroll(self) -> None:
        bar = self._main_scroll_bar()
        if bar is not None:
            self._saved_scroll_value = bar.value()

    def _restore_main_scroll(self) -> None:
        if self._saved_scroll_value is None:
            return
        bar = self._main_scroll_bar()
        if bar is None:
            return
        value = self._saved_scroll_value
        self._saved_scroll_value = None
        QTimer.singleShot(0, lambda b=bar, v=value: b.setValue(v))

    def _prune_toolbar_buttons(self) -> None:
        if self._toolbar_buttons_pruned:
            return
        app = QApplication.instance()
        if app is None:
            return
        removed = False
        for widget in app.allWidgets():
            if isinstance(widget, QPushButton) and widget.text().strip() in TARGET_BUTTON_TEXTS:
                widget.hide()
                widget.setEnabled(False)
                widget.deleteLater()
                removed = True
        if removed:
            self._toolbar_buttons_pruned = True

    def eventFilter(self, watched, event):
        if not isinstance(watched, QWidget):
            return False

        title = watched.windowTitle().strip()

        if event.type() in self._CHECK_EVENTS:
            QTimer.singleShot(0, self._prune_toolbar_buttons)
            if title == PREVIEW_WINDOW_TITLE:
                QTimer.singleShot(0, self._capture_main_scroll)
            if self._is_blank_top_level(watched):
                # Defer one tick so size/flags settle before we judge it.
                QTimer.singleShot(0, lambda w=watched: self._hide_if_blank(w))

        if title == PREVIEW_WINDOW_TITLE and event.type() in (QEvent.Type.Hide, QEvent.Type.Close):
            self._restore_main_scroll()

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


# Keep preview decoding independent from the temporary dialog size.  The
# image is decoded once to a generous common bound and then fitted to the
# current QLabel area, so portrait and landscape files use the same rule.
def _install_preview_scaling_patch():
    import builtins
    import sys
    from PySide6.QtCore import Qt, QObject, QEvent, QTimer
    from PySide6.QtGui import QPixmap

    original_import = builtins.__import__
    installed = {"done": False}

    class _PreviewImageResizeFilter(QObject):
        """Refit the cached image whenever the actual image viewport changes."""
        def __init__(self, dialog):
            super().__init__(dialog.image)
            self.dialog = dialog

        def eventFilter(self, watched, event):
            if event.type() == QEvent.Type.Resize:
                # QLabel receives its final geometry after the dialog/layout resize.
                QTimer.singleShot(0, lambda d=self.dialog: _refresh_display(d))
            return False

    def _refresh_display(instance):
        key = getattr(instance, "_current_key", None)
        cache = getattr(instance, "_image_cache", {})
        image = cache.get(key) if key is not None else None
        if image is not None and not image.isNull():
            area = instance.image.contentsRect().size()
            if area.width() > 0 and area.height() > 0:
                fitted = QPixmap.fromImage(image).scaled(
                    area,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                instance.image.setText("")
                instance.image.setPixmap(fitted)

    def _patch(app):
        if installed["done"] or not hasattr(app, "PreviewDialog"):
            return
        dialog = app.PreviewDialog
        original_cache_key = dialog._cache_key
        original_show_current = dialog.show_current
        original_loaded = dialog._on_image_loaded

        def stable_cache_key(self, index, target=None):
            path = str(app.IMAGE_DIR / self.rows[index][1])
            return (path, 2560, 2560)

        def display_cached_image(self, image):
            if image is None or image.isNull():
                self.image.setPixmap(QPixmap())
                return
            area = self.image.contentsRect().size()
            if area.width() < 1 or area.height() < 1:
                return
            pixmap = QPixmap.fromImage(image)
            fitted = pixmap.scaled(
                area,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.image.setText("")
            self.image.setPixmap(fitted)

        def stable_show_current(self):
            original_show_current(self)
            key = getattr(self, "_current_key", None)
            image = self._image_cache.get(key) if key is not None else None
            if image is not None:
                display_cached_image(self, image)
            else:
                # Never leave the previous wallpaper visible at a different scale.
                self.image.setPixmap(QPixmap())

        def stable_image_loaded(self, key, image):
            original_loaded(self, key, image)
            if key == getattr(self, "_current_key", None) and image is not None and not image.isNull():
                display_cached_image(self, image)

        original_dialog_init = dialog.__init__

        def responsive_dialog_init(self, *args, **kwargs):
            original_dialog_init(self, *args, **kwargs)
            self._preview_resize_filter = _PreviewImageResizeFilter(self)
            self.image.installEventFilter(self._preview_resize_filter)

        dialog.__init__ = responsive_dialog_init
        dialog._cache_key = stable_cache_key
        dialog.show_current = stable_show_current
        dialog._on_image_loaded = stable_image_loaded
        installed["done"] = True

    def _import_with_preview_patch(name, globals=None, locals=None, fromlist=(), level=0):
        module = original_import(name, globals, locals, fromlist, level)
        if name == "main":
            target = sys.modules.get("main", module)
            _patch(target)
        return module

    builtins.__import__ = _import_with_preview_patch


_install_preview_scaling_patch()
