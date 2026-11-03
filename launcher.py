from __future__ import annotations

import sys
from typing import Any

import main as app
from PySide6.QtWidgets import QDialog, QScrollBar


TARGET_BUTTON_ATTRS = ("select_mode_btn", "select_all_btn")


def _patch_toolbar_buttons() -> None:
    """Remove the old batch-selection controls from the built UI."""
    original_build_ui = app.MainWindow._build_ui

    def patched_build_ui(self: app.MainWindow) -> None:
        original_build_ui(self)
        for attr in TARGET_BUTTON_ATTRS:
            button = getattr(self, attr, None)
            if button is None:
                continue
            try:
                button.setEnabled(False)
                button.hide()
                button.setParent(None)
                button.deleteLater()
            except RuntimeError:
                pass
            setattr(self, attr, None)

    app.MainWindow._build_ui = patched_build_ui  # type: ignore[assignment]


def _patch_preview_dialog() -> None:
    """Keep gallery scroll position and preview image index stable across fullscreen toggles."""
    original_init = app.PreviewDialog.__init__
    original_toggle_fullscreen = app.PreviewDialog.toggle_fullscreen
    original_escape_fullscreen = app.PreviewDialog._escape_fullscreen
    original_close_event = getattr(app.PreviewDialog, "closeEvent", None)

    def patched_init(self: app.PreviewDialog, rows, start_index=0, parent=None):
        original_init(self, rows, start_index=start_index, parent=parent)
        self._restore_scroll_value = None
        self._restore_scrollbar: QScrollBar | None = None
        self._restore_index = self.current_index
        if parent is not None and hasattr(parent, "scroll"):
            try:
                self._restore_scrollbar = parent.scroll.verticalScrollBar()
                self._restore_scroll_value = self._restore_scrollbar.value()
            except Exception:
                self._restore_scrollbar = None
                self._restore_scroll_value = None

    def _restore_state(self: app.PreviewDialog) -> None:
        if self._restore_scrollbar is not None and self._restore_scroll_value is not None:
            try:
                self._restore_scrollbar.setValue(self._restore_scroll_value)
            except Exception:
                pass
        if hasattr(self, "_restore_index"):
            try:
                self.current_index = int(self._restore_index)
                self.show_current()
            except Exception:
                pass

    def patched_toggle_fullscreen(self: app.PreviewDialog):
        self._restore_index = self.current_index
        original_toggle_fullscreen(self)
        _restore_state(self)

    def patched_escape_fullscreen(self: app.PreviewDialog):
        self._restore_index = self.current_index
        original_escape_fullscreen(self)
        _restore_state(self)

    def patched_close_event(self: app.PreviewDialog, event):
        _restore_state(self)
        if original_close_event is not None:
            return original_close_event(self, event)
        return QDialog.closeEvent(self, event)

    app.PreviewDialog.__init__ = patched_init  # type: ignore[assignment]
    app.PreviewDialog.toggle_fullscreen = patched_toggle_fullscreen  # type: ignore[assignment]
    app.PreviewDialog._escape_fullscreen = patched_escape_fullscreen  # type: ignore[assignment]
    app.PreviewDialog.closeEvent = patched_close_event  # type: ignore[assignment]


_patch_toolbar_buttons()
_patch_preview_dialog()


def main() -> int:
    if callable(getattr(app, "main", None)):
        return int(app.main())  # type: ignore[call-arg]

    app.ensure_storage()
    qapp = app.QApplication(sys.argv)
    qapp.setApplicationName(app.APP_NAME)
    qapp.setOrganizationName("Huanjing")
    window = app.MainWindow()
    window.show()
    return qapp.exec()


if __name__ == "__main__":
    raise SystemExit(main())
