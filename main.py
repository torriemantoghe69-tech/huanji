import ctypes
import shutil
import sqlite3
import sys
import uuid
from pathlib import Path

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPixmap, QShortcut, QKeySequence
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

class PreviewDialog(QDialog):
    def __init__(self, image_path, title, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(1050, 720)
        layout = QVBoxLayout(self)
        self.image = QLabel()
        self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image.setStyleSheet("background:#08090d;border-radius:12px;")
        pix = QPixmap(str(image_path))
        self.image.setPixmap(pix.scaled(QSize(1000, 620), Qt.AspectRatioMode.KeepAspectRatio,
                                        Qt.TransformationMode.SmoothTransformation))
        layout.addWidget(self.image, 1)
        close = QPushButton("关闭预览")
        close.clicked.connect(self.accept)
        layout.addWidget(close, alignment=Qt.AlignmentFlag.AlignRight)

class WallpaperCard(QFrame):
    def __init__(self, row, image_path, on_open, on_favorite, on_delete, parent=None):
        super().__init__(parent)
        self.setObjectName("WallpaperCard")
        self.setStyleSheet("""
            QFrame#WallpaperCard { background:#1a1e29; border:1px solid #2b3040; border-radius:14px; }
            QFrame#WallpaperCard:hover { border:1px solid #8174ed; background:#202536; }
        """)
        self.row = row
        layout = QVBoxLayout(self)
        layout.setContentsMargins(9, 9, 9, 10)
        layout.setSpacing(8)
        cover = QLabel()
        cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cover.setFixedHeight(150)
        cover.setStyleSheet("background:#0e1016;border-radius:9px;")
        pix = QPixmap(str(image_path))
        cover.setPixmap(pix.scaled(QSize(250, 150), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                   Qt.TransformationMode.SmoothTransformation))
        cover.mousePressEvent = lambda event: on_open(row)
        layout.addWidget(cover)
        title = QLabel(row[2])
        title.setStyleSheet("font-weight:600;padding:1px 2px;")
        title.setWordWrap(False)
        title.setToolTip(row[2])
        layout.addWidget(title)
        bottom = QHBoxLayout()
        cat = QLabel(row[3])
        cat.setStyleSheet("color:#9299aa;font-size:11px;")
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
        more.clicked.connect(lambda: self.show_menu(more, on_delete))
        bottom.addWidget(more)
        layout.addLayout(bottom)

    def show_menu(self, button, on_delete):
        menu = QMenu(self)
        delete = menu.addAction("删除图片")
        chosen = menu.exec(button.mapToGlobal(button.rect().bottomLeft()))
        if chosen == delete:
            on_delete(self.row[0])

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1280, 820)
        self.current_category = "全部壁纸"
        self.show_favorites = False
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        root = QWidget()
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
        outer.addWidget(side)

        content = QVBoxLayout()
        header = QHBoxLayout()
        intro = QVBoxLayout()
        heading = QLabel("我的壁纸")
        heading.setStyleSheet("font-size:27px;font-weight:700;")
        intro.addWidget(heading)
        self.count_label = QLabel("收藏每一份喜欢的画面")
        self.count_label.setObjectName("Muted")
        intro.addWidget(self.count_label)
        header.addLayout(intro)
        header.addStretch()
        self.search = QLineEdit()
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
        content.addLayout(header)

        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setContentsMargins(0, 12, 0, 12)
        self.grid.setHorizontalSpacing(14)
        self.grid.setVerticalSpacing(14)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setWidget(self.grid_host)
        content.addWidget(self.scroll, 1)
        outer.addLayout(content, 1)

    def rows(self):
        with sqlite3.connect(DB_PATH) as db:
            return db.execute("SELECT id,filename,title,category,favorite FROM wallpapers ORDER BY added_at DESC").fetchall()

    def refresh(self, *_):
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
        self.count_label.setText(f"共 {len(filtered)} 张壁纸  ·  图片存储于本地")
        for index, row in enumerate(filtered):
            path = IMAGE_DIR / row[1]
            card = WallpaperCard(row, path, self.open_preview, self.toggle_favorite, self.delete_image)
            self.grid.addWidget(card, index // 4, index % 4)
        self.grid.setRowStretch((len(filtered) + 3) // 4, 1)
        self._refresh_categories(rows)

    def _refresh_categories(self, rows=None):
        names = sorted({r[3] for r in (rows or self.rows()) if r[3] not in ("未分类", "")})
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
        if ok and name:
            with sqlite3.connect(DB_PATH) as db:
                db.execute("UPDATE wallpapers SET category=? WHERE category='未分类'", (name,))
            self.current_category = name
            self.refresh()

    def import_images(self):
        files, _ = QFileDialog.getOpenFileNames(self, "选择图片", str(Path.home()),
                                                "图片文件 (*.jpg *.jpeg *.png *.webp *.bmp *.gif)")
        self._import_paths(files)

    def import_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择图片文件夹", str(Path.home()))
        if folder:
            files = [str(p) for p in Path(folder).rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED]
            self._import_paths(files)

    def _import_paths(self, files):
        added = 0
        for source in files:
            src = Path(source)
            if src.suffix.lower() not in SUPPORTED:
                continue
            uid = uuid.uuid4().hex
            filename = uid + src.suffix.lower()
            try:
                shutil.copy2(src, IMAGE_DIR / filename)
                with sqlite3.connect(DB_PATH) as db:
                    db.execute("INSERT INTO wallpapers(id,filename,title) VALUES(?,?,?)",
                               (uid, filename, src.stem))
                added += 1
            except OSError as exc:
                QMessageBox.warning(self, "导入失败", f"{src.name}\n{exc}")
        self.refresh()
        if added:
            self.statusBar().showMessage(f"已导入 {added} 张图片", 4000)

    def open_preview(self, row):
        path = IMAGE_DIR / row[1]
        dlg = PreviewDialog(path, row[2], self)
        dlg.exec()

    def toggle_favorite(self, uid, value):
        with sqlite3.connect(DB_PATH) as db:
            db.execute("UPDATE wallpapers SET favorite=? WHERE id=?", (0 if value else 1, uid))
        self.refresh()

    def delete_image(self, uid):
        answer = QMessageBox.question(self, "删除壁纸", "确定从壁纸馆删除这张图片吗？")
        if answer != QMessageBox.StandardButton.Yes:
            return
        with sqlite3.connect(DB_PATH) as db:
            row = db.execute("SELECT filename FROM wallpapers WHERE id=?", (uid,)).fetchone()
            db.execute("DELETE FROM wallpapers WHERE id=?", (uid,))
        if row:
            (IMAGE_DIR / row[0]).unlink(missing_ok=True)
        self.refresh()

def main():
    ensure_storage()
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(DARK_STYLE)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
