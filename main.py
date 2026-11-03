import ctypes
import logging
import os
import shutil
import sqlite3
import sys
import tempfile
import traceback
import uuid
from pathlib import Path
from collections import OrderedDict

from PySide6.QtCore import Qt, QSize, QEvent, QSettings, QPoint, QRect, QPropertyAnimation, QEasingCurve, QObject, QRunnable, QThreadPool, Signal, QTimer
from PySide6.QtGui import QPixmap, QShortcut, QKeySequence, QImageReader, QImage
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFileDialog, QLineEdit, QListWidget, QListWidgetItem,
    QScrollArea, QGridLayout, QFrame, QMessageBox, QDialog, QInputDialog,
    QMenu, QSizePolicy, QCheckBox, QSpinBox, QToolTip
)

APP_NAME = "幻境壁纸馆"
DATA_DIR = Path.home() / "Pictures" / "HuanjingWallpaperGallery"
IMAGE_DIR = DATA_DIR / "images"
THUMB_DIR = DATA_DIR / "thumbnails"
DB_PATH = DATA_DIR / "gallery.db"
SUPPORTED = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}
PIXMAP_CACHE = OrderedDict()
PIXMAP_CACHE_LIMIT = 160  # Keep nearby thumbnails decoded to reduce scroll-stop stalls

def _log_path():
    base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    try:
        folder = base / "HuanjingWallpaperGallery"
        folder.mkdir(parents=True, exist_ok=True)
        return folder / "crash.log"
    except Exception:
        return Path(tempfile.gettempdir()) / "HuanjingWallpaperGallery-crash.log"

LOG_PATH = _log_path()
logging.basicConfig(filename=str(LOG_PATH), level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s",
                    encoding="utf-8")
logging.info("========== Application launch ==========")
logging.info("Python=%s | executable=%s | frozen=%s", sys.version, sys.executable, getattr(sys, "frozen", False))

def _handle_exception(exc_type, exc_value, exc_tb):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return
    logging.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_tb))
    try:
        sys.__stderr__.write("".join(traceback.format_exception(exc_type, exc_value, exc_tb)))
        sys.__stderr__.flush()
    except Exception:
        pass

sys.excepthook = _handle_exception

def _qt_message_handler(mode, context, message):
    logging.error("Qt message (type=%s, file=%s, line=%s): %s",
                  mode, getattr(context, "file", None),
                  getattr(context, "line", None), message)

LIGHT_STYLE = """
QMainWindow, QWidget { background:#f4f6fb; color:#202534; font-family:'Microsoft YaHei UI'; font-size:13px; }
QFrame#Sidebar { background:#ffffff; border:1px solid #e2e6ef; border-radius:16px; }
QLabel#Brand { font-size:21px; font-weight:700; color:#202534; padding:8px 2px; }
QLabel#Muted { color:#788196; }
QPushButton { background:#ffffff; border:1px solid #d8deea; border-radius:9px; padding:9px 14px; color:#293246; }
QPushButton:hover { background:#edf1f8; }
QPushButton#Primary { background:#7667e8; border:0; font-weight:600; color:#ffffff; }
QPushButton#Primary:hover { background:#887af5; }
QLineEdit { background:#ffffff; border:1px solid #d8deea; border-radius:10px; padding:11px 14px; color:#202534; }
QListWidget { background:transparent; border:0; outline:0; }
QListWidget::item { padding:11px; border-radius:8px; }
QListWidget::item:selected { background:#e5e8fb; color:#28234f; }
QScrollArea { border:0; background:transparent; }
QScrollBar:vertical { background:#e9edf5; width:10px; margin:4px 2px; border-radius:5px; }
QScrollBar::handle:vertical { background:#c4ccda; min-height:34px; border-radius:5px; }
QScrollBar::handle:vertical:hover { background:#9faac0; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background:transparent; }
QMenu { background:#ffffff; color:#202534; border:1px solid #d8deea; padding:5px; }
QMenu::item { padding:7px 24px; border-radius:5px; }
QMenu::item:selected { background:#e9eaff; color:#28234f; }
QLineEdit:focus { border:1px solid #8174ed; }
QFrame#WallpaperCard { background:#ffffff; border:1px solid #e1e5ef; border-radius:14px; }
QFrame#WallpaperCard:hover { border:1px solid #8174ed; background:#f8f8ff; }
QFrame#WallpaperCard[portrait="true"] { background:transparent; border:1px solid transparent; }
QFrame#WallpaperCard[portrait="true"]:hover { background:transparent; border:1px solid transparent; }
QWidget#CardCoverHost { background:#e9edf5; border:1px solid #e1e5ef; border-radius:9px; padding:6px; }
QLabel#CardCover { background:#e9edf5; color:#788196; border-radius:8px; }
QLabel#CardCover[portrait="true"] { background:transparent; border:0px; }
QLabel#CardCategory { color:#788196; font-size:11px; }
QDialog { background:#f4f6fb; }
"""

DARK_STYLE = """
QMainWindow, QWidget { background:#11131a; color:#edf0f7; font-family:'Microsoft YaHei UI'; font-size:13px; }
QFrame#Sidebar { background:#171a23; border:1px solid #272b38; border-radius:16px; }
QLabel#Brand { font-size:21px; font-weight:700; color:#ffffff; padding:8px 2px; }
QLabel#Muted { color:#9299aa; }
QPushButton { background:#252a38; border:1px solid #343b4d; border-radius:9px; padding:9px 14px; color:#eef1f8; }
QPushButton:hover { background:#343c50; }
QPushButton#Primary { background:#7667e8; border:0; font-weight:600; }
QPushButton#Primary:hover { background:#887af5; }
QLineEdit { background:#1b1f2a; border:1px solid #303648; border-radius:10px; padding:11px 14px; color:#fff; }
QListWidget { background:transparent; border:0; outline:0; }
QListWidget::item { padding:11px; border-radius:8px; }
QListWidget::item:selected { background:#30334b; color:#fff; }
QScrollArea { border:0; background:transparent; }
QScrollBar:vertical { background:#171a23; width:10px; margin:4px 2px; border-radius:5px; }
QScrollBar::handle:vertical { background:#3a4153; min-height:34px; border-radius:5px; }
QScrollBar::handle:vertical:hover { background:#535d75; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background:transparent; }
QMenu { background:#1b1f2a; color:#edf0f7; border:1px solid #343b4d; padding:5px; }
QMenu::item { padding:7px 24px; border-radius:5px; }
QMenu::item:selected { background:#343c50; color:#ffffff; }
QLineEdit:focus { border:1px solid #8174ed; }
QFrame#WallpaperCard { background:#1a1e29; border:1px solid #2b3040; border-radius:14px; }
QFrame#WallpaperCard:hover { border:1px solid #8174ed; background:#202536; }
QFrame#WallpaperCard[portrait="true"] { background:transparent; border:1px solid transparent; }
QFrame#WallpaperCard[portrait="true"]:hover { background:transparent; border:1px solid transparent; }
QWidget#CardCoverHost { background:#0e1016; border:1px solid #2b3040; border-radius:9px; padding:6px; }
QLabel#CardCover { background:#0e1016; color:#9299aa; border-radius:8px; }
QLabel#CardCover[portrait="true"] { background:transparent; border:0px; }
QLabel#CardCategory { color:#9299aa; font-size:11px; }
QDialog { background:#101219; }
"""

