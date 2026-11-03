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

from PySide6.QtCore import Qt, QSize, QEvent, QSettings, QPoint, QRect, QTimer, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QPixmap, QShortcut, QKeySequence, QImageReader
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFileDialog, QLineEdit, QListWidget, QListWidgetItem,
    QScrollArea, QGridLayout, QFrame, QMessageBox, QDialog, QInputDialog,
    QMenu, QSizePolicy
)

APP_NAME = "幻境壁纸馆"
DATA_DIR = Path.home() / "Pictures" / "HuanjingWallpaperGallery"
IMAGE_DIR = DATA_DIR / "images"
THUMB_DIR = DATA_DIR / "thumbnails"
DB_PATH = DATA_DIR / "gallery.db"
SUPPORTED = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}
PIXMAP_CACHE = OrderedDict()
PIXMAP_CACHE_LIMIT = 64  # Bound decoded thumbnail memory

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
QLabel#CardCover { background:#e9edf5; color:#788196; border-radius:9px; }
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
QLabel#CardCover { background:#0e1016; color:#9299aa; border-radius:9px; }
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

class PreviewDialog(QDialog):
    def __init__(self, rows, start_index=0, parent=None):
        super().__init__(parent)
        self.rows = list(rows)
        self.current_index = max(0, min(start_index, len(self.rows) - 1))
        self._fullscreen = False
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

        self.show_current()

    def show_current(self):
        if not self.rows:
            return
        row = self.rows[self.current_index]
        path = IMAGE_DIR / row[1]
        self.setWindowTitle(row[2] or "图片预览")
        self.position_label.setText(
            f"{row[2]}    ·    {self.current_index + 1} / {len(self.rows)}"
        )
        self.prev_button.setEnabled(len(self.rows) > 1)
        self.next_button.setEnabled(len(self.rows) > 1)

        target = self.image.size()
        if target.width() < 100 or target.height() < 100:
            target = QSize(1000, 620)
        reader = QImageReader(str(path))
        reader.setAutoTransform(True)
        original = reader.size()
        if original.isValid():
            reader.setScaledSize(original.scaled(
                target, Qt.AspectRatioMode.KeepAspectRatio
            ))
        image = reader.read()
        if image.isNull():
            self.image.setText("无法读取这张图片")
            self.image.setPixmap(QPixmap())
        else:
            self.image.setText("")
            self.image.setPixmap(QPixmap.fromImage(image))

    def eventFilter(self, watched, event):
        # 在图片区域滚动鼠标滚轮即可切换上一张/下一张。
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
        # 鼠标滚轮位于预览窗口其他空白区域时同样可以切换。
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
        if hasattr(self, "image") and hasattr(self, "position_label"):
            self.show_current()

