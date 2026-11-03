from pathlib import Path
import re

path = Path("main.py")
source = path.read_text(encoding="utf-8")

def replace_once(pattern, replacement, label):
    global source
    source, count = re.subn(pattern, lambda _m: replacement, source, count=1, flags=re.S)
    if count != 1:
        raise SystemExit(f"Preview scaling patch failed at: {label} (matches={count})")

replace_once(
    r"class PreviewLoadTask\(QRunnable\):.*?(?=\n\nclass PreviewDialog)",
    '''class PreviewLoadTask(QRunnable):
    """后台解码预览图；统一解码上限，显示时再按预览区域等比例适配。"""
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
            if original.isValid():
                # 所有图片统一使用同一解码上限，避免按窗口临时尺寸重复解码。
                reader.setScaledSize(original.scaled(QSize(2560, 1600), Qt.AspectRatioMode.KeepAspectRatio))
            image = reader.read()
        except (OSError, RuntimeError):
            logging.exception("Preview image load failed: %s", self.source_path)
        self.signals.finished.emit(self.cache_key, image)''',
    "preview worker"
)

replace_once(
    r"    def _cache_key\(self, index, target\):.*?(?=\n    def _request_image)",
    '''    def _cache_key(self, index, target=None):
        # 缓存按图片路径，而不是窗口尺寸；窗口变化只重新适配显示，不重复解码。
        return str(IMAGE_DIR / self.rows[index][1])
''',
    "cache key"
)

replace_once(
    r"    def _on_image_loaded\(self, key, image\):.*?(?=\n    def show_current)",
    '''    def _display_image(self, image):
        if image is None or image.isNull():
            self.image.setPixmap(QPixmap())
            self.image.setText("无法读取这张图片")
            return
        area = self.image.contentsRect().size()
        if area.width() < 1 or area.height() < 1:
            return
        pixmap = QPixmap.fromImage(image)
        fitted = pixmap.scaled(
            area, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self.image.setText("")
        self.image.setPixmap(fitted)

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
            self._display_image(image)
''',
    "image display"
)

replace_once(
    r"    def show_current\(self\):.*?(?=\n    def eventFilter)",
    '''    def show_current(self):
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
            self._display_image(cached)
        else:
            # 不保留上一张图片，避免新旧图片尺寸不同造成“先缩小再恢复”的错觉。
            self.image.setPixmap(QPixmap())
            self.image.setText("正在加载图片…")
            self._request_image(self.current_index, target)

        # 预读相邻图片；缓存与窗口尺寸无关。
        if len(self.rows) > 1:
            self._request_image(self.current_index - 1, target)
            self._request_image(self.current_index + 1, target)
''',
    "show current"
)

path.write_text(source, encoding="utf-8")
print("Preview scaling patch applied.")