def ensure_storage():
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    THUMB_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS wallpapers (
            id TEXT PRIMARY KEY, filename TEXT NOT NULL, title TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT '未分类', favorite INTEGER NOT NULL DEFAULT 0,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS categories (
            name TEXT PRIMARY KEY
        )""")
        columns = {row[1] for row in db.execute("PRAGMA table_info(wallpapers)")}
        if "source_path" not in columns:
            db.execute("ALTER TABLE wallpapers ADD COLUMN source_path TEXT")
        db.execute("""CREATE UNIQUE INDEX IF NOT EXISTS idx_wallpapers_source_path
                      ON wallpapers(source_path) WHERE source_path IS NOT NULL AND source_path != ''""")
        db.execute("""CREATE TABLE IF NOT EXISTS source_folders (
            path TEXT PRIMARY KEY,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        db.execute("INSERT OR IGNORE INTO categories(name) SELECT DISTINCT category FROM wallpapers WHERE category NOT IN ('', '未分类')")

class ChineseLineEdit(QLineEdit):
    """使用中文动作的输入框右键菜单，避免系统默认英文菜单。"""
    def contextMenuEvent(self, event):
        menu = QMenu(self)
        actions = [
            ("撤销", self.undo, self.isUndoAvailable()),
            ("重做", self.redo, self.isRedoAvailable()),
            (None, None, False),
            ("剪切", self.cut, self.hasSelectedText()),
            ("复制", self.copy, self.hasSelectedText()),
            ("粘贴", self.paste, self.isEnabled()),
            ("删除", lambda: self.insert(""), self.hasSelectedText()),
            (None, None, False),
            ("全选", self.selectAll, bool(self.text())),
        ]
        for label, callback, enabled in actions:
            if label is None:
                menu.addSeparator()
            else:
                action = menu.addAction(label)
                action.setEnabled(enabled)
                action.triggered.connect(callback)
        menu.exec(event.globalPos())

class PreviewLoadSignals(QObject):
    finished = Signal(object, object)


class PreviewLoadTask(QRunnable):
    """在后台线程按预览窗口尺寸解码图片，避免切换时阻塞界面。"""
    def __init__(self, cache_key, source_path):
        super().__init__()
        self.cache_key = cache_key
        self.source_path = str(source_path)
        self.signals = PreviewLoadSignals()

    def run(self):
        image = QImage()
        try:
            reader = QImageReader(self.source_path)
            reader.setAutoTransform(True)
            original = reader.size()
            target = QSize(self.cache_key[1], self.cache_key[2])
            if original.isValid():
                reader.setScaledSize(original.scaled(target, Qt.AspectRatioMode.KeepAspectRatio))
            image = reader.read()
        except (OSError, RuntimeError):
            logging.exception("Preview image load failed: %s", self.source_path)
        self.signals.finished.emit(self.cache_key, image)


class PreviewDialog(QDialog):
    def __init__(self, rows, start_index=0, parent=None):
        super().__init__(parent)
        self.rows = list(rows)
        self.current_index = max(0, min(start_index, len(self.rows) - 1))
        self._fullscreen = False
        self._preview_pool = QThreadPool(self)
        self._preview_pool.setMaxThreadCount(2)
        self._image_cache = OrderedDict()
        self._image_cache_limit = 6
        self._loading_keys = set()
        self._current_key = None
        self.setWindowTitle("图片预览")
        self.resize(1050, 720)
        self.setMinimumSize(560, 420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        self.image = QLabel()
        self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image.setStyleSheet("background:#08090d;border-radius:12px;")
        self.image.setMinimumSize(1, 1)
        self.image.installEventFilter(self)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        layout.addWidget(self.image, 1)

        toolbar = QHBoxLayout()
        self.prev_button = QPushButton("‹ 上一张")
        self.prev_button.clicked.connect(self.show_previous)
        toolbar.addWidget(self.prev_button)

        self.position_label = QLabel()
        self.position_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        toolbar.addWidget(self.position_label, 1)

        self.next_button = QPushButton("下一张 ›")
        self.next_button.clicked.connect(self.show_next)
        toolbar.addWidget(self.next_button)

        self.fullscreen_button = QPushButton("⛶ 全屏")
        self.fullscreen_button.clicked.connect(self.toggle_fullscreen)
        toolbar.addWidget(self.fullscreen_button)

        close = QPushButton("关闭")
        close.clicked.connect(self.accept)
        toolbar.addWidget(close)
        layout.addLayout(toolbar)

        self.shortcut_left = QShortcut(QKeySequence(Qt.Key.Key_Left), self)
        self.shortcut_left.activated.connect(self.show_previous)
        self.shortcut_right = QShortcut(QKeySequence(Qt.Key.Key_Right), self)
        self.shortcut_right.activated.connect(self.show_next)
        self.shortcut_escape = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        self.shortcut_escape.activated.connect(self._escape_fullscreen)

        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(90)
        self._resize_timer.timeout.connect(self.show_current)
        self.show_current()

    def _target_size(self):
        target = self.image.contentsRect().size()
        if target.width() < 100 or target.height() < 100:
            return QSize(1000, 620)
        return target

    def _cache_key(self, index, target):
        path = str(IMAGE_DIR / self.rows[index][1])
        return (path, target.width(), target.height())

    def _request_image(self, index, target):
        if not self.rows:
            return
        index %= len(self.rows)
        key = self._cache_key(index, target)
        if key in self._image_cache or key in self._loading_keys:
            return
        self._loading_keys.add(key)
        task = PreviewLoadTask(key, key[0])
        task.signals.finished.connect(self._on_image_loaded)
        self._preview_pool.start(task)

    def _on_image_loaded(self, key, image):
        self._loading_keys.discard(key)
        if image.isNull():
            if key == self._current_key:
                self.image.setPixmap(QPixmap())
                self.image.setText("无法读取这张图片")
            return
        self._image_cache[key] = image
        self._image_cache.move_to_end(key)
        while len(self._image_cache) > self._image_cache_limit:
            self._image_cache.popitem(last=False)
        if key == self._current_key:
            self.image.setText("")
            self.image.setPixmap(QPixmap.fromImage(image))

    def show_current(self):
        if not self.rows:
            return
        row = self.rows[self.current_index]
        self.setWindowTitle(row[2] or "图片预览")
        self.position_label.setText(f"{row[2]}    ·    {self.current_index + 1} / {len(self.rows)}")
        self.prev_button.setEnabled(len(self.rows) > 1)
        self.next_button.setEnabled(len(self.rows) > 1)

        target = self._target_size()
        self._current_key = self._cache_key(self.current_index, target)
        cached = self._image_cache.get(self._current_key)
        if cached is not None:
            self._image_cache.move_to_end(self._current_key)
            self.image.setText("")
            self.image.setPixmap(QPixmap.fromImage(cached))
        else:
            # 保留上一张已显示的画面，直到新图解码完成，避免切换时闪黑/白屏。
            current_pixmap = self.image.pixmap()
            if current_pixmap is None or current_pixmap.isNull():
                self.image.setText("正在加载图片…")
            self._request_image(self.current_index, target)

        # 预读相邻图片；切换时通常可直接命中内存缓存。
        if len(self.rows) > 1:
            self._request_image(self.current_index - 1, target)
            self._request_image(self.current_index + 1, target)

    def eventFilter(self, watched, event):
        if watched is self.image and event.type() == QEvent.Type.Wheel:
            delta = event.angleDelta().y()
            if delta > 0:
                self.show_previous()
                event.accept()
                return True
            if delta < 0:
                self.show_next()
                event.accept()
                return True
        return super().eventFilter(watched, event)

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if delta > 0:
            self.show_previous()
            event.accept()
            return
        if delta < 0:
            self.show_next()
            event.accept()
            return
        super().wheelEvent(event)

    def show_previous(self):
        if len(self.rows) > 1:
            self.current_index = (self.current_index - 1) % len(self.rows)
            self.show_current()

    def show_next(self):
        if len(self.rows) > 1:
            self.current_index = (self.current_index + 1) % len(self.rows)
            self.show_current()

    def toggle_fullscreen(self):
        if self._fullscreen:
            self.showNormal()
            self._fullscreen = False
            self.fullscreen_button.setText("⛶ 全屏")
        else:
            self.showFullScreen()
            self._fullscreen = True
            self.fullscreen_button.setText("退出全屏")
        self.show_current()

    def _escape_fullscreen(self):
        if self._fullscreen:
            self.showNormal()
            self._fullscreen = False
            self.fullscreen_button.setText("⛶ 全屏")
            self.show_current()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._resize_timer.start()


class SmoothScrollArea(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._scroll_animation = QPropertyAnimation(self.verticalScrollBar(), b"value", self)
        self._scroll_animation.setDuration(180)
        self._scroll_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

    def wheelEvent(self, event):
        # Smooth scrolling
        delta = event.angleDelta().y()
        if delta == 0:
            return super().wheelEvent(event)
        steps = delta / 120.0
        bar = self.verticalScrollBar()
        self._scroll_animation.stop()
        self._scroll_animation.setStartValue(bar.value())
        self._scroll_animation.setEndValue(int(bar.value() - steps * 120))
        self._scroll_animation.start()
        event.accept()

class ThumbnailSignals(QObject):
    finished = Signal(int, int, str)

class ThumbnailTask(QRunnable):
    """在线程池中读取并生成缩略图，避免翻页时阻塞界面线程。"""
    def __init__(self, generation, index, source_path):
        super().__init__()
        self.generation = generation
        self.index = index
        self.source_path = str(source_path)
        self.signals = ThumbnailSignals()

    def run(self):
        source = Path(self.source_path)
        result_path = str(source)
        try:
            stat = source.stat()
            cache_name = f"{source.stem}_{stat.st_mtime_ns}_{stat.st_size}.jpg"
            cached = THUMB_DIR / cache_name
            if cached.exists():
                result_path = str(cached)
            else:
                reader = QImageReader(str(source))
                reader.setAutoTransform(True)
                original = reader.size()
                if original.isValid():
                    scaled = original.scaled(QSize(480, 300), Qt.AspectRatioMode.KeepAspectRatio)
                    reader.setScaledSize(scaled)
                image = reader.read()
                if not image.isNull() and image.save(str(cached), "JPG", 88):
                    result_path = str(cached)
        except (OSError, RuntimeError):
            logging.exception("Thumbnail generation failed: %s", source)
        self.signals.finished.emit(self.generation, self.index, result_path)


class WallpaperCard(QFrame):
    def __init__(self, row, image_path, on_open, on_favorite, on_delete, on_rename, on_category, on_wallpaper, categories, parent=None):
        super().__init__(parent)
        self.setObjectName("WallpaperCard")
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(0)
        self.row = row
        self.image_path = str(image_path)
        self._on_open = on_open
        self._on_favorite = on_favorite
        self._on_delete = on_delete
        self._on_rename = on_rename
        self._on_category = on_category
        self._on_wallpaper = on_wallpaper
        self._categories = list(categories)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 6)
        layout.setSpacing(4)
        self.card_layout = layout
        self.cover_host = QWidget(self)
        self.cover_host.setObjectName("CardCoverHost")
        self.cover_host.setFixedHeight(240)
        self.cover_layout = QHBoxLayout(self.cover_host)
        self.cover_layout.setContentsMargins(8, 8, 8, 8)
        self.cover_layout.setSpacing(0)
        self.cover = QLabel(self.cover_host)
        self.cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover.setFixedHeight(222)
        self.cover.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.cover.setObjectName("CardCover")
        self._portrait_layout = None
        self.cover.setText("正在加载预览…")
        self.cover.mousePressEvent = lambda event: self._on_open(self.row)
        self.cover_layout.addWidget(self.cover)
        layout.addWidget(self.cover_host)
        self.title_label = QLabel()
        self.title_label.setObjectName("CardTitle")
        self.title_label.setStyleSheet("font-weight:600;padding:1px 2px;")
        self.title_label.setWordWrap(False)
        layout.addWidget(self.title_label)
        bottom = QHBoxLayout()
        self.category_label = QLabel()
        self.category_label.setObjectName("CardCategory")
        bottom.addWidget(self.category_label)
        bottom.addStretch()
        self.favorite_button = QPushButton()
        self.favorite_button.setFixedWidth(35)
        self.favorite_button.clicked.connect(self._toggle_favorite)
        bottom.addWidget(self.favorite_button)
        self.more_button = QPushButton("···")
        self.more_button.setFixedWidth(38)
        self.more_button.clicked.connect(self._show_current_menu)
        bottom.addWidget(self.more_button)
        layout.addLayout(bottom)
        self.update_row(row, categories)

    def _toggle_favorite(self):
        self._on_favorite(self.row[0], self.row[4])

    def _show_current_menu(self):
        self.show_menu(self.more_button, self._on_delete, self._on_rename,
                       self._on_category, self._on_wallpaper, self._categories)

    def update_row(self, row, categories):
        changed_image = self.row[1] != row[1]
        self.row = row
        self._categories = list(categories)
        self.title_label.setText(row[2])
        self.category_label.setText(row[3])
        self.favorite_button.setText("♥" if row[4] else "♡")
        if changed_image:
            self.image_path = str(IMAGE_DIR / row[1])
            self._portrait_layout = None
            self.cover.setPixmap(QPixmap())
            self.cover.setText("正在加载预览…")
            source_size = QImageReader(self.image_path).size()
            if source_size.isValid():
                self._set_portrait_layout(source_size.height() > source_size.width(), source_size)

    def _set_portrait_layout(self, is_portrait, image_size=None):
        # Windows 资源管理器式统一缩略图画布：所有卡片预览区域等大，
        # 图片按原始比例完整显示并居中，竖图两侧自然留白，不裁切不拉伸。
        self._portrait_layout = is_portrait
        for widget in (self, self.cover_host, self.cover):
            widget.setProperty("portrait", False)
            widget.style().unpolish(widget)
            widget.style().polish(widget)
        self.cover_host.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.cover_host.setFixedHeight(240)
        self.cover_host.setMinimumWidth(0)
        self.cover_host.setMaximumWidth(16777215)
        self.cover_layout.setContentsMargins(8, 8, 8, 8)
        self.cover_layout.setAlignment(self.cover, Qt.AlignmentFlag.AlignCenter)
        self.cover.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.cover.setMinimumWidth(0)
        self.cover.setMaximumWidth(16777215)
        self.cover.setFixedHeight(222)
        self.card_layout.setAlignment(self.cover_host, Qt.Alignment())

    def load_thumbnail(self):
        cache_key = self.image_path
        pix = PIXMAP_CACHE.get(cache_key)
        if pix is None:
            pix = QPixmap(cache_key)
            if pix.isNull():
                return
            PIXMAP_CACHE[cache_key] = pix
            PIXMAP_CACHE.move_to_end(cache_key)
            while len(PIXMAP_CACHE) > PIXMAP_CACHE_LIMIT:
                PIXMAP_CACHE.popitem(last=False)
        else:
            PIXMAP_CACHE.move_to_end(cache_key)
        # 卡片创建时已根据原图尺寸确定布局。只有方向确实发生变化时才重排，
        # 避免每次缩略图加载/点击后都触发 Qt 样式重算，造成预览区域短暂缩小。
        is_portrait = pix.height() > pix.width()
        if self._portrait_layout is None or self._portrait_layout != is_portrait:
            self._set_portrait_layout(is_portrait, pix.size())
        self.cover.setText("")
        target_size = self.cover.contentsRect().size()
        if target_size.width() < 2 or target_size.height() < 2:
            target_size = QSize(268, 240)
        self.cover.setScaledContents(False)
        self.cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover.setPixmap(pix.scaled(
            target_size, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        ))

    def show_menu(self, button, on_delete, on_rename, on_category, on_wallpaper, categories):
        menu = QMenu(self)
        rename = menu.addAction("重命名")
        category_menu = menu.addMenu("移动到分类")
        category_actions = {}
        for name in categories:
            category_actions[category_menu.addAction(name)] = name
        category_actions[category_menu.addAction("未分类")] = "未分类"
        menu.addSeparator()
        wallpaper = menu.addAction("设为桌面壁纸")
        delete = menu.addAction("删除图片")
        chosen = menu.exec(button.mapToGlobal(button.rect().bottomLeft()))
        if chosen == rename:
            on_rename(self.row[0], self.row[2])
        elif chosen in category_actions:
            on_category(self.row[0], category_actions[chosen])
        elif chosen == wallpaper:
            on_wallpaper(self.row[1])
        elif chosen == delete:
            on_delete(self.row[0])

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1280, 820)
        self.setAcceptDrops(True)
        self.current_category = "横屏壁纸"
        self.show_favorites = False
        self.settings = QSettings("Huanjing", "WallpaperGallery")
        saved_theme = self.settings.value("theme", "dark")
        self.set_theme(saved_theme)
        self.search = ChineseLineEdit()
        self.search.setPlaceholderText("搜索标题或分类…")
        self.search.textChanged.connect(self.refresh)
        self.current_page = 0
        # 缩略图后台任务状态必须在首次 refresh() 前初始化。
        # refresh() 会立即递增 generation 并提交 ThumbnailTask。
        self._thumbnail_generation = 0
        self._thumbnail_jobs = {}
        self._thumbnail_pool = QThreadPool.globalInstance()
        self._thumbnail_pool.setMaxThreadCount(max(2, min(4, QThreadPool.globalInstance().maxThreadCount())))
        self.page_size = max(1, min(40, int(self.settings.value("page_size", 4))))
        self._build_ui()
        self._thumbnail_timer = QTimer(self)
        self._thumbnail_timer.setSingleShot(True)
        self._thumbnail_timer.setInterval(120)
        self._thumbnail_timer.timeout.connect(self.load_visible_thumbnails)
        self._virtual_row_height = 250
        self._virtual_overscan_rows = 1
        self.scroll.verticalScrollBar().valueChanged.connect(self.schedule_visible_thumbnails)
        self.refresh()

    def set_theme(self, mode):
        self.theme = mode if mode in ("light", "dark") else "dark"
        self.settings.setValue("theme", self.theme)
        self._style = LIGHT_STYLE if self.theme == "light" else DARK_STYLE
        self.setStyleSheet(self._style)
        self._update_theme_button()

    def _update_theme_button(self):
        button = getattr(self, "theme_button", None)
        if button is None:
            return
        if self.theme == "dark":
            button.setText("☀ 浅色模式")
            button.setToolTip("切换到浅色主题")
        else:
            button.setText("🌙 深色模式")
            button.setToolTip("切换到深色主题")

    def toggle_theme(self):
        self.set_theme("light" if self.theme == "dark" else "dark")

    def _build_ui(self):
        # 主体布局：左侧分类栏 + 右侧内容区
        root = QWidget()
        outer = QHBoxLayout(root)
        outer.setContentsMargins(18, 18, 18, 18)
        outer.setSpacing(18)

        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(16, 16, 16, 16)
        side.setSpacing(12)
        brand = QLabel("✦ 幻境壁纸馆")
        brand.setObjectName("Brand")
        side.addWidget(brand)
        side.addWidget(QLabel("图片空间", objectName="Muted"))
        self.categories = QListWidget()
        self.categories.setMinimumWidth(200)
        self.categories.currentTextChanged.connect(self.change_category)
        side.addWidget(self.categories, 1)
        side.addWidget(QLabel("自定义分类", objectName="Muted"))
        add_cat = QPushButton("+ 新建分类")
        add_cat.clicked.connect(self.add_category)
        side.addWidget(add_cat)
        note = QLabel("图片仅保存在本机\n不会自动上传网络")
        note.setObjectName("Muted")
        note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        side.addWidget(note)
        side.addStretch()

        content = QVBoxLayout()
        header = QHBoxLayout()
        header.setSpacing(12)
        self.search.setMinimumHeight(42)
        header.addWidget(self.search, 1)
        self.theme_button = QPushButton()
        self.theme_button.clicked.connect(self.toggle_theme)
        self._update_theme_button()
        header.addWidget(self.theme_button)
        content.addLayout(header)

        title_wrap = QVBoxLayout()
        title = QLabel("我的壁纸")
        title.setStyleSheet("font-size:28px;font-weight:700;")
        self.count_label = QLabel("收藏每一份喜欢的画面 · 也可以把图片直接拖进窗口")
        self.count_label.setObjectName("Muted")
        title_wrap.addWidget(title)
        title_wrap.addWidget(self.count_label)
        content.addLayout(title_wrap)

        controls = QHBoxLayout()
        controls.setSpacing(10)
        import_btn = QPushButton("＋ 导入图片")
        import_btn.setObjectName("Primary")
        import_btn.clicked.connect(self.import_images)
        controls.addWidget(import_btn)
        folder_btn = QPushButton("导入文件夹")
        folder_btn.clicked.connect(self.import_folder)
        controls.addWidget(folder_btn)
        self.refresh_folders_btn = QPushButton("↻ 刷新文件夹")
        self.refresh_folders_btn.clicked.connect(self.refresh_folders)
        controls.addWidget(self.refresh_folders_btn)
        self.delete_folder_btn = QPushButton("删除文件夹壁纸")
        self.delete_folder_btn.clicked.connect(self.delete_folder_wallpapers)
        controls.addWidget(self.delete_folder_btn)
        controls.addStretch()
        content.addLayout(controls)

        # 分页工具栏：默认每页 4 张，支持调整每页容量。
        pagination = QHBoxLayout()
        pagination.addStretch()
        pagination.addWidget(QLabel("每页显示"))
        self.page_size_spin = QSpinBox()
        self.page_size_spin.setRange(1, 40)
        self.page_size_spin.setValue(self.page_size)
        self.page_size_spin.setSuffix(" 张")
        self.page_size_spin.setFixedWidth(86)
        self.page_size_spin.valueChanged.connect(self.change_page_size)
        pagination.addWidget(self.page_size_spin)
        self.prev_page_btn = QPushButton("‹ 上一页")
        self.prev_page_btn.clicked.connect(lambda: self.change_page(-1))
        pagination.addWidget(self.prev_page_btn)
        self.page_label = QLabel("第 1 / 1 页")
        self.page_label.setMinimumWidth(100)
        self.page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pagination.addWidget(self.page_label)
        self.next_page_btn = QPushButton("下一页 ›")
        self.next_page_btn.clicked.connect(lambda: self.change_page(1))
        pagination.addWidget(self.next_page_btn)
        pagination.addStretch()

        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setContentsMargins(0, 8, 0, 8)
        self.grid.setHorizontalSpacing(14)
        self.grid.setVerticalSpacing(8)
        self.scroll = SmoothScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # 始终预留垂直滚动条槽位，分类/分页后内容高度变化时视口宽度不会跳变。
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.scroll.verticalScrollBar().setSingleStep(18)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.grid_host.setMinimumWidth(0)
        self.scroll.setWidget(self.grid_host)
        self.scroll.viewport().installEventFilter(self)
        self._wallpaper_cards = OrderedDict()
        self._card_row_height = 250
        content.addWidget(self.scroll, 1)
        # 分页控件固定在内容区底部，不再占用缩略图上方空间。
        content.addLayout(pagination)
        outer.addWidget(sidebar)
        outer.addLayout(content, 1)
        self.setCentralWidget(root)

    def rows(self):
        with sqlite3.connect(DB_PATH) as db:
            return db.execute("SELECT id,filename,title,category,favorite FROM wallpapers ORDER BY added_at DESC").fetchall()

    def refresh(self, *_):
        # 保留已创建的卡片对象：刷新只调整网格位置，不销毁/重建控件。
        self.grid_host.setUpdatesEnabled(False)
        self._thumbnail_generation += 1
        generation = self._thumbnail_generation
        QToolTip.hideText()
        for card in self._wallpaper_cards.values():
            self.grid.removeWidget(card)
            card.hide()

        query = self.search.text().strip().lower()
        rows = self.rows()
        filtered = []
        for row in rows:
            if self.show_favorites and not row[4]:
                continue
            if self.current_category in ("横屏壁纸", "竖屏壁纸"):
                reader = QImageReader(str(IMAGE_DIR / row[1]))
                image_size = reader.size()
                if not image_size.isValid():
                    continue
                is_landscape = image_size.width() > image_size.height()
                if self.current_category == "横屏壁纸" and not is_landscape:
                    continue
                if self.current_category == "竖屏壁纸" and is_landscape:
                    continue
            elif self.current_category not in ("全部壁纸", "我的收藏") and row[3] != self.current_category:
                continue
            if self.current_category == "未分类" and row[3] != "未分类":
                continue
            if query and query not in row[2].lower() and query not in row[3].lower():
                continue
            filtered.append(row)

        self.visible_rows = filtered
        total_pages = max(1, (len(filtered) + self.page_size - 1) // self.page_size)
        self.current_page = max(0, min(self.current_page, total_pages - 1))
        page_start = self.current_page * self.page_size
        self.page_rows = filtered[page_start:page_start + self.page_size]
        self._virtual_row_count = (len(self.page_rows) + 1) // 2
        self.page_label.setText(f"第 {self.current_page + 1} / {total_pages} 页")
        self.prev_page_btn.setEnabled(self.current_page > 0)
        self.next_page_btn.setEnabled(self.current_page + 1 < total_pages)
        self.count_label.setText(f"共 {len(filtered)} 张壁纸  ·  当前第 {self.current_page + 1} 页")

        self.grid_columns = 2
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        for column in range(self.grid_columns):
            # 两列始终参与布局计算；即使某页只有一张图，也保留另一列的空间。
            self.grid.setColumnMinimumWidth(column, 0)
            self.grid.setColumnStretch(column, 1)
        self._card_categories = self.category_names()

        # 在创建/放入网格前先固定画布宽度和卡片宽度，避免显示后再二次缩放。
        viewport_width = max(1, self.scroll.viewport().width())
        self.grid_host.setFixedWidth(viewport_width)
        card_width = self._card_column_width()
        active_ids = set()
        for index, row in enumerate(self.page_rows):
            uid = row[0]
            active_ids.add(uid)
            card = self._wallpaper_cards.get(uid)
            if card is None:
                card = WallpaperCard(
                    row, IMAGE_DIR / row[1], self.open_preview, self.toggle_favorite,
                    self.delete_image, self.rename_image, self.move_category,
                    self.set_wallpaper, self._card_categories,
                    parent=self.grid_host
                )
                self._wallpaper_cards[uid] = card
            else:
                card.update_row(row, self._card_categories)
            card.setFixedSize(card_width, card.sizeHint().height())
            card.show()
            self.grid.addWidget(card, index // self.grid_columns, index % self.grid_columns)

            # 缩略图缓存命中时直接使用；否则异步生成并更新对应卡片。
            cached_path = self.thumbnail_for(row[1])
            if cached_path.exists():
                card.image_path = str(cached_path)
                card.load_thumbnail()
            else:
                task = ThumbnailTask(generation, index, IMAGE_DIR / row[1])
                task.signals.finished.connect(self._on_thumbnail_ready)
                self._thumbnail_jobs[(generation, index)] = task
                self._thumbnail_pool.start(task)

        # 限制隐藏卡片缓存规模，避免大型图库长期保留过多 QWidget。
        while len(self._wallpaper_cards) > 120:
            oldest_uid = next(iter(self._wallpaper_cards))
            if oldest_uid in active_ids:
                self._wallpaper_cards.move_to_end(oldest_uid)
                continue
            old_card = self._wallpaper_cards.pop(oldest_uid)
            self.grid.removeWidget(old_card)
            old_card.deleteLater()

        self._refresh_categories(rows)
        self.scroll.verticalScrollBar().setValue(0)
        self.grid_host.setUpdatesEnabled(True)
        self.grid_host.update()
        QTimer.singleShot(0, self._apply_card_column_widths)

    def _card_column_width(self):
        # 以滚动视口为唯一宽度基准，确保翻页/筛选后列宽不受内容 sizeHint 影响。
        margins = self.grid.contentsMargins()
        available = max(1, self.scroll.viewport().width())
        spacing = self.grid.horizontalSpacing()
        return max(1, (available - margins.left() - margins.right() - spacing) // 2)

    def _apply_card_column_widths(self):
        if not hasattr(self, "grid") or not hasattr(self, "scroll"):
            return
        viewport_width = max(1, self.scroll.viewport().width())
        # 内容画布始终与 viewport 等宽，避免 QScrollArea 按当前页内容重新估算宽度。
        self.grid_host.setFixedWidth(viewport_width)
        card_width = self._card_column_width()
        for column in range(2):
            self.grid.setColumnMinimumWidth(column, card_width)
            self.grid.setColumnStretch(column, 0)
        for card in self._wallpaper_cards.values():
            if card.isVisible():
                card.setFixedSize(card_width, card.sizeHint().height())

    def eventFilter(self, watched, event):
        if watched is getattr(self, "scroll", None).viewport() if hasattr(self, "scroll") else False:
            if event.type() == QEvent.Type.Resize:
                QTimer.singleShot(0, self._apply_card_column_widths)
        return super().eventFilter(watched, event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "grid"):
            QTimer.singleShot(0, self._apply_card_column_widths)

    def _on_thumbnail_ready(self, generation, index, image_path):
        self._thumbnail_jobs.pop((generation, index), None)
        # 只更新当前页对应卡片，翻页后返回的旧任务结果不会污染新页面。
        if generation != self._thumbnail_generation:
            return
        card = self._wallpaper_cards.get(index)
        if card is None:
            return
        card.image_path = image_path
        card.load_thumbnail()

    def change_page(self, offset):
        total_pages = max(1, (len(self.visible_rows) + self.page_size - 1) // self.page_size)
        new_page = max(0, min(total_pages - 1, self.current_page + offset))
        if new_page != self.current_page:
            # 翻页时显式关闭已显示的 Qt tooltip，避免鼠标停留导致悬浮窗重复出现。
            QToolTip.hideText()
            self.current_page = new_page
            self.refresh()

    def change_page_size(self, value):
        self.page_size = max(1, min(40, int(value)))
        self.current_page = 0
        self.settings.setValue("page_size", self.page_size)
        self.refresh()

    def schedule_visible_thumbnails(self, *_):
        # 页面最多显示 40 张，全部卡片已在 refresh() 中创建并后台生成缩略图。
        # 不再因滚动而销毁/重建卡片，避免重建时行高变化引发页面抖动。
        return

    def load_visible_thumbnails(self):
        # 保留方法名以兼容现有定时器连接；当前页卡片一次性创建，
        # 缩略图由 ThumbnailTask 异步加载，无需滚动时回收控件。
        return

    def _refresh_categories(self, rows=None):
        # 系统分类必须始终显示；数据库中只保存自定义分类，不能只展示数据库内容。
        system_names = ["全部壁纸", "横屏壁纸", "竖屏壁纸", "未分类", "我的收藏"]
        with sqlite3.connect(DB_PATH) as db:
            saved = {r[0] for r in db.execute("SELECT name FROM categories").fetchall()}
        custom = {
            r[3] for r in (rows if rows is not None else self.rows())
            if r[3] not in ("", "未分类") and r[3] not in system_names
        }
        names = system_names + sorted((saved | custom) - set(system_names))
        current = self.current_category
        selected = self.categories.currentItem().text() if self.categories.currentItem() else None
        if selected in names:
            current = selected
        if current not in names:
            current = "全部壁纸"
        self.categories.blockSignals(True)
        self.categories.clear()
        self.categories.addItems(names)
        matches = self.categories.findItems(current, Qt.MatchFlag.MatchExactly)
        if matches:
            self.categories.setCurrentItem(matches[0])
        self.categories.blockSignals(False)
        self.current_category = current
        self.show_favorites = current == "我的收藏"

    def change_category(self, name):
        if not name:
            return
        self.current_category = name
        self.show_favorites = name == "我的收藏"
        self.refresh()

    def add_category(self):
        name, ok = QInputDialog.getText(self, "新建分类", "分类名称：")
        name = name.strip()
        if not ok or not name:
            return
        if name in ("全部壁纸", "我的收藏", "未分类"):
            QMessageBox.information(self, "分类名称", "这个名称是系统分类，请换一个名称。")
            return
        with sqlite3.connect(DB_PATH) as db:
            try:
                db.execute("INSERT INTO categories(name) VALUES(?)", (name,))
            except sqlite3.IntegrityError:
                QMessageBox.information(self, "分类已存在", "这个分类已经存在。")
                return
        self.show_favorites = False
        self.current_category = name
        self.refresh()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and any(url.isLocalFile() for url in event.mimeData().urls()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        self._import_paths(paths)
        event.acceptProposedAction()

    def import_images(self):
        files, _ = QFileDialog.getOpenFileNames(self, "选择图片", str(Path.home()),
                                                "图片文件 (*.jpg *.jpeg *.png *.webp *.bmp *.gif)")
        self._import_paths(files)

    def import_folder(self):
        # 使用 Qt 自绘目录选择器，避开 Windows 原生目录对话框偶发的空白闪窗。
        dialog = QFileDialog(self, "选择图片文件夹", str(Path.home()))
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        dialog.setFileMode(QFileDialog.FileMode.Directory)
        dialog.setOption(QFileDialog.Option.ShowDirsOnly, True)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            selected = dialog.selectedFiles()
            if not selected:
                return
            folder_path = str(Path(selected[0]).resolve())
            with sqlite3.connect(DB_PATH) as db:
                db.execute("INSERT OR IGNORE INTO source_folders(path) VALUES(?)", (folder_path,))
            self._import_paths([folder_path])

    def thumbnail_for(self, filename):
        source = IMAGE_DIR / filename
        try:
            stat = source.stat()
            cache_name = f"{source.stem}_{stat.st_mtime_ns}_{stat.st_size}.jpg"
            cached = THUMB_DIR / cache_name
            if cached.exists():
                return cached
            reader = QImageReader(str(source))
            reader.setAutoTransform(True)
            original = reader.size()
            if original.isValid():
                reader.setScaledSize(original.scaled(QSize(360, 220), Qt.AspectRatioMode.KeepAspectRatio))
            image = reader.read()
            if image.isNull():
                return source
            pixmap = QPixmap.fromImage(image)
            if pixmap.save(str(cached), "JPG", 88):
                return cached
        except (OSError, RuntimeError):
            pass
        return source

    def refresh_folders(self):
        with sqlite3.connect(DB_PATH) as db:
            folders = [row[0] for row in db.execute(
                "SELECT path FROM source_folders ORDER BY added_at, path"
            ).fetchall()]
        if not folders:
            QMessageBox.information(self, "刷新文件夹", "还没有记录导入过的文件夹。请先点击“导入文件夹”选择一次。")
            return
        existing = [path for path in folders if Path(path).is_dir()]
        missing = [path for path in folders if not Path(path).is_dir()]
        if not existing:
            QMessageBox.warning(self, "刷新文件夹", "之前导入的文件夹都找不到了，请重新选择文件夹导入。")
            return
        self._import_paths(existing, show_result=False)
        if missing:
            QMessageBox.warning(self, "部分文件夹无法访问",
                                "以下文件夹不存在或无法访问：\\n" + "\\n".join(missing[:5]))
        self.statusBar().showMessage("文件夹扫描完成", 5000)

    def delete_folder_wallpapers(self):
        with sqlite3.connect(DB_PATH) as db:
            folders = [Path(row[0]).resolve() for row in db.execute(
                "SELECT path FROM source_folders"
            ).fetchall()]
            rows = db.execute(
                "SELECT id, filename, source_path FROM wallpapers WHERE source_path IS NOT NULL AND source_path != ''"
            ).fetchall()
            targets = []
            for uid, filename, source_path in rows:
                try:
                    source = Path(source_path).resolve()
                    if any(source == folder or folder in source.parents for folder in folders):
                        targets.append((uid, filename))
                except (OSError, RuntimeError):
                    continue
            if not targets:
                QMessageBox.information(self, "删除文件夹壁纸", "没有找到通过已导入文件夹添加的壁纸。")
                return
            answer = QMessageBox.question(
                self, "删除文件夹壁纸",
                f"确定从壁纸馆移除这 {len(targets)} 张文件夹导入的壁纸吗？\\n原文件夹中的图片不会被删除。",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            db.executemany("DELETE FROM wallpapers WHERE id=?", [(uid,) for uid, _ in targets])
        for _, filename in targets:
            (IMAGE_DIR / filename).unlink(missing_ok=True)
            for cached in THUMB_DIR.glob(f"{Path(filename).stem}_*.jpg"):
                cached.unlink(missing_ok=True)
        self.current_page = 0
        self.refresh()
        self.statusBar().showMessage(f"已从壁纸馆移除 {len(targets)} 张图片；原文件未改动", 5000)

    def _import_paths(self, files, show_result=True):
        candidates = []
        seen = set()
        for item in files:
            path = Path(item)
            try:
                if path.is_dir():
                    candidates.extend(p for p in path.rglob("*") if p.is_file())
                elif path.is_file():
                    candidates.append(path)
            except OSError:
                continue
        added = skipped = 0
        errors = []
        with sqlite3.connect(DB_PATH) as db:
            for src in candidates:
                if src.suffix.lower() not in SUPPORTED:
                    continue
                try:
                    resolved = str(src.resolve())
                    if resolved in seen or IMAGE_DIR.resolve() in Path(resolved).parents:
                        continue
                    seen.add(resolved)
                    if db.execute("SELECT 1 FROM wallpapers WHERE source_path=?", (resolved,)).fetchone():
                        skipped += 1
                        continue
                    uid = uuid.uuid4().hex
                    filename = uid + src.suffix.lower()
                    shutil.copy2(src, IMAGE_DIR / filename)
                    db.execute(
                        "INSERT INTO wallpapers(id,filename,title,source_path) VALUES(?,?,?,?)",
                        (uid, filename, src.stem, resolved)
                    )
                    added += 1
                except (OSError, sqlite3.Error) as exc:
                    errors.append(f"{src.name}: {exc}")
        self.current_page = 0
        self.refresh()
        if added:
            self.statusBar().showMessage(f"新增导入 {added} 张图片", 5000)
        elif show_result:
            self.statusBar().showMessage(f"没有发现新图片（已跳过 {skipped} 张重复图片）", 5000)
        if errors:
            preview = "\\n".join(errors[:8])
            if len(errors) > 8:
                preview += f"\\n另有 {len(errors) - 8} 个文件导入失败。"
            QMessageBox.warning(self, "部分文件导入失败", preview)

    def open_preview(self, row):
        rows = getattr(self, "visible_rows", [])
        try:
            index = next(i for i, item in enumerate(rows) if item[0] == row[0])
        except StopIteration:
            rows, index = [row], 0
        saved_page = self.current_page
        saved_scroll = self.scroll.verticalScrollBar().value()
        dialog = PreviewDialog(rows, index, self)
        dialog.exec()
        self.current_page = saved_page
        QTimer.singleShot(0, lambda value=saved_scroll: self.scroll.verticalScrollBar().setValue(value))

    def toggle_favorite(self, uid, value):
        with sqlite3.connect(DB_PATH) as db:
            db.execute("UPDATE wallpapers SET favorite=? WHERE id=?", (0 if value else 1, uid))
        self.refresh()

    def category_names(self):
        with sqlite3.connect(DB_PATH) as db:
            saved = {r[0] for r in db.execute("SELECT name FROM categories").fetchall()}
        return sorted(saved | {r[3] for r in self.rows() if r[3] not in ("未分类", "")})

    def rename_image(self, uid, old_title):
        title, ok = QInputDialog.getText(self, "重命名壁纸", "新名称：", text=old_title)
        title = title.strip()
        if ok and title:
            with sqlite3.connect(DB_PATH) as db:
                db.execute("UPDATE wallpapers SET title=? WHERE id=?", (title, uid))
            self.refresh()

    def move_category(self, uid, category):
        with sqlite3.connect(DB_PATH) as db:
            db.execute("UPDATE wallpapers SET category=? WHERE id=?", (category, uid))
        self.refresh()

    def set_wallpaper(self, filename):
        if sys.platform != "win32":
            QMessageBox.information(self, "设置壁纸", "一键设置桌面壁纸目前仅支持 Windows。")
            return
        image_path = str(IMAGE_DIR / filename)
        try:
            api = ctypes.windll.user32.SystemParametersInfoW
            api.argtypes = [ctypes.c_uint, ctypes.c_uint, ctypes.c_wchar_p, ctypes.c_uint]
            api.restype = ctypes.c_bool
            if api(20, 0, image_path, 0x01 | 0x02):
                self.statusBar().showMessage("桌面壁纸设置成功", 4000)
            else:
                raise OSError("Windows 未能应用这张图片")
        except Exception as exc:
            QMessageBox.warning(self, "设置失败", str(exc))

    def delete_image(self, uid):
        answer = QMessageBox.question(
            self, "删除壁纸", "确定从壁纸馆删除这张图片吗？\\n原始导入文件不会被删除。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        with sqlite3.connect(DB_PATH) as db:
            row = db.execute("SELECT filename FROM wallpapers WHERE id=?", (uid,)).fetchone()
            db.execute("DELETE FROM wallpapers WHERE id=?", (uid,))
        if row:
            (IMAGE_DIR / row[0]).unlink(missing_ok=True)
            for cached in THUMB_DIR.glob(f"{Path(row[0]).stem}_*.jpg"):
                cached.unlink(missing_ok=True)
        self.refresh()