class SmoothScrollArea(QScrollArea):
    """使用小步长像素滚动，减少鼠标滚轮上下滚动的跳跃感。"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll_animation = QPropertyAnimation(self.verticalScrollBar(), b"value", self)
        self._scroll_animation.setDuration(170)
        self._scroll_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

    def wheelEvent(self, event):
        # 只处理垂直滚轮；忽略触控板/鼠标的横向滚动分量。
        delta_y = event.pixelDelta().y()
        if not delta_y:
            delta_y = event.angleDelta().y() / 120.0 * 105
        if delta_y:
            bar = self.verticalScrollBar()
            target = max(bar.minimum(), min(bar.maximum(), bar.value() - int(delta_y)))
            self._scroll_animation.stop()
            self._scroll_animation.setStartValue(bar.value())
            self._scroll_animation.setEndValue(target)
            self._scroll_animation.start()
            event.accept()
            return
        event.accept()


class WallpaperCard(QFrame):
    def __init__(self, row, image_path, on_open, on_favorite, on_delete, on_rename, on_category, on_wallpaper, categories, parent=None):
        super().__init__(parent)
        self.setObjectName("WallpaperCard")
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(0)
        self.row = row
        self.image_path = str(image_path)
        self.cover = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 6)
        layout.setSpacing(4)
        cover = QLabel()
        cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cover.setFixedHeight(190)
        cover.setObjectName("CardCover")
        self.cover = cover
        cover.setText("滚动到此处加载预览")
        cover.mousePressEvent = lambda event: on_open(row)
        layout.addWidget(cover)
        title = QLabel(row[2])
        title.setObjectName("CardTitle")
        title.setStyleSheet("font-weight:600;padding:1px 2px;")
        title.setWordWrap(False)
        title.setToolTip(row[2])
        layout.addWidget(title)
        bottom = QHBoxLayout()
        cat = QLabel(row[3])
        cat.setObjectName("CardCategory")
        bottom.addWidget(cat)
        bottom.addStretch()
        fav = QPushButton("♥" if row[4] else "♡")
        fav.setFixedWidth(35)
        fav.clicked.connect(lambda: on_favorite(row[0], row[4]))
        bottom.addWidget(fav)
        more = QPushButton("···")
        more.setFixedWidth(38)
        menu = QMenu(more)
        rename = menu.addAction("重命名")
        delete = menu.addAction("删除图片")
        action = menu.exec(more.mapToGlobal(more.rect().bottomLeft())) if False else None
        more.clicked.connect(lambda: self.show_menu(more, on_delete, on_rename, on_category, on_wallpaper, categories))
        bottom.addWidget(more)
        layout.addLayout(bottom)

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
        self.cover.setText("")
        self.cover.setPixmap(pix.scaled(
            QSize(360, 190), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
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
        self.current_category = "全部壁纸"
        self.show_favorites = False
        self.settings = QSettings("Huanjing", "WallpaperGallery")
        saved_theme = self.settings.value("theme", "dark")
        self.theme = saved_theme if saved_theme in ("light", "dark") else "dark"
        self._thumbnail_timer = QTimer(self)
        self._thumbnail_timer.setSingleShot(True)
        self._thumbnail_timer.setInterval(35)
        self._thumbnail_timer.timeout.connect(self.load_visible_thumbnails)
        self._build_ui()
        self.apply_theme()
        self.refresh()

    def apply_theme(self):
        # 从模块全局读取样式，避免主题切换引用到旧版本/缺失的局部变量。
        app = QApplication.instance()
        if app is None:
            raise RuntimeError("Qt application is not initialized")
        light_style = globals().get(
            "LIGHT_STYLE",
            "QWidget { background:#f4f6fb; color:#202534; }"
        )
        dark_style = globals().get(
            "DARK_STYLE",
            "QWidget { background:#11131a; color:#edf0f7; }"
        )
        if self.theme not in ("light", "dark"):
            self.theme = "dark"
        app.setStyleSheet(light_style if self.theme == "light" else dark_style)
        app.setProperty("gallery_theme", self.theme)
        self.theme_button.setText("☀ 白天模式" if self.theme == "dark" else "🌙 夜间模式")
        self.settings.setValue("theme", self.theme)
        logging.info("Theme applied: %s", self.theme)

    def toggle_theme(self):
        previous_theme = self.theme
        self.theme = "light" if previous_theme == "dark" else "dark"
        try:
            self.apply_theme()
        except Exception:
            self.theme = previous_theme
            logging.exception("Failed to switch theme")
            QMessageBox.warning(
                self, "主题切换失败",
                f"切换主题时发生错误。程序已恢复原主题。\n日志位置：{LOG_PATH}"
            )

    def _build_ui(self):
        root = QWidget()
        root.setAcceptDrops(True)
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(18, 18, 18, 18)
        outer.setSpacing(16)

        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(220)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(16, 18, 16, 16)
        brand = QLabel("✦ 幻境壁纸馆")
        brand.setObjectName("Brand")
        side.addWidget(brand)
        side.addSpacing(14)
        side.addWidget(QLabel("图片空间", objectName="Muted"))
        self.nav = QListWidget()
        for name in ["全部壁纸", "我的收藏", "未分类"]:
            self.nav.addItem(name)
        self.nav.setCurrentRow(0)
        self.nav.currentTextChanged.connect(self.change_category)
        side.addWidget(self.nav)
        side.addSpacing(10)
        side.addWidget(QLabel("自定义分类", objectName="Muted"))
        self.categories = QListWidget()
        self.categories.currentTextChanged.connect(self.change_category)
        side.addWidget(self.categories, 1)
        add_cat = QPushButton("+ 新建分类")
        add_cat.clicked.connect(self.add_category)
        side.addWidget(add_cat)
        side.addStretch()
        note = QLabel("图片仅保存在本机\n不会自动上传网络")
        note.setObjectName("Muted")
        side.addWidget(note)
        outer.addWidget(sidebar)

        content = QVBoxLayout()
        header = QHBoxLayout()
        intro = QVBoxLayout()
        heading = QLabel("我的壁纸")
        heading.setStyleSheet("font-size:27px;font-weight:700;")
        intro.addWidget(heading)
        self.count_label = QLabel("收藏每一份喜欢的画面 · 也可以把图片直接拖进窗口")
        self.count_label.setObjectName("Muted")
        intro.addWidget(self.count_label)
        header.addLayout(intro)
        header.addStretch()
        self.theme_button = QPushButton()
        self.theme_button.clicked.connect(self.toggle_theme)
        header.addWidget(self.theme_button)
        self.search = ChineseLineEdit()
        self.search.setPlaceholderText("搜索壁纸名称或分类…")
        self.search.setFixedWidth(260)
        self.search.textChanged.connect(self.refresh)
        header.addWidget(self.search)
        import_btn = QPushButton("＋ 导入图片")
        import_btn.setObjectName("Primary")
        import_btn.clicked.connect(self.import_images)
        header.addWidget(import_btn)
        folder_btn = QPushButton("导入文件夹")
        folder_btn.clicked.connect(self.import_folder)
        header.addWidget(folder_btn)
        self.refresh_folders_btn = QPushButton("↻ 刷新文件夹")
        self.refresh_folders_btn.setToolTip("重新扫描之前导入过的文件夹，只添加新图片，不重复导入")
        self.refresh_folders_btn.clicked.connect(self.refresh_source_folders)
        header.addWidget(self.refresh_folders_btn)
        content.addLayout(header)

        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setContentsMargins(0, 8, 0, 8)
        self.grid.setHorizontalSpacing(8)
        self.grid.setVerticalSpacing(8)
        self.scroll = SmoothScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll.verticalScrollBar().setSingleStep(18)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.grid_host.setMinimumWidth(0)
        self.scroll.setWidget(self.grid_host)
        self._wallpaper_cards = {}
        self._virtual_row_height = 250
        self._virtual_overscan_rows = 1
        self.scroll.verticalScrollBar().valueChanged.connect(self.schedule_visible_thumbnails)
        content.addWidget(self.scroll, 1)
        outer.addLayout(content, 1)

    def rows(self):
        with sqlite3.connect(DB_PATH) as db:
            return db.execute("SELECT id,filename,title,category,favorite FROM wallpapers ORDER BY added_at DESC").fetchall()

    def refresh(self, *_):
        # 只保留视口附近的卡片控件，数据库中的完整壁纸列表仍然保留。
        for card in self._wallpaper_cards.values():
            self.grid.removeWidget(card)
            card.deleteLater()
        self._wallpaper_cards.clear()
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        query = self.search.text().strip().lower()
        rows = self.rows()
        filtered = []
        for row in rows:
            if self.show_favorites and not row[4]:
                continue
            if self.current_category not in ("全部壁纸", "我的收藏") and row[3] != self.current_category:
                continue
            if self.current_category == "未分类" and row[3] != "未分类":
                continue
            if query and query not in row[2].lower() and query not in row[3].lower():
                continue
            filtered.append(row)
        self.visible_rows = filtered
        self.count_label.setText(f"共 {len(filtered)} 张壁纸  ·  图片存储于本地")
        categories = self.category_names()
        self.grid_columns = 5
        for column in range(self.grid_columns):
            # 忽略卡片内容的自然宽度，由网格把可用空间平均分给两列。
            self.grid.setColumnMinimumWidth(column, 1)
            self.grid.setColumnStretch(column, 1)
        self._card_categories = categories
        self._virtual_row_count = (len(filtered) + self.grid_columns - 1) // self.grid_columns
        self.grid_host.setMinimumHeight(
            self._virtual_row_count * (self._virtual_row_height + self.grid.verticalSpacing()) + 16
        )
        for grid_row in range(self._virtual_row_count):
            self.grid.setRowMinimumHeight(grid_row, self._virtual_row_height)
        self._refresh_categories(rows)
        self.load_visible_thumbnails()

    def schedule_visible_thumbnails(self, *_):
        # 滚动过程中合并重复加载请求，避免解码缩略图抢占滚动事件。
        if hasattr(self, "_thumbnail_timer"):
            self._thumbnail_timer.start()

    def load_visible_thumbnails(self):
        if not hasattr(self, "_wallpaper_cards") or not hasattr(self, "visible_rows"):
            return
        # 虚拟化：视口上下各预加载一行，其余卡片控件立即回收。
        columns = getattr(self, "grid_columns", 2)
        row_step = self._virtual_row_height + self.grid.verticalSpacing()
        scroll_top = self.scroll.verticalScrollBar().value()
        viewport_height = max(1, self.scroll.viewport().height())
        first_row = max(0, scroll_top // row_step - self._virtual_overscan_rows)
        last_row = min(
            max(0, self._virtual_row_count - 1),
            (scroll_top + viewport_height) // row_step + self._virtual_overscan_rows
        )
        start = first_row * columns
        stop = min(len(self.visible_rows), (last_row + 1) * columns)
        wanted = set(range(start, stop))

        for index in list(self._wallpaper_cards):
            if index not in wanted:
                card = self._wallpaper_cards.pop(index)
                self.grid.removeWidget(card)
                card.deleteLater()

        for index in sorted(wanted):
            if index in self._wallpaper_cards:
                continue
            row = self.visible_rows[index]
            card = WallpaperCard(
                row, IMAGE_DIR / row[1], self.open_preview, self.toggle_favorite,
                self.delete_image, self.rename_image, self.move_category,
                self.set_wallpaper, self._card_categories
            )
            card.setFixedHeight(self._virtual_row_height)
            self._wallpaper_cards[index] = card
            self.grid.addWidget(card, index // columns, index % columns)
            thumbnail = self.thumbnail_for(row[1])
            card.image_path = str(thumbnail or (IMAGE_DIR / row[1]))
            card.load_thumbnail()

        self.count_label.setToolTip(
            f"当前只创建 {len(self._wallpaper_cards)} 张可视区域附近的卡片控件，共 {len(self.visible_rows)} 张壁纸"
        )

    def _refresh_categories(self, rows=None):
        with sqlite3.connect(DB_PATH) as db:
            saved = {r[0] for r in db.execute("SELECT name FROM categories").fetchall()}
        names = sorted(saved | {r[3] for r in (rows or self.rows()) if r[3] not in ("未分类", "")})
        current = self.categories.currentItem().text() if self.categories.currentItem() else None
        self.categories.blockSignals(True)
        self.categories.clear()
        self.categories.addItems(names)
        if current in names:
            matches = self.categories.findItems(current, Qt.MatchFlag.MatchExactly)
            if matches:
                self.categories.setCurrentItem(matches[0])
        self.categories.blockSignals(False)

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
                scaled = original.scaled(QSize(360, 220), Qt.AspectRatioMode.KeepAspectRatio)
                reader.setScaledSize(scaled)
            image = reader.read()
            if image.isNull():
                return source
            pixmap = QPixmap.fromImage(image)
            if pixmap.save(str(cached), "JPG", 88):
                return cached
        except (OSError, RuntimeError):
            pass
        return source

    def import_images(self):
        files, _ = QFileDialog.getOpenFileNames(self, "选择图片", str(Path.home()),
                                                "图片文件 (*.jpg *.jpeg *.png *.webp *.bmp *.gif)")
        self._import_paths(files)

    def import_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择图片文件夹", str(Path.home()))
        if folder:
            folder_path = str(Path(folder).resolve())
            with sqlite3.connect(DB_PATH) as db:
                db.execute("INSERT OR IGNORE INTO source_folders(path) VALUES(?)", (folder_path,))
            self._import_paths([folder_path])

    def refresh_source_folders(self):
        with sqlite3.connect(DB_PATH) as db:
            folders = [row[0] for row in db.execute("SELECT path FROM source_folders ORDER BY added_at, path")]
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
                                "以下文件夹不存在或无法访问：\n" + "\n".join(missing[:5]))
        self.statusBar().showMessage("文件夹扫描完成", 5000)

    def _import_paths(self, files, show_result=True):
        # Accept individual images and folders, including folders dropped onto the window.
        candidates = []
        seen = set()
        for item in files:
            path = Path(item)
            if path.is_dir():
                candidates.extend(p for p in path.rglob("*") if p.is_file())
            elif path.is_file():
                candidates.append(path)

        added = 0
        skipped = 0
        errors = []
        with sqlite3.connect(DB_PATH) as db:
            for src in candidates:
                if src.suffix.lower() not in SUPPORTED:
                    continue
                try:
                    resolved = str(src.resolve())
                    if resolved in seen or IMAGE_DIR.resolve() in src.resolve().parents:
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

        self.refresh()
        if added:
            self.statusBar().showMessage(f"新增导入 {added} 张图片", 5000)
        elif show_result:
            self.statusBar().showMessage(f"没有发现新图片（已跳过 {skipped} 张重复图片）", 5000)
        if errors:
            preview = "\n".join(errors[:8])
            if len(errors) > 8:
                preview += f"\n另有 {len(errors) - 8} 个文件导入失败。"
            QMessageBox.warning(self, "部分文件导入失败", preview)

    def open_preview(self, row):
        rows = getattr(self, "visible_rows", [])
        try:
            index = next(i for i, item in enumerate(rows) if item[0] == row[0])
        except StopIteration:
            rows = [row]
            index = 0
        dlg = PreviewDialog(rows, index, self)
        dlg.exec()

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
        SPI_SETDESKWALLPAPER = 20
        SPIF_UPDATEINIFILE = 0x01
        SPIF_SENDCHANGE = 0x02
        try:
            system_parameters_info = ctypes.windll.user32.SystemParametersInfoW
            system_parameters_info.argtypes = [
                ctypes.c_uint, ctypes.c_uint, ctypes.c_wchar_p, ctypes.c_uint
            ]
            system_parameters_info.restype = ctypes.c_bool
            result = system_parameters_info(
                SPI_SETDESKWALLPAPER, 0, image_path, SPIF_UPDATEINIFILE | SPIF_SENDCHANGE
            )
            if result:
                self.statusBar().showMessage("桌面壁纸设置成功", 4000)
            else:
                raise OSError("Windows 未能应用这张图片")
        except Exception as exc:
            QMessageBox.warning(self, "设置失败", str(exc))

    def delete_image(self, uid):
        answer = QMessageBox.question(
            self, "从壁纸馆移除",
            "确定从壁纸馆移除这张壁纸吗？\n\n"
            "只会移除软件内的记录和软件自己的副本，"
            "不会删除导入时所在文件夹中的原始图片。"
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        with sqlite3.connect(DB_PATH) as db:
            row = db.execute(
                "SELECT filename, source_path FROM wallpapers WHERE id=?", (uid,)
            ).fetchone()
            db.execute("DELETE FROM wallpapers WHERE id=?", (uid,))
        if row:
            # filename 指向软件自己的图库副本；source_path 始终只作来源记录，绝不删除。
            managed_copy = IMAGE_DIR / row[0]
            try:
                managed_copy.unlink(missing_ok=True)
            except OSError:
                logging.warning("Could not remove managed image copy: %s", managed_copy)
            for cached in THUMB_DIR.glob(f"{Path(row[0]).stem}_*.jpg"):
                try:
                    cached.unlink(missing_ok=True)
                except OSError:
                    logging.warning("Could not remove thumbnail cache: %s", cached)
        self.refresh()

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(DARK_STYLE)
    from PySide6.QtCore import qInstallMessageHandler
    qInstallMessageHandler(_qt_message_handler)

    try:
        logging.info("Preparing local storage: %s", DATA_DIR)
        ensure_storage()
        logging.info("Creating main window")
        window = MainWindow()
        window.show()
        logging.info("Main window shown")
    except Exception:
        details = traceback.format_exc()
        logging.critical("Startup failed\n%s", details)
        QMessageBox.critical(
            None, "幻境壁纸馆启动失败",
            f"程序启动时发生错误。\n\n请把下面的日志文件发给开发者：\n{LOG_PATH}\n\n错误摘要：\n{details[-1800:]}"
        )
        return 1
    return app.exec()

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        logging.critical("Fatal application error\n%s", traceback.format_exc())
        raise
