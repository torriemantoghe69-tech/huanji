from __future__ import annotations

import sys
from typing import Any

import main as app
from PySide6.QtCore import QTimer


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
    """Restore the gallery page and scroll offset after the preview dialog exits."""
    original_exec = app.PreviewDialog.exec

    def patched_exec(self: app.PreviewDialog):
        parent = self.parentWidget()
        saved_page = getattr(parent, "current_page", None)
        saved_scrollbar = None
        saved_scroll_value = None
        if parent is not None and hasattr(parent, "scroll"):
            try:
                saved_scrollbar = parent.scroll.verticalScrollBar()
                saved_scroll_value = saved_scrollbar.value()
            except RuntimeError:
                saved_scrollbar = None

        result = original_exec(self)

        if parent is not None and saved_page is not None:
            try:
                if getattr(parent, "current_page", saved_page) != saved_page:
                    parent.current_page = saved_page
                    parent.refresh()
                if saved_scrollbar is not None and saved_scroll_value is not None:
                    QTimer.singleShot(
                        0,
                        lambda bar=saved_scrollbar, value=saved_scroll_value:
                            bar.setValue(value) if bar is not None else None
                    )
            except RuntimeError:
                pass
        return result

    app.PreviewDialog.exec = patched_exec  # type: ignore[assignment]


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
