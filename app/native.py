"""Native PySide6 recipe library, with direct SQLite access and private local IPC."""
import argparse
import html
import json
import os
from pathlib import Path
import re
import sys
import time
import tomllib
from urllib.parse import quote

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Qt, Signal, Slot, QUrl, QSize, QEvent, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QBrush, QColor, QDesktopServices, QFont, QKeySequence, QPalette, QShortcut, QPixmap, QIcon, QPainter
from PySide6.QtNetwork import QLocalServer, QLocalSocket, QNetworkAccessManager, QNetworkRequest, QNetworkReply
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QFrame, QGroupBox, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QListView, QMessageBox, QProgressBar, QPushButton, QScrollArea, QSpinBox,
    QSplitter, QStyle, QStyledItemDelegate, QStyleOptionViewItem, QTabWidget, QTextBrowser, QTextEdit, QVBoxLayout, QWidget)

from . import recipe_store as store
from . import interface_languages
from . import local_runtime
from .ai_config import PROVIDERS, get_online_models, get_providers_dict, get_provider_status, mask_key
from .i18n import LANGUAGES, TARGET_LANGUAGES, localize_category, t
from .native_locales import text as native_text
from .native_ipc import socket_path


class WorkerSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)


class Worker(QRunnable):
    def __init__(self, function):
        super().__init__()
        self.function = function
        self.signals = WorkerSignals()

    @Slot()
    def run(self):
        try:
            result = self.function()
        except store.TranslationUnavailable:
            self.signals.failed.emit("translation_unavailable")
        except store.IncompleteRecipeTranslation:
            self.signals.failed.emit("translation_incomplete")
        except Exception:
            self.signals.failed.emit("failed")
        else:
            self.signals.finished.emit(result)


def get_theme_colors():
    theme = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))) / "omarchy/current/theme"
    try:
        return tomllib.loads((theme / "colors.toml").read_text())
    except (OSError, ValueError):
        return {"background": "#202020", "foreground": "#e0e0e0", "accent": "#d7a66c", "lighter_background": "#303030"}


def create_cook_icon(colors=None, size=38):
    colors = colors or {}
    accent = colors.get("accent", "#d7a66c")
    surface = colors.get("lighter_background", "#282828")
    muted = colors.get("muted", "#655545")
    svg_cloche = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" width="{size}" height="{size}">
  <rect width="48" height="48" rx="10" fill="{surface}" stroke="{muted}" stroke-width="1"/>
  <!-- Steam curls -->
  <path d="M19 13 C18 10.5 20 9 19 6.5 M24 12 C23 9.5 25 8 24 5.5 M29 13 C28 10.5 30 9 29 6.5" stroke="{accent}" stroke-width="1.5" stroke-linecap="round" fill="none"/>
  <!-- Cloche Handle -->
  <circle cx="24" cy="16.5" r="2.2" fill="{accent}"/>
  <!-- Cloche Dome -->
  <path d="M11 31 C11 19.5 37 19.5 37 31 Z" fill="{accent}"/>
  <!-- Subtle shine on dome -->
  <path d="M15 28 C15 22.5 21 21 25 21" stroke="{surface}" stroke-width="1.4" stroke-linecap="round" fill="none"/>
  <!-- Base platter -->
  <rect x="8" y="31.5" width="32" height="3" rx="1.5" fill="{accent}"/>
  <!-- Platter stand -->
  <rect x="16" y="35.5" width="16" height="2" rx="1" fill="{muted}"/>
</svg>"""
    try:
        renderer = QSvgRenderer(svg_cloche.encode("utf-8"))
        pixmap = QPixmap(size, size)
        pixmap.fill(QColor(0, 0, 0, 0))
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        return pixmap
    except Exception:
        return QPixmap()


def apply_theme(app):
    colors = get_theme_colors()
    palette = QPalette()
    roles = {QPalette.Window: "background", QPalette.WindowText: "foreground", QPalette.Base: "background",
             QPalette.AlternateBase: "lighter_background", QPalette.Text: "foreground", QPalette.Button: "lighter_background",
             QPalette.ButtonText: "foreground", QPalette.Highlight: "accent", QPalette.HighlightedText: "background",
             QPalette.ToolTipBase: "lighter_background", QPalette.ToolTipText: "foreground", QPalette.Link: "accent"}
    for role, name in roles.items():
        palette.setColor(role, QColor(colors.get(name, colors.get("foreground", "#e0e0e0"))))
    app.setPalette(palette)
    app.setStyle("Fusion")
    font_size = 13
    try:
        prefs = tomllib.loads((Path.home() / ".config/omarchy/shell.toml").read_text())
        font_size = max(10, min(24, int(prefs.get("font", {}).get("base-size", 13))))
    except (OSError, ValueError, TypeError):
        pass
    font = QFont("sans-serif")
    font.setPixelSize(font_size)
    app.setFont(font)
    bg = colors.get("background", "#202020"); fg = colors.get("foreground", "#e0e0e0")
    surface = colors.get("lighter_background", "#303030"); accent = colors.get("accent", "#d7a66c")
    muted = colors.get("muted", "#867658"); red = colors.get("red", "#db6c4f")
    selection = colors.get("selection", surface)
    app.setStyleSheet("""
        QWidget { color: FG; }
        QDialog, QTabWidget::pane, QScrollArea { background: BG; }
        QScrollArea { border: none; }
        QPushButton { background: SURFACE; border: 1px solid MUTED; border-radius: 7px; padding: 7px 13px; font-weight: 500; }
        QPushButton:hover { border-color: ACCENT; background: SELECTION; }
        QPushButton:disabled { color: MUTED; border-color: SURFACE; }
        QPushButton#primaryAction { border-color: ACCENT; color: ACCENT; font-weight: 600; min-width: 85px; }
        QPushButton#primaryAction:hover { background: ACCENT; color: BG; }
        QPushButton#dangerAction { border-color: MUTED; color: RED; }
        QPushButton#dangerAction:hover { border-color: RED; background: RED; color: BG; }
        QLineEdit, QComboBox, QSpinBox { background: SURFACE; border: 1px solid MUTED; border-radius: 6px; padding: 6px 9px; min-height: 20px; }
        QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border-color: ACCENT; }
        QLineEdit { selection-background-color: ACCENT; }
        QComboBox QAbstractItemView { background: SURFACE; color: FG; selection-background-color: ACCENT; selection-color: BG; border: 1px solid MUTED; }
        QComboBox QAbstractItemView::item:disabled { color: MUTED; }
        QTabWidget::pane { border: 0; }
        QTabBar::tab { background: SURFACE; padding: 11px 18px; margin-right: 4px; border-radius: 6px; font-weight: 500; }
        QTabBar::tab:selected { border-bottom: 2px solid ACCENT; color: ACCENT; font-weight: 600; }
        QListWidget { background: BG; border: 0; }
        QListWidget::item { background: SURFACE; color: FG; padding: 8px; border-radius: 8px; }
        QListWidget::item:selected { border: 1px solid ACCENT; }
        QGroupBox { margin-top: 8px; padding-top: 8px; }
        QGroupBox#card, QGroupBox#importCard, QGroupBox#settingsCard { background: SURFACE; border: 1px solid MUTED; border-radius: 10px; margin-top: 4px; padding: 12px; }
        QLabel#cardTitle { color: ACCENT; font-size: 13px; font-weight: 700; margin-bottom: 2px; }
        QLabel#hero { font-size: 24px; font-weight: 600; margin-top: 4px; margin-bottom: 2px; }
        QLabel#subtitle { color: MUTED; font-size: 12px; margin-bottom: 4px; }
        QLabel#headerFoodIcon { background: transparent; border: none; }
        QLabel#mutedHint { color: MUTED; font-size: 11px; }
        QLabel#modelBadge { background: SELECTION; border: 1px solid MUTED; border-radius: 5px; padding: 3px 8px; font-size: 11px; }
        QLabel#statusLabel { color: MUTED; font-size: 11px; padding: 2px 4px; }
        QTextBrowser { background: BG; border: 0; padding: 12px; }
        QTextBrowser#helpBrowser { background: BG; border: 0; padding: 18px 24px; }
        QGroupBox#card QPushButton { padding: 5px 9px; font-size: 11px; }
        QPushButton#cookAction { border-color: ACCENT; color: ACCENT; font-weight: 500; font-size: 11px; padding: 5px 9px; }
        QPushButton#cookAction:hover { background: ACCENT; color: BG; }
        QPushButton#cookAction:disabled { color: MUTED; border-color: SURFACE; }
        QSplitter::handle { background: MUTED; width: 1px; }
        QFrame#busyBanner { background: SELECTION; border: 2px solid ACCENT; border-radius: 10px; }
        QFrame#busyBanner[state="failed"] { border-color: RED; }
        QLabel#busyTitle { color: ACCENT; font-size: 16px; font-weight: 700; }
        QFrame#busyBanner[state="failed"] QLabel#busyTitle { color: RED; }
        QLabel#busyStep { font-size: 13px; font-weight: 500; }
        QLabel#busyElapsed { color: ACCENT; font-size: 15px; font-weight: 700; }
        QProgressBar#busyProgress { background: BG; border: 0; border-radius: 3px; max-height: 6px; min-height: 6px; }
        QProgressBar#busyProgress::chunk { background: ACCENT; border-radius: 3px; }
        QListWidget#videoResults::item:selected { border: 2px solid ACCENT; }
    """.replace("SURFACE", surface).replace("ACCENT", accent).replace("MUTED", muted).replace("FG", fg).replace("BG", bg).replace("RED", red).replace("SELECTION", selection))



class ProviderDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        fg = index.data(Qt.ItemDataRole.ForegroundRole)
        colors = get_theme_colors()
        if not (opt.state & QStyle.StateFlag.State_Enabled):
            muted_brush = QBrush(QColor(colors.get("muted", "#867658")))
            opt.palette.setBrush(QPalette.ColorRole.Text, muted_brush)
            opt.palette.setBrush(QPalette.ColorRole.WindowText, muted_brush)
        elif fg and not (opt.state & QStyle.StateFlag.State_Selected):
            brush = fg if isinstance(fg, QBrush) else QBrush(QColor(fg))
            opt.palette.setBrush(QPalette.ColorRole.Text, brush)
            opt.palette.setBrush(QPalette.ColorRole.WindowText, brush)
        super().paint(painter, opt, index)


class VideoDelegate(QStyledItemDelegate):
    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        option.decorationPosition = QStyleOptionViewItem.Left
        option.displayAlignment = Qt.AlignLeft | Qt.AlignVCenter


class VideoResults(QListWidget):
    ROW_HEIGHT = 124

    def __init__(self):
        super().__init__()
        self.setViewMode(QListView.IconMode); self.setItemDelegate(VideoDelegate(self))
        self.setFlow(QListView.LeftToRight); self.setWrapping(True)
        self.setResizeMode(QListView.Adjust); self.setMovement(QListView.Static)
        self.setUniformItemSizes(True); self.setWordWrap(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.NoFrame)
        # At least one row of cards; more rows when the window is taller.
        self.setMinimumHeight(self.ROW_HEIGHT)
        self.placeholder = ""

        sb = self.verticalScrollBar()
        sb.setSingleStep(self.ROW_HEIGHT)
        sb.setPageStep(self.ROW_HEIGHT)
        sb.sliderReleased.connect(self.snap_to_nearest)

        self.anim = QPropertyAnimation(sb, b"value", self)
        self.anim.setDuration(160)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)

        self.wheel_accumulator = 0
        self.reset_timer = QTimer(self)
        self.reset_timer.setSingleShot(True)
        self.reset_timer.timeout.connect(self.handle_wheel_timeout)
        self.currentItemChanged.connect(self.on_item_changed)

    def snap_to_nearest(self):
        sb = self.verticalScrollBar()
        target = round(sb.value() / self.ROW_HEIGHT) * self.ROW_HEIGHT
        target = max(sb.minimum(), min(sb.maximum(), target))
        self.scroll_to_val(target)

    def scroll_to_val(self, target):
        sb = self.verticalScrollBar()
        if sb.value() == target and self.anim.state() != QPropertyAnimation.Running:
            return
        self.anim.stop()
        self.anim.setStartValue(sb.value())
        self.anim.setEndValue(target)
        self.anim.start()

    def handle_wheel_timeout(self):
        if abs(self.wheel_accumulator) >= 40:
            step = 1 if self.wheel_accumulator < 0 else -1
            self.wheel_accumulator = 0
            sb = self.verticalScrollBar()
            end_val = self.anim.endValue()
            current = end_val if (self.anim.state() == QPropertyAnimation.Running and end_val is not None) else sb.value()
            target = current + step * self.ROW_HEIGHT
            target = max(sb.minimum(), min(sb.maximum(), target))
            self.scroll_to_val(target)
        else:
            self.wheel_accumulator = 0
            self.snap_to_nearest()

    def on_item_changed(self, current, _):
        if not current:
            return
        row_idx = self.row(current) // 2
        target = row_idx * self.ROW_HEIGHT
        sb = self.verticalScrollBar()
        target = max(sb.minimum(), min(sb.maximum(), target))
        self.scroll_to_val(target)

    def wheelEvent(self, event):
        delta = event.angleDelta().y() or event.pixelDelta().y()
        if not delta:
            return
        self.wheel_accumulator += delta
        sb = self.verticalScrollBar()
        end_val = self.anim.endValue()
        current = end_val if (self.anim.state() == QPropertyAnimation.Running and end_val is not None) else sb.value()
        if abs(self.wheel_accumulator) >= 100:
            step = 1 if self.wheel_accumulator < 0 else -1
            self.wheel_accumulator = 0
            target = current + step * self.ROW_HEIGHT
            target = max(sb.minimum(), min(sb.maximum(), target))
            self.scroll_to_val(target)
        else:
            self.reset_timer.start(250)
        event.accept()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.resize_cards()

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.count() and self.placeholder:
            painter = QPainter(self.viewport()); painter.setPen(self.palette().color(QPalette.PlaceholderText))
            painter.drawText(self.viewport().rect().adjusted(16, 0, -16, 0), Qt.AlignCenter | Qt.TextWordWrap, self.placeholder); painter.end()

    def resize_cards(self):
        vp_w = self.viewport().width()
        width = max(180, (vp_w - 24) // 2)
        self.setGridSize(QSize(width, self.ROW_HEIGHT))
        card_w = width - 12
        card_h = self.ROW_HEIGHT - 12
        for index in range(self.count()):
            self.item(index).setSizeHint(QSize(card_w, card_h))


def video_duration(seconds):
    if seconds is None:
        return "—"
    seconds = max(0, int(seconds)); hours, remaining = divmod(seconds, 3600); minutes, seconds = divmod(remaining, 60)
    return f"{hours}:{minutes:02}:{seconds:02}" if hours else f"{minutes}:{seconds:02}"


class Editor(QDialog):
    def __init__(self, parent, data):
        super().__init__(parent)
        self.owner = parent
        self.data = data
        self.setWindowTitle(parent.nt("edit"))
        self.resize(700, 680)
        outer_layout = QVBoxLayout(self); outer_layout.setContentsMargins(16, 16, 16, 16); outer_layout.setSpacing(10)
        
        self.title = QLineEdit(data["title"]); self.title.setMaxLength(300)
        self.emoji = QLineEdit(data["emoji"]); self.emoji.setMaxLength(8); self.emoji.setMaximumWidth(60)
        self.category = QComboBox(); self.category.addItems(store.categories()); self.category.setCurrentText(data["category"])
        self.ingredients = QTextEdit(); self.ingredients.setPlainText("\n".join(data["ingredients"]))
        self.instructions = QTextEdit(); self.instructions.setPlainText("\n".join(data["instructions"]))
        self.tags = QLineEdit(", ".join(data["tags"]))
        self.duration = QSpinBox(); self.duration.setRange(0, 100000); self.duration.setValue(data["duration_minutes"] or 0)
        self.calories = QSpinBox(); self.calories.setRange(0, 100000); self.calories.setValue(data["calories"] or 0)
        self.servings = QLineEdit(data["servings"])
        
        # General Info Card
        info_card = QGroupBox(); info_card.setObjectName("card"); info_layout = QVBoxLayout(info_card); info_layout.setContentsMargins(12, 10, 12, 10); info_layout.setSpacing(6)
        outer_layout.addWidget(info_card)
        info_form = QFormLayout(); info_layout.addLayout(info_form)
        title_row = QHBoxLayout()
        title_row.addWidget(self.title, 1); title_row.addWidget(self.emoji)
        info_form.addRow(parent.tr("title"), title_row)
        info_form.addRow(parent.tr("category_label"), self.category)
        info_form.addRow(parent.tr("tags"), self.tags)
        
        # Details Card
        meta_card = QGroupBox(); meta_card.setObjectName("card"); meta_layout = QHBoxLayout(meta_card); meta_layout.setContentsMargins(12, 8, 12, 8); meta_layout.setSpacing(12)
        outer_layout.addWidget(meta_card)
        dur_layout = QVBoxLayout(); dur_layout.addWidget(QLabel(parent.tr("duration"))); dur_layout.addWidget(self.duration); meta_layout.addLayout(dur_layout)
        serv_layout = QVBoxLayout(); serv_layout.addWidget(QLabel(parent.tr("servings"))); serv_layout.addWidget(self.servings); meta_layout.addLayout(serv_layout)
        cal_layout = QVBoxLayout(); cal_layout.addWidget(QLabel(parent.tr("calories"))); cal_layout.addWidget(self.calories); meta_layout.addLayout(cal_layout)
        
        # Content Card
        content_card = QGroupBox(); content_card.setObjectName("card"); content_layout = QVBoxLayout(content_card); content_layout.setContentsMargins(12, 10, 12, 10); content_layout.setSpacing(6)
        outer_layout.addWidget(content_card, 1)
        content_form = QFormLayout(); content_layout.addLayout(content_form)
        content_form.addRow(parent.tr("ingredients"), self.ingredients)
        content_form.addRow(parent.tr("instructions"), self.instructions)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText(parent.nt("save"))
        buttons.button(QDialogButtonBox.Save).setObjectName("primaryAction")
        buttons.button(QDialogButtonBox.Cancel).setText(parent.nt("cancel"))
        buttons.accepted.connect(self.save); buttons.rejected.connect(self.reject); outer_layout.addWidget(buttons)

    def save(self):
        try:
            store.update_recipe(self.data["id"], {"title": self.title.text().strip(), "emoji": self.emoji.text(),
                "category": self.category.currentText(), "ingredients": self.ingredients.toPlainText().splitlines(),
                "instructions": self.instructions.toPlainText().splitlines(), "tags": [s.strip() for s in self.tags.text().split(",") if s.strip()],
                "duration_minutes": self.duration.value() or None, "servings": self.servings.text(), "calories": self.calories.value() or None})
        except ValueError:
            QMessageBox.warning(self, self.owner.nt("edit"), self.owner.nt("failed"))
            return
        self.accept()


class CookingDialog(QDialog):
    def __init__(self, parent, data):
        super().__init__(parent)
        self.owner = parent; self.data = data; self.index = 0; self.remaining = 0
        self.setWindowTitle(parent.tr("cooking_mode_title")); self.resize(840, 580)
        layout = QVBoxLayout(self); layout.setContentsMargins(16, 16, 16, 16); layout.setSpacing(10)
        
        header = QHBoxLayout(); layout.addLayout(header)
        self.step_label = QLabel(); header.addWidget(self.step_label)
        header.addStretch()
        header.addWidget(QLabel(parent.nt("font_size")))
        self.text_size = QSpinBox(); self.text_size.setRange(18, 48); self.text_size.setSuffix(" px")
        try:
            size = int(store.setting("cooking_text_size", "26"))
        except ValueError:
            size = 26
        self.text_size.setValue(size); header.addWidget(self.text_size)
        
        card = QGroupBox(); card.setObjectName("card"); card_layout = QVBoxLayout(card); card_layout.setContentsMargins(14, 14, 14, 14)
        layout.addWidget(card, 1)
        self.step = QTextBrowser(); card_layout.addWidget(self.step)
        self.step.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        
        footer = QHBoxLayout(); footer.setSpacing(8); layout.addLayout(footer)
        self.prev = QPushButton(parent.nt("previous")); self.prev.clicked.connect(lambda: self.move(-1)); footer.addWidget(self.prev)
        self.next = QPushButton(parent.nt("next")); self.next.setObjectName("primaryAction"); self.next.clicked.connect(lambda: self.move(1)); footer.addWidget(self.next)
        footer.addStretch()
        self.minutes = QSpinBox(); self.minutes.setRange(1, 1440); self.minutes.setSuffix(" min"); footer.addWidget(self.minutes)
        self.start = QPushButton(parent.tr("timer_start")); self.start.clicked.connect(self.start_timer); footer.addWidget(self.start)
        self.timer_label = QLabel(); footer.addWidget(self.timer_label)
        
        self.timer = QTimer(self); self.timer.setInterval(1000); self.timer.timeout.connect(self.tick)
        self.text_size.valueChanged.connect(self.set_text_size)
        self.set_text_size(self.text_size.value(), save=False)
        self.refresh()

    def set_text_size(self, size, save=True):
        self.step.setStyleSheet(f"font-size: {size}px;")
        self.step_label.setStyleSheet(f"font-size: {max(18, size - 4)}px; font-weight: 600;")
        self.timer_label.setStyleSheet(f"font-size: {size}px; font-weight: 600;")
        if save:
            store.save_settings({"cooking_text_size": size})

    def refresh(self):
        steps = self.data["instructions"] or [""]
        self.step_label.setText(f"{self.owner.tr('cooking_step')} {self.index + 1} / {len(steps)}")
        self.step.setPlainText(steps[self.index])
        self.prev.setEnabled(self.index > 0); self.next.setEnabled(self.index < len(steps)-1)
        amount = re.search(r"(\d+)\s*(?:min|minute|Minut|minuto)", steps[self.index], re.I)
        self.minutes.setValue(int(amount[1]) if amount else 5)

    def move(self, delta):
        self.index = max(0, min(len(self.data["instructions"])-1, self.index + delta)); self.refresh()

    def start_timer(self):
        self.remaining = self.minutes.value() * 60; self.timer.start(); self.tick()

    def tick(self):
        self.timer_label.setText(f"{self.owner.nt('timer')}: {self.remaining // 60:02d}:{self.remaining % 60:02d}")
        if self.remaining <= 0:
            self.timer.stop(); QApplication.beep(); self.timer_label.setText(self.owner.nt("timer_done"))
        else:
            self.remaining -= 1


class RecipeWindow(QDialog):
    # Emitted from worker threads; Qt queues delivery onto the GUI thread.
    job_progress = Signal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Simple Recipes")
        self.resize(1050, 760)
        self.setMinimumSize(700, 520)
        self.language = store.setting("ui_language", "en")
        if self.language not in TARGET_LANGUAGES or not interface_languages.load(self.language):
            self.language = "en"
        self.setLayoutDirection(Qt.RightToLeft if self.language == "ar" else Qt.LeftToRight)
        self.current_id = None
        self.busy = False
        self.stop_ai_pending = False
        self.ai_workers = []
        self.pool = QThreadPool(self); self.pool.setMaxThreadCount(1)
        self.worker = None
        self.selected_config = store.configuration()
        self.theme_colors = get_theme_colors()
        self.setup_pending = not store.setting("native_setup_done") and not any(store.setting(key) for key in ("ai_provider", "ai_model", "ui_language", "phone_number"))
        self.ui_texts = []
        self.tab_keys = []
        outer = QVBoxLayout(self); outer.setContentsMargins(12, 10, 12, 10); outer.setSpacing(6)
        self.build_busy_banner(outer)
        self.tabs = QTabWidget(); outer.addWidget(self.tabs)
        self.status = QLabel(); self.status.setObjectName("statusLabel"); self.status.setWordWrap(True); self.status.setTextFormat(Qt.PlainText); outer.addWidget(self.status)
        self.build_library(); self.build_import(); self.build_settings(); self.build_help()
        pages = {key: self.tabs.widget(index) for index, key in enumerate(self.tab_keys)}
        self.tabs.clear(); self.tab_keys = []
        for key in ("import_tab", "library", "settings", "help"):
            self.add_tab(pages[key], key)
        self.tabs.currentChanged.connect(self.tab_switched)
        self.network = QNetworkAccessManager(self); self.previews = {}; self.preview_pending = set()
        self.video_rows = []
        QShortcut(QKeySequence("Escape"), self, activated=self.hide)
        QShortcut(QKeySequence("Ctrl+F"), self, activated=lambda: self.video_query.setFocus() if self.tabs.currentIndex() == 0 else self.search.setFocus())
        self.retranslate(); self.refresh_library(); self.fill_models(); self.fill_targets(store.targets())

    def nt(self, key):
        return native_text(key, self.language)

    def tr(self, key):
        fallback = {"title": self.nt("new"), "emoji": "Emoji", "tags": "Tags"}
        value = t(key, self.language)
        return fallback.get(key, value) if value == key else value

    def bound(self, widget, key, native=True):
        self.ui_texts.append((widget, key, native))
        return widget

    def button(self, key, action, native=True):
        button = self.bound(QPushButton(), key, native); button.clicked.connect(action); return button

    def label(self, key, native=True):
        label = self.bound(QLabel(self.nt(key) if native else self.tr(key)), key, native); label.setTextFormat(Qt.PlainText); label.setWordWrap(True); return label

    def add_tab(self, page, key):
        self.tabs.addTab(page, ""); self.tab_keys.append(key)

    def build_busy_banner(self, outer):
        # Long AI jobs need a status that is impossible to miss, on every tab.
        self.busy_banner = QFrame(); self.busy_banner.setObjectName("busyBanner"); self.busy_banner.setProperty("state", "busy")
        layout = QVBoxLayout(self.busy_banner); layout.setContentsMargins(12, 6, 12, 8); layout.setSpacing(4)
        top = QHBoxLayout(); top.setSpacing(10); layout.addLayout(top)
        self.busy_title = QLabel(); self.busy_title.setObjectName("busyTitle"); self.busy_title.setTextFormat(Qt.PlainText); self.busy_title.setWordWrap(True); top.addWidget(self.busy_title, 1)
        self.busy_elapsed = QLabel(); self.busy_elapsed.setObjectName("busyElapsed"); top.addWidget(self.busy_elapsed)
        self.busy_close = QPushButton("×"); self.busy_close.setFlat(True); self.busy_close.setFixedWidth(32); self.busy_close.clicked.connect(self.dismiss_banner); top.addWidget(self.busy_close)
        self.busy_step = QLabel(); self.busy_step.setObjectName("busyStep"); self.busy_step.setTextFormat(Qt.PlainText); self.busy_step.setWordWrap(True); layout.addWidget(self.busy_step)
        self.busy_progress = QProgressBar(); self.busy_progress.setObjectName("busyProgress"); self.busy_progress.setRange(0, 0); self.busy_progress.setTextVisible(False); layout.addWidget(self.busy_progress)
        self.busy_banner.hide(); outer.addWidget(self.busy_banner)
        self.busy_started = None
        self.busy_clock = QTimer(self); self.busy_clock.setInterval(1000); self.busy_clock.timeout.connect(self.update_busy_clock)
        self.banner_timer = QTimer(self); self.banner_timer.setSingleShot(True); self.banner_timer.timeout.connect(self.dismiss_banner)
        self.job_progress.connect(self.show_job_step)

    def set_banner_state(self, state):
        self.busy_banner.setProperty("state", state)
        self.busy_banner.style().unpolish(self.busy_banner); self.busy_banner.style().polish(self.busy_banner)
        self.busy_title.style().unpolish(self.busy_title); self.busy_title.style().polish(self.busy_title)

    def show_busy(self, message):
        self.banner_timer.stop(); self.set_banner_state("busy")
        self.busy_title.setText("⏳ " + self.nt(message)); self.busy_step.setText(""); self.busy_step.hide()
        self.busy_banner.setToolTip(self.nt("working"))
        self.busy_progress.show(); self.busy_close.hide()
        self.busy_started = time.monotonic(); self.update_busy_clock(); self.busy_clock.start()
        self.busy_banner.show()
        self.setWindowTitle("⏳ Simple Recipes")

    def show_job_step(self, key):
        if self.busy:
            self.busy_step.setText(("← " if self.layoutDirection() == Qt.RightToLeft else "→ ") + self.nt(key)); self.busy_step.show()

    def update_busy_clock(self):
        seconds = int(time.monotonic() - self.busy_started) if self.busy_started is not None else 0
        self.busy_elapsed.setText(f"{seconds // 60}:{seconds % 60:02d}")

    def end_busy(self, text, failed=False):
        self.busy_clock.stop(); self.busy_started = None
        self.setWindowTitle("Simple Recipes")
        self.set_banner_state("failed" if failed else "done")
        self.busy_title.setText(("⚠ " if failed else "✓ ") + text)
        self.busy_progress.hide(); self.busy_step.hide(); self.busy_close.show(); self.busy_banner.setToolTip("")
        self.banner_timer.start(15000 if failed else 5000)

    def dismiss_banner(self):
        if not self.busy:
            self.banner_timer.stop(); self.busy_banner.hide()

    def tab_switched(self, index):
        key = self.tab_keys[index] if index < len(self.tab_keys) else ""
        if key == "import_tab":
            self.model_line.setText(self.model_status())
            self.use_ai.setChecked(bool(store.setting("ai_provider")) and store.setting("ai_enabled", "1") != "0")
            self.fill_targets(store.targets())
        elif key == "library":
            self.refresh_library()
        elif key == "settings":
            self.fill_provider_list()

    def retranslate(self):
        for widget, key, native in self.ui_texts:
            value = self.nt(key) if native else self.tr(key)
            widget.setText(value.replace("<br>", " ") if key == "hero_title" else value)
        for index, key in enumerate(self.tab_keys):
            self.tabs.setTabText(index, self.nt(key))
        self.search.setPlaceholderText(t("search_placeholder", self.language))
        self.url.setPlaceholderText("https://…")
        self.model_line.setText(self.model_status())
        for index, key in enumerate(["sort_newest", "sort_oldest", "sort_title", "sort_duration", "sort_calories", "sort_tried"]):
            self.sort.setItemText(index, t(key, self.language))
        self.video_language.setItemText(0, self.nt("all_languages"))
        self.video_group.setItemText(0, self.nt("all_channels"))
        self.video_results.placeholder = self.nt("video_empty"); self.video_results.viewport().update()
        self.video_language.setToolTip(self.nt("search_language")); self.video_count.setSuffix(" " + self.nt("result_count"))
        self.video_filter.setPlaceholderText(self.nt("filter_results"))
        self.refresh_help()

    def build_library(self):
        page = QWidget(); layout = QVBoxLayout(page); layout.setContentsMargins(14, 10, 14, 10); layout.setSpacing(8)
        row = QHBoxLayout(); row.setSpacing(6); layout.addLayout(row)
        self.search = QLineEdit(); self.search.textChanged.connect(self.refresh_library); row.addWidget(self.search, 2)
        self.category_filter = QComboBox(); self.category_filter.setMinimumWidth(130); self.category_filter.currentIndexChanged.connect(self.refresh_library); row.addWidget(self.category_filter)
        self.sort = QComboBox(); self.sort.setMinimumWidth(130)
        for sort in ("newest", "oldest", "title", "duration", "calories", "tried"):
            self.sort.addItem(sort, sort)
        self.sort.currentIndexChanged.connect(self.refresh_library); row.addWidget(self.sort)
        self.favorite_filter = self.bound(QCheckBox(), "favorites", False); self.favorite_filter.toggled.connect(self.refresh_library); row.addWidget(self.favorite_filter)
        self.group_categories = self.bound(QCheckBox(), "group_category"); self.group_categories.setChecked(True); self.group_categories.toggled.connect(self.refresh_library); row.addWidget(self.group_categories)
        split = QSplitter(); layout.addWidget(split, 1)
        self.list = QListWidget(); self.list.setIconSize(QSize(120, 80)); self.list.setSpacing(8); self.list.setWordWrap(True); self.list.currentItemChanged.connect(self.show_selected); split.addWidget(self.list)
        right = QWidget(); detail = QVBoxLayout(right); detail.setContentsMargins(6, 0, 0, 0); detail.setSpacing(6)
        self.detail = QTextBrowser(); self.detail.setOpenExternalLinks(False); detail.addWidget(self.detail, 1)
        
        action_card = QGroupBox(); action_card.setObjectName("card"); card_layout = QVBoxLayout(action_card); card_layout.setContentsMargins(12, 8, 12, 8); card_layout.setSpacing(6)
        detail.addWidget(action_card)
        
        # Row 1: what you do with a recipe most: cook it, mark it, file it.
        cook_row = QHBoxLayout(); cook_row.setSpacing(6); card_layout.addLayout(cook_row)
        self.cook_button = self.button("cooking_mode_title", self.cook, False); self.cook_button.setObjectName("cookAction"); cook_row.addWidget(self.cook_button)
        self.favorite_button = self.button("favorites", self.toggle_favorite, False); cook_row.addWidget(self.favorite_button)
        self.tried_button = self.button("status_tried", self.toggle_tried, False); cook_row.addWidget(self.tried_button)
        cook_row.addStretch()
        cook_row.addWidget(self.label("category_label", False))
        self.recipe_category = QComboBox(); self.recipe_category.setMinimumWidth(140); self.recipe_category.setMaximumWidth(240); self.recipe_category.currentIndexChanged.connect(self.assign_category); cook_row.addWidget(self.recipe_category)

        # Row 2: share or look up the original.
        share_row = QHBoxLayout(); share_row.setSpacing(6); card_layout.addLayout(share_row)
        self.source_button = self.button("source", self.open_source); share_row.addWidget(self.source_button)
        self.copy_button = self.button("copy", self.copy_recipe); share_row.addWidget(self.copy_button)
        self.share_button = self.button("share_all", self.share, False); share_row.addWidget(self.share_button)
        share_row.addStretch()
        
        mgmt_row = QHBoxLayout(); mgmt_row.setSpacing(6); card_layout.addLayout(mgmt_row)
        self.edit_button = self.button("edit", self.edit); mgmt_row.addWidget(self.edit_button)
        self.reprocess_button = self.button("use_ai_label", self.reprocess, False); mgmt_row.addWidget(self.reprocess_button)
        mgmt_row.addStretch()
        self.delete_button = self.button("delete", self.delete); self.delete_button.setObjectName("dangerAction"); mgmt_row.addWidget(self.delete_button)
        
        split.addWidget(right); split.setSizes([380, 600])
        bottom = QHBoxLayout(); bottom.setSpacing(6); layout.addLayout(bottom)
        self.new_button = self.button("new", self.new_recipe); self.new_button.setObjectName("primaryAction"); bottom.addWidget(self.new_button)
        bottom.addStretch(); bottom.addWidget(self.button("close", self.hide))
        self.add_tab(page, "library")

    def build_import(self):
        # Scroll instead of overlapping cards when the window is short (e.g. while the busy banner shows).
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QScrollArea.NoFrame)
        page = QWidget(); scroll.setWidget(page); outer = QVBoxLayout(page); outer.setContentsMargins(16, 10, 16, 12); outer.setSpacing(10)

        # Compact header: icon beside title and subtitle instead of two stacked rows.
        header = QHBoxLayout(); header.setSpacing(12); outer.addLayout(header)
        self.header_food_icon = QLabel(); self.header_food_icon.setObjectName("headerFoodIcon")
        self.header_food_icon.setFixedSize(38, 38)
        self.header_food_icon.setPixmap(create_cook_icon(self.theme_colors, 38))
        header.addWidget(self.header_food_icon, 0, Qt.AlignVCenter)
        titles = QVBoxLayout(); titles.setSpacing(0); header.addLayout(titles, 1)
        hero = self.label("hero_title", False); hero.setTextFormat(Qt.RichText); hero.setObjectName("hero"); titles.addWidget(hero)
        subtitle = self.label("hero_subtitle", False); subtitle.setObjectName("subtitle"); titles.addWidget(subtitle)

        # 1. Paste a link and import (primary action).
        card = QGroupBox(); card.setObjectName("importCard"); layout = QVBoxLayout(card); layout.setContentsMargins(14, 12, 14, 12); layout.setSpacing(8)
        outer.addWidget(card)
        import_title = self.label("import_label", False); import_title.setObjectName("cardTitle"); layout.addWidget(import_title)
        row = QHBoxLayout(); layout.addLayout(row)
        self.url = QLineEdit(); self.url.returnPressed.connect(self.import_link); row.addWidget(self.url, 1)
        self.import_button = self.button("import_tab", self.import_link); self.import_button.setObjectName("primaryAction"); row.addWidget(self.import_button)

        # AI options read as one sentence: [x] Translate with AI into [target] using [model].
        options = QHBoxLayout(); options.setSpacing(8); layout.addLayout(options)
        self.use_ai = self.bound(QCheckBox(), "use_ai_label", False); self.use_ai.setChecked(bool(store.setting("ai_provider")) and store.setting("ai_enabled", "1") != "0"); options.addWidget(self.use_ai)
        self.use_ai.toggled.connect(lambda checked: store.save_settings({"ai_enabled": "1" if checked else "0"}))
        options.addWidget(QLabel("→"))
        self.target = QComboBox(); self.target.setMinimumWidth(160); self.target.setMaximumWidth(250); self.target.currentIndexChanged.connect(self.target_changed); options.addWidget(self.target)
        self.model_line = QLabel(); self.model_line.setTextFormat(Qt.PlainText); self.model_line.setObjectName("modelBadge"); options.addWidget(self.model_line)
        options.addStretch()
        self.check_button = self.button("check_languages", self.select_and_check); self.check_button.setObjectName("primaryAction"); options.addWidget(self.check_button)
        settings_shortcut = self.button("ai_settings", lambda: self.tabs.setCurrentIndex(self.tab_keys.index("settings"))); options.addWidget(settings_shortcut)
        # Only shown while AI cannot translate yet, together with the button that fixes it.
        self.ai_hint = self.label("target_hint"); self.ai_hint.setObjectName("mutedHint"); layout.addWidget(self.ai_hint)

        # 2. Or find a recipe video.
        search_card = QGroupBox(); search_card.setObjectName("importCard"); search_layout = QVBoxLayout(search_card); search_layout.setContentsMargins(14, 12, 14, 12); search_layout.setSpacing(8); outer.addWidget(search_card, 1)
        search_title = self.label("video_search"); search_title.setObjectName("cardTitle"); search_layout.addWidget(search_title)
        # Query and the options that apply to the next search stay together.
        search_row = QHBoxLayout(); search_row.setSpacing(8); search_layout.addLayout(search_row)
        self.video_query = QLineEdit(); self.video_query.setPlaceholderText(t("video_placeholder", self.language)); self.video_query.returnPressed.connect(self.video_search); search_row.addWidget(self.video_query, 1)
        self.video_language = QComboBox(); self.video_language.addItem(self.nt("all_languages"), "")
        for code, name in TARGET_LANGUAGES.items():
            self.video_language.addItem(name, code)
        self.video_language.setCurrentIndex(max(0, self.video_language.findData(store.setting("video_search_language"))))
        self.video_language.setMaximumWidth(180); self.video_language.setToolTip(self.nt("search_language")); search_row.addWidget(self.video_language)
        self.video_count = QSpinBox(); self.video_count.setRange(1, 50); self.video_count.setValue(int(store.setting("video_result_count", "10"))); self.video_count.setMaximumWidth(75)
        self.video_count.setMaximumWidth(150); self.video_count.setSuffix(" " + self.nt("result_count")); search_row.addWidget(self.video_count)
        self.video_button = self.button("search", self.video_search); self.video_button.setObjectName("primaryAction"); search_row.addWidget(self.video_button)

        # Filters only narrow the results already shown, so they live above the results.
        self.video_filter_row = QWidget(); filters = QHBoxLayout(self.video_filter_row); filters.setContentsMargins(0, 0, 0, 0); filters.setSpacing(8)
        self.video_filter = QLineEdit(); self.video_filter.setPlaceholderText(self.nt("filter_results")); self.video_filter.textChanged.connect(self.render_videos); filters.addWidget(self.video_filter, 1)
        self.video_group = QComboBox(); self.video_group.setMinimumWidth(140); self.video_group.setMaximumWidth(220); self.video_group.addItem(self.nt("all_channels"), ""); self.video_group.currentIndexChanged.connect(self.render_videos); filters.addWidget(self.video_group)
        self.video_filter_row.hide(); search_layout.addWidget(self.video_filter_row)

        self.video_results = VideoResults(); self.video_results.setObjectName("videoResults"); self.video_results.setIconSize(QSize(120, 80)); self.video_results.setSpacing(8)
        self.video_results.placeholder = self.nt("video_empty")
        self.video_results.itemActivated.connect(self.preview_video); self.video_results.itemClicked.connect(self.pick_video)
        search_layout.addWidget(self.video_results, 1)

        video_actions = QHBoxLayout(); search_layout.addLayout(video_actions)
        self.video_preview_button = self.button("preview_video", self.preview_video); self.video_preview_button.setEnabled(False); video_actions.addWidget(self.video_preview_button)
        pick_hint = self.label("pick_hint"); pick_hint.setObjectName("mutedHint"); video_actions.addWidget(pick_hint, 1)
        self.video_results.currentItemChanged.connect(self.video_selection_changed)
        self.add_tab(scroll, "import_tab")

    def build_settings(self):
        page = QWidget(); page_layout = QVBoxLayout(page); page_layout.setContentsMargins(14, 10, 14, 10)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QScrollArea.NoFrame); page_layout.addWidget(scroll)
        content = QWidget(); layout = QVBoxLayout(content); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(10); scroll.setWidget(content)
        def card(title_key, native=False):
            box = QGroupBox(); box.setObjectName("settingsCard"); box_layout = QVBoxLayout(box); box_layout.setContentsMargins(14, 10, 14, 10); box_layout.setSpacing(8); layout.addWidget(box)
            title = self.label(title_key, native); title.setObjectName("cardTitle"); box_layout.addWidget(title)
            return box_layout
        def form(parent):
            rows = QFormLayout(); rows.setFieldGrowthPolicy(QFormLayout.FieldsStayAtSizeHint); rows.setHorizontalSpacing(12); rows.setVerticalSpacing(8); parent.addLayout(rows)
            return rows

        # Card 1: AI provider and model. Target languages depend on it, so it comes first.
        ai_layout = card("ai_heading")
        ai_form = form(ai_layout); self.ai_form = ai_form
        self.provider = QComboBox(); self.provider.setMinimumWidth(200); self.provider.setMaximumWidth(320)
        self.provider_delegate = ProviderDelegate(self.provider)
        self.provider.setItemDelegate(self.provider_delegate)
        self.fill_provider_list()
        self.provider.currentIndexChanged.connect(self.provider_changed)
        ai_form.addRow(self.label("provider_label", False), self.provider)
        self.provider_help = QLabel(); self.provider_help.setTextFormat(Qt.PlainText); self.provider_help.setWordWrap(True); self.provider_help.setObjectName("mutedHint")
        self.provider_help.setMaximumWidth(520)
        ai_form.addRow("", self.provider_help)
        self.custom_url = QLineEdit(store.setting("custom_base_url")); self.custom_url.setMinimumWidth(240); self.custom_url.setMaximumWidth(380); self.custom_url.textChanged.connect(self.model_edited)
        self.custom_url_label = self.label("server_url_label", False); ai_form.addRow(self.custom_url_label, self.custom_url)
        self.key = QLineEdit(); self.key.setEchoMode(QLineEdit.Password); self.key.setMinimumWidth(240); self.key.setMaximumWidth(380); self.key.textChanged.connect(self.model_edited)
        self.key_label = self.label("api_key_label", False); ai_form.addRow(self.key_label, self.key)
        self.model = QComboBox(); self.model.setEditable(True); self.model.setMinimumWidth(220); self.model.setMaximumWidth(320); self.model.currentTextChanged.connect(self.model_edited)
        ai_form.addRow(self.label("model_label", False), self.model)
        self.select_button = self.button("select_check", self.select_and_check); self.select_button.setObjectName("primaryAction")
        ai_form.addRow("", self.select_button)
        privacy_label = self.label("privacy"); privacy_label.setObjectName("mutedHint")
        ai_layout.addWidget(privacy_label)

        # Card 2: Languages: interface and recipe target (verified by the model above).
        lang_layout = card("lang_heading")
        lang_form = form(lang_layout); self.lang_form = lang_form
        self.layout_language = QComboBox(); self.layout_language.setMinimumWidth(200); self.layout_language.setMaximumWidth(280)
        for code, name in {**LANGUAGES, **{code: TARGET_LANGUAGES[code] for code in interface_languages.available()},
                           **{row["code"]: row["name"] for row in store.targets()}}.items():
            self.layout_language.addItem(name, code)
        self.layout_language.setCurrentIndex(self.layout_language.findData(self.language))
        self.layout_language.currentIndexChanged.connect(self.layout_changed)
        lang_form.addRow(self.label("lang_layout_label", False), self.layout_language)
        self.settings_target = QComboBox(); self.settings_target.setMinimumWidth(200); self.settings_target.setMaximumWidth(280); self.settings_target.currentIndexChanged.connect(self.settings_target_changed)
        lang_form.addRow(self.label("target_lang_label", False), self.settings_target)
        self.language_status = QLabel(); self.language_status.setTextFormat(Qt.PlainText); self.language_status.setWordWrap(True); self.language_status.setObjectName("mutedHint")
        self.language_status.setMaximumWidth(520)
        lang_form.addRow("", self.language_status)

        # Card 3: Categories
        cat_btn_row = QHBoxLayout(); cat_btn_row.setSpacing(6); card("categories_heading", True).addLayout(cat_btn_row)
        cat_btn_row.addWidget(self.button("add_category", self.add_category))
        cat_btn_row.addWidget(self.button("rename_category", self.rename_category))
        cat_btn_row.addWidget(self.button("delete_category", self.delete_category))
        cat_btn_row.addStretch()

        # Card 4: WhatsApp sharing
        phone_row = QHBoxLayout(); phone_row.setSpacing(6); card("whatsapp_heading").addLayout(phone_row)
        phone_row.addWidget(self.label("phone_label", False))
        self.phone = QLineEdit(store.setting("phone_number")); self.phone.setMinimumWidth(200); self.phone.setMaximumWidth(280); self.phone.returnPressed.connect(self.save_phone); phone_row.addWidget(self.phone)
        self.phone_button = self.button("phone_save_btn", self.save_phone, False); phone_row.addWidget(self.phone_button)
        phone_row.addStretch()

        # Card 5: Data & backup
        data_btn_row = QHBoxLayout(); data_btn_row.setSpacing(6); card("data_heading", True).addLayout(data_btn_row)
        data_btn_row.addWidget(self.button("backup", self.backup))
        data_btn_row.addWidget(self.button("export", self.export))
        data_btn_row.addWidget(self.button("restore", self.restore))
        data_btn_row.addStretch()

        # Card 6: Setup & reset (the destructive action stays last and red).
        maint_btn_row = QHBoxLayout(); maint_btn_row.setSpacing(6); card("maintenance_heading", True).addLayout(maint_btn_row)
        maint_btn_row.addWidget(self.button("setup", self.show_setup))
        maint_btn_row.addStretch()
        reset_btn = self.button("reset", self.reset); reset_btn.setObjectName("dangerAction"); maint_btn_row.addWidget(reset_btn)

        layout.addStretch()
        self.add_tab(page, "settings")

    def build_help(self):
        self.help_view = QTextBrowser(); self.help_view.setOpenExternalLinks(True)
        self.help_view.setObjectName("helpBrowser")
        self.add_tab(self.help_view, "help")

    def refresh_help(self):
        guide = Path(__file__).resolve().parent.parent / "USER_GUIDE.md"
        try:
            contents = guide.read_text()
        except OSError:
            contents = self.nt("setup_help")
        raw_md = "# " + self.nt("help") + "\n\n" + self.nt("setup_help") + "\n\n" + self.nt("privacy") + "\n\n" + contents
        self.help_view.setMarkdown(raw_md)
        colors = get_theme_colors()
        accent = colors.get("accent", "#d7a66c")
        html = self.help_view.toHtml()
        html = re.sub(r'(<h1[^>]*margin-top:)[0-9]+px;(.*?margin-bottom:)[0-9]+px;', r'\g<1>22px;\g<2>10px;', html)
        html = re.sub(r'(<h[2-6][^>]*margin-top:)[0-9]+px;(.*?margin-bottom:)[0-9]+px;', r'\g<1>18px;\g<2>8px;', html)
        html = re.sub(r'(<p[^>]*margin-top:)[0-9]+px;(.*?margin-bottom:)[0-9]+px;', r'\g<1>3px;\g<2>12px; line-height: 145%;', html)
        html = re.sub(r'^(.*?<h1[^>]*margin-top:)22px;', r'\g<1>4px;', html, count=1, flags=re.DOTALL)
        html = re.sub(r'(<h[1-6][^>]*><span style=\")', rf'\1color:{accent}; ', html)
        html = re.sub(r'(<a\s+[^>]*><span\s+style=\")[^\"\']*color:[^;]+;', rf'\1color:{accent};', html)
        self.help_view.setHtml(html)

    def refresh_library(self, *_):
        if not hasattr(self, "category_filter"):
            return
        selected_category = self.category_filter.currentData() or ""
        self.category_filter.blockSignals(True); self.category_filter.clear(); self.category_filter.addItem(self.nt("all"), "")
        for name in store.categories():
            self.category_filter.addItem(localize_category(name, self.language), name)
        found = self.category_filter.findData(selected_category)
        self.category_filter.setCurrentIndex(max(0, found)); self.category_filter.blockSignals(False)
        records = store.recipes(self.search.text(), self.favorite_filter.isChecked(), self.category_filter.currentData() or "", self.sort.currentData())
        if self.group_categories.isChecked():
            records.sort(key=lambda record: record["category"] or "Sonstiges")
        self.list.blockSignals(True); self.list.clear()
        selected = None
        current_group = None
        first_recipe = None
        for record in records:
            category = record["category"] or "Sonstiges"
            if self.group_categories.isChecked() and category != current_group:
                count = sum((row["category"] or "Sonstiges") == category for row in records)
                header = QListWidgetItem(f"{localize_category(category, self.language)} ({count})")
                font = header.font(); font.setBold(True); font.setPixelSize(15); header.setFont(font)
                header.setFlags(Qt.ItemIsEnabled); header.setSizeHint(QSize(340, 40))
                header.setForeground(QApplication.palette().color(QPalette.Highlight)); self.list.addItem(header)
                current_group = category
            item = QListWidgetItem(f"{'★ ' if record['favorite'] else ''}{record['title']}\n{localize_category(record['category'], self.language)} · {record['duration_minutes'] or '—'} {t('min', self.language)}\n{', '.join(record['tags'][:3])}")
            item.setSizeHint(QSize(340, 118)); self.preview(item, record.get("image_url"), record.get("emoji") or "🍽️")
            item.setData(Qt.UserRole, record["id"]); self.list.addItem(item)
            if first_recipe is None:
                first_recipe = item
            if record["id"] == self.current_id:
                selected = item
        if selected is None:
            selected = first_recipe
        self.list.setCurrentItem(selected); self.list.blockSignals(False)
        self.show_selected(selected)

    def show_selected(self, item, *_):
        self.current_id = item.data(Qt.UserRole) if item else None
        data = store.recipe(self.current_id) if self.current_id else None
        self.recipe_category.blockSignals(True); self.recipe_category.clear()
        for name in store.categories():
            self.recipe_category.addItem(localize_category(name, self.language), name)
        self.recipe_category.setCurrentIndex(self.recipe_category.findData(data["category"]) if data else -1)
        self.recipe_category.setEnabled(bool(data) and not self.busy); self.recipe_category.blockSignals(False)
        for widget in (self.favorite_button, self.tried_button, self.edit_button, self.delete_button, self.reprocess_button,
                       getattr(self, "cook_button", None), getattr(self, "source_button", None),
                       getattr(self, "copy_button", None), getattr(self, "share_button", None)):
            if widget is not None:
                widget.setEnabled(bool(data) and (not self.busy or widget in (self.favorite_button, self.tried_button)))
        if not data:
            self.detail.setPlainText(t("no_recipes_title", self.language)); return
        esc = lambda value: html.escape(str(value or ""))
        facts = " · ".join(value for value in [localize_category(data["category"], self.language),
            f"{data['duration_minutes']} {t('min', self.language)}" if data['duration_minutes'] else "",
            data["servings"], f"{data['calories']} kcal" if data['calories'] else ""] if value)
        self.detail.setHtml(f"<h1>{esc(data['emoji'])} {esc(data['title'])}</h1><p>{esc(facts)}</p>"
            + f"<h2>{esc(t('ingredients', self.language))}</h2><ul>" + "".join(f"<li>{esc(item)}</li>" for item in data["ingredients"]) + "</ul>"
            + f"<h2>{esc(t('instructions', self.language))}</h2><ol>" + "".join(f"<li>{esc(item).replace(chr(10), '<br>')}</li>" for item in data["instructions"]) + "</ol>"
            + "<p>" + esc(", ".join(data["tags"])) + "</p>")
        self.favorite_button.setText(("★ " if data["favorite"] else "☆ ") + t("favorites", self.language))
        tried = t("status_tried", self.language)
        self.tried_button.setText(("✓ " if data["tried"] else "○ ") + tried[:1].upper() + tried[1:])

    def show_recipe(self, rid):
        self.tabs.setCurrentIndex(1); self.search.clear(); self.favorite_filter.setChecked(False); self.category_filter.setCurrentIndex(0)
        self.current_id = rid; self.refresh_library()

    def assign_category(self, *_):
        category = self.recipe_category.currentData()
        if self.current_id and category and not self.busy:
            store.update_recipe(self.current_id, {"category": category})
            self.refresh_library(); self.status.setText(self.nt("saved"))

    def toggle_favorite(self):
        data = store.recipe(self.current_id) if self.current_id else None
        if data:
            store.update_recipe(self.current_id, {"favorite": not data["favorite"]}); self.refresh_library()

    def toggle_tried(self):
        data = store.recipe(self.current_id) if self.current_id else None
        if data:
            store.update_recipe(self.current_id, {"tried": not data["tried"]}); self.refresh_library()

    def edit(self):
        if self.busy or not self.current_id:
            return
        dialog = Editor(self, store.recipe(self.current_id)); dialog.exec(); self.refresh_library()

    def new_recipe(self):
        if self.busy:
            return
        rid = store.new_recipe(); self.show_recipe(rid)
        dialog = Editor(self, store.recipe(rid))
        if dialog.exec() != QDialog.Accepted:
            store.delete_recipe(rid)
        self.refresh_library()

    def delete(self):
        if self.busy or not self.current_id:
            return
        if QMessageBox.question(self, self.nt("delete"), self.nt("confirm_delete"), QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
            store.delete_recipe(self.current_id); self.current_id = None; self.refresh_library()

    def recipe_text(self):
        data = store.recipe(self.current_id) if self.current_id else None
        if not data:
            return ""
        return data["title"] + "\n\n" + t("ingredients", self.language) + "\n" + "\n".join("- " + item for item in data["ingredients"]) + "\n\n" + t("instructions", self.language) + "\n" + "\n".join(f"{index}. {item}" for index, item in enumerate(data["instructions"], 1))

    def copy_recipe(self):
        QApplication.clipboard().setText(self.recipe_text())

    def open_link(self, field):
        data = store.recipe(self.current_id) if self.current_id else None
        if data and QUrl(data[field]).scheme() in ("http", "https"):
            QDesktopServices.openUrl(QUrl(data[field]))

    def open_source(self):
        self.open_link("source_url")

    def open_image(self):
        self.open_link("image_url")

    def share(self):
        text = self.recipe_text()
        if text:
            phone = re.sub(r"\D", "", store.setting("phone_number"))
            QDesktopServices.openUrl(QUrl("https://wa.me/" + phone + "?text=" + quote(text)))

    def cook(self):
        if self.current_id:
            CookingDialog(self, store.recipe(self.current_id)).exec()

    def run_job(self, function, callback, message="working", failure_callback=None, use_ai=False):
        if self.busy:
            return False
        self.busy = True; self.status.setText(self.nt(message)); self.set_busy(True)
        self.show_busy(message)
        self.on_job_failure = failure_callback
        def work():
            if use_ai:
                if store.configuration()["provider"] in ("llamacpp", "lmstudio", "ollama"):
                    self.job_progress.emit("progress_starting_ai")
                local_runtime.ensure()
            return function()
        worker = Worker(work); self.worker = worker
        worker.signals.finished.connect(lambda result: self.finish_job(callback, result))
        worker.signals.failed.connect(self.fail_job); self.pool.start(worker)
        return True

    def set_busy(self, busy):
        for widget in (self.provider, self.model, self.key, self.custom_url, self.select_button, self.check_button, self.layout_language,
                       self.import_button, self.video_button, self.new_button, self.edit_button, self.delete_button, self.reprocess_button):
            widget.setEnabled(not busy)
        if not busy:
            self.show_selected(self.list.currentItem())

    def finish_job(self, callback, result):
        self.busy = False; self.set_busy(False); self.worker = None
        self.status.setText(self.nt("done")); callback(result)
        self.end_busy(self.status.text(), failed=getattr(self, "job_warning", False)); self.job_warning = False
        self.on_job_failure = None
        self.stop_ai_if_hidden()

    def fail_job(self, reason="failed"):
        self.busy = False; self.set_busy(False); self.worker = None; self.status.setText(self.nt(reason))
        self.end_busy(self.nt(reason), failed=True)
        # A model may have loaded successfully before its language probe failed.
        self.selected_config = store.configuration(); self.fill_targets(store.targets()); self.model_line.setText(self.model_status())
        failed = getattr(self, "on_job_failure", None); self.on_job_failure = None
        if failed:
            failed(reason)
        self.stop_ai_if_hidden()

    def model_status(self):
        if hasattr(self, "provider") and self.provider.count():
            provider = self.provider.currentData()
            model = self.model.currentText().strip() if hasattr(self, "model") else ""
        else:
            provider = store.setting("ai_provider")
            model = store.setting("ai_model")
        if not provider or not store.setting("ai_provider"):
            return self.nt("no_ai")
        cfg = PROVIDERS.get(provider, {})
        name = cfg.get("name", provider)
        return f"{name} · {model}" if model else name

    def fill_provider_list(self):
        current_data = self.provider.currentData() if hasattr(self, "provider") and self.provider.count() else self.selected_config.get("provider", "llamacpp")
        self.provider.blockSignals(True)
        self.provider.clear()
        colors = get_theme_colors()
        muted_color = QColor(colors.get("muted", "#867658"))
        fg_color = QColor(colors.get("foreground", "#e0e0e0"))

        for code, cfg in PROVIDERS.items():
            ready, status_key = get_provider_status(code)
            base_name = cfg["name"]

            if ready:
                label = base_name
                color = fg_color
                is_enabled = True
            else:
                reason = t(status_key, self.language)
                label = f"{base_name} ({reason})"
                color = muted_color
                if cfg.get("type") == "local" or code in ("codex", "claude"):
                    is_enabled = False
                else:
                    is_enabled = True

            self.provider.addItem(label, code)
            item = self.provider.model().item(self.provider.count() - 1)
            item.setEnabled(is_enabled)
            item.setForeground(QBrush(color))
            if not ready:
                item.setToolTip(t(f"{status_key}_tip", self.language))

        idx = self.provider.findData(current_data)
        if idx >= 0:
            self.provider.setCurrentIndex(idx)
        self.provider.blockSignals(False)

    def provider_changed(self, *_):
        self.key.clear(); self.fill_models()
        self.release_gpu_in_background(local_runtime.release_unselected, self.provider.currentData())

    def release_gpu_in_background(self, function, *args):
        """Free GPU memory off the UI thread; the single-thread pool keeps it ordered with AI jobs."""
        worker = Worker(lambda: function(*args)); self.ai_workers.append(worker)
        def finished(*_):
            if worker in self.ai_workers:
                self.ai_workers.remove(worker)
        worker.signals.finished.connect(finished); worker.signals.failed.connect(finished)
        self.pool.start(worker)

    def fill_models(self):
        provider = self.provider.currentData()
        cfg = get_providers_dict()[provider]
        models = get_online_models(provider, store.setting(f"{provider}_api_key")) or cfg["models"]
        saved = store.setting(f"{provider}_model") or (self.selected_config["model"] if provider == self.selected_config["provider"] else cfg["default_model"])
        if provider in ("lmstudio", "ollama") and models and saved not in models:
            # A model saved earlier may have been deleted from the local library.
            saved = models[0]
        self.model.blockSignals(True); self.model.clear(); self.model.addItems(models)
        self.model.setCurrentText(saved); self.model.blockSignals(False)
        needs_key = cfg.get("needs_key") or provider == "custom"
        self.key.setVisible(bool(needs_key)); self.key_label.setVisible(bool(needs_key))
        self.key.setPlaceholderText(mask_key(store.setting(f"{provider}_api_key")))
        self.custom_url.setVisible(provider == "custom"); self.custom_url_label.setVisible(provider == "custom")
        self.provider_help.setText(cfg["help"])
        self.model_edited()

    def model_edited(self, *_):
        provider = self.provider.currentData()
        model = self.model.currentText().strip() if hasattr(self, "model") else ""
        cfg = PROVIDERS.get(provider, {})
        if provider in PROVIDERS and model:
            values = {"ai_provider": provider, f"{provider}_model": model, "ai_model": model}
            if hasattr(self, "key"):
                key = self.key.text().strip()
                if key and cfg.get("needs_key"):
                    values[f"{provider}_api_key"] = key
                    values["ai_api_key"] = key
            if provider == "custom" and hasattr(self, "custom_url"):
                url = self.custom_url.text().strip()
                if url:
                    values["custom_base_url"] = url
            store.save_settings(values)
            self.selected_config = store.configuration()
        if hasattr(self, "model_line"):
            self.model_line.setText(self.model_status())
        self.fill_targets(store.targets())
        if cfg.get("needs_key"):
            has_key = bool(self.key.text().strip() or store.setting(f"{provider}_api_key"))
            self.select_button.setEnabled(has_key and not self.busy)
        else:
            self.select_button.setEnabled(not self.busy)

    def fill_targets(self, languages):
        selected = store.setting("recipe_target_language", "en")
        for combo in (self.target, self.settings_target):
            combo.blockSignals(True); combo.clear()
            for row in languages:
                combo.addItem(row["name"], row["code"])
            index = combo.findData(selected)
            combo.setCurrentIndex(index if index >= 0 else -1); combo.setEnabled(bool(languages)); combo.blockSignals(False)
        self.fill_interface_languages(languages)
        self.use_ai.setEnabled(True)
        self.language_status.setText(", ".join(row["name"] for row in languages) if languages else self.nt("target_hint"))
        self.update_ai_state(languages)

    def update_ai_state(self, languages):
        """Hint and 'Check languages' only appear while a selected model cannot translate yet."""
        configured = bool(store.setting("ai_provider"))
        ready = configured and bool(languages)
        self.ai_hint.setVisible(not ready)
        self.ai_hint.setText(self.nt("target_hint") if configured else self.nt("ai_off_hint"))
        self.check_button.setVisible(configured and not ready)

    def select_and_check(self):
        provider = self.provider.currentData(); model = self.model.currentText().strip()
        key = self.key.text(); url = self.custom_url.text().strip()
        def work():
            # Frees every other runtime (and waits for VRAM) before a local model loads.
            local_runtime.ensure(provider=provider, model=model)
            store.select_model(provider, model, key, url)
            return store.check_languages()
        def finished(result):
            self.selected_config = store.configuration(); self.fill_targets(result["target_languages"])
            self.fill_provider_list()
            self.model_line.setText(self.model_status()); self.key.clear()
            # Clearing the edit field fires model_edited; restore verified choices.
            self.fill_targets(result["target_languages"])
            self.use_ai.setChecked(store.setting("ai_enabled", "1") != "0")
            self.status.setText(self.nt("model_ready"))
        self.run_job(work, finished, "checking", use_ai=False)

    def target_changed(self, *_):
        code = self.target.currentData()
        if code:
            store.save_settings({"recipe_target_language": code})
            if store.setting("ai_provider"):
                self.use_ai.setChecked(True)
            self.fill_targets(store.targets())

    def settings_target_changed(self, *_):
        code = self.settings_target.currentData()
        if code:
            store.save_settings({"recipe_target_language": code})
            if store.setting("ai_provider"):
                self.use_ai.setChecked(True)
            self.fill_targets(store.targets())

    def fill_interface_languages(self, languages):
        # Shipped translations work without a model; verified targets can be generated by the model.
        choices = {**LANGUAGES, **{code: TARGET_LANGUAGES[code] for code in interface_languages.available()},
                   **{row["code"]: row["name"] for row in languages}}
        choices[self.language] = TARGET_LANGUAGES[self.language]
        self.layout_language.blockSignals(True); self.layout_language.clear()
        for code, name in choices.items():
            self.layout_language.addItem(name, code)
        self.layout_language.setCurrentIndex(self.layout_language.findData(self.language)); self.layout_language.blockSignals(False)

    def activate_interface(self, code):
        if not interface_languages.load(code):
            raise ValueError("Interface translation missing")
        self.language = code; store.save_settings({"ui_language": code, "recipe_target_language": code})
        self.layout_language.blockSignals(True); self.layout_language.setCurrentIndex(self.layout_language.findData(code)); self.layout_language.blockSignals(False)
        self.setLayoutDirection(Qt.RightToLeft if code == "ar" else Qt.LeftToRight)
        self.retranslate(); self.refresh_library()
        self.fill_targets(store.targets())
        self.fill_provider_list()
        self.video_query.setPlaceholderText(t("video_placeholder", code))

    def layout_changed(self, *_):
        code = self.layout_language.currentData()
        if not code or code == self.language:
            return
        if interface_languages.load(code):
            self.activate_interface(code)
        else:
            self.layout_language.blockSignals(True); self.layout_language.setCurrentIndex(self.layout_language.findData(self.language)); self.layout_language.blockSignals(False)
            self.run_job(lambda: interface_languages.generate(code), self.activate_interface, use_ai=True)

    def import_link(self):
        url = self.url.text().strip(); target = self.target.currentData() or store.setting("recipe_target_language", "en"); ai = self.use_ai.isChecked()
        if not url:
            return
        def done(result):
            self.url.clear(); self.show_recipe(result["id"])
            self.status.setText(self.nt("duplicate" if result["duplicate"] else "raw" if result["without_ai"] else "import_done"))
            if result["without_ai"]:
                # Say why AI processing did not happen instead of a generic notice.
                reason = result.get("ai_error") or "raw"
                self.job_warning = True
                self.status.setText(self.nt("raw") + " — " + self.nt(reason) if reason != "raw" else self.nt("raw"))
                self.show_translation_failure(reason)
        self.run_job(lambda: store.import_recipe(url, ai, target, progress=self.job_progress.emit), done, "importing", use_ai=ai)

    def reprocess(self):
        if self.current_id:
            rid = self.current_id
            target = self.target.currentData() or store.setting("recipe_target_language", "en")
            self.run_job(lambda: store.reprocess(rid, target, progress=self.job_progress.emit), self.show_recipe, "reprocessing",
                         failure_callback=self.show_translation_failure, use_ai=True)
        else:
            self.tabs.setCurrentIndex(2); self.status.setText(self.nt("target_hint"))

    def show_translation_failure(self, reason):
        if not self.isVisible():
            return
        self.failure_notice = QMessageBox(QMessageBox.Warning, self.tr("use_ai_label"), self.nt(reason), QMessageBox.Ok, self)
        self.failure_notice.setAttribute(Qt.WA_DeleteOnClose)
        self.failure_notice.open()

    def video_search(self):
        query = self.video_query.text().strip()
        if not query:
            return
        def done(results):
            self.video_rows = results
            self.video_group.blockSignals(True); self.video_group.clear(); self.video_group.addItem(self.nt("all_channels"), "")
            for group in sorted({row.get("group", "YouTube") for row in results}):
                self.video_group.addItem(group, group)
            self.video_group.blockSignals(False); self.render_videos()
        count, language = self.video_count.value(), self.video_language.currentData() or ""
        store.save_settings({"video_result_count": count, "video_search_language": language})
        self.run_job(lambda: store.search_videos(query, count, language), done, "searching")

    def clear_video_search(self):
        self.video_rows = []
        self.video_query.clear(); self.video_filter.clear(); self.url.clear()
        self.video_group.blockSignals(True)
        self.video_group.clear(); self.video_group.addItem(self.nt("all_channels"), "")
        self.video_group.blockSignals(False)
        self.video_count.setValue(10); self.video_language.setCurrentIndex(0)
        self.video_results.clear(); self.video_selection_changed(None)
        store.save_settings({"video_result_count": "10", "video_search_language": ""})

    def render_videos(self, *_):
        self.video_results.clear()
        query = self.video_filter.text().casefold(); group = self.video_group.currentData()
        for row in sorted(self.video_rows, key=lambda row: row.get("group", "")):
            if query not in row["title"].casefold() or (group and row.get("group", "YouTube") != group):
                continue
            item = QListWidgetItem(row["title"] + "\n" + row.get("group", "YouTube") + " · " + video_duration(row.get("duration")))
            item.setData(Qt.UserRole, row["url"]); item.setSizeHint(QSize(340, 106))
            item.setToolTip(row["title"] + " · " + video_duration(row.get("duration")))
            self.preview(item, row.get("thumbnail"), "🎬"); self.video_results.addItem(item)
        self.video_results.resize_cards()
        self.video_filter_row.setVisible(bool(self.video_rows))
        self.video_results.viewport().update()

    def preview(self, item, url, emoji):
        pixmap = QPixmap(120, 80); pixmap.fill(QApplication.palette().color(QPalette.Button))
        painter = QPainter(pixmap); font = painter.font(); font.setPixelSize(34); painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignCenter, emoji); painter.end()
        item.setIcon(self.previews.get(url, QIcon(pixmap)))
        item.setData(Qt.UserRole + 1, url)
        if not url or url in self.previews or url in self.preview_pending or QUrl(url).scheme() not in ("http", "https"):
            return
        self.preview_pending.add(url)
        request = QNetworkRequest(QUrl(url)); request.setTransferTimeout(10000)
        reply = self.network.get(request)
        def loaded():
            self.preview_pending.discard(url)
            image = QPixmap()
            if reply.error() == QNetworkReply.NoError and image.loadFromData(bytes(reply.readAll())):
                icon = QIcon(image.scaled(120, 80, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)); self.previews[url] = icon
                for listing in (self.list, self.video_results):
                    for index in range(listing.count()):
                        current = listing.item(index)
                        if current.data(Qt.UserRole + 1) == url:
                            current.setIcon(icon)
            reply.deleteLater()
        reply.downloadProgress.connect(lambda received, total: reply.abort() if received > 5_000_000 or total > 5_000_000 else None)
        reply.finished.connect(loaded)

    def pick_video(self, item):
        if item:
            self.url.setText(item.data(Qt.UserRole)); self.url.setFocus()
            self.status.setText(self.nt("video_picked"))

    def video_selection_changed(self, item, *_):
        self.video_preview_button.setEnabled(bool(item))
        # Keyboard navigation through the cards also fills the import field.
        if item and self.video_results.hasFocus():
            self.pick_video(item); self.video_results.setFocus()

    def preview_video(self, item=None):
        if not isinstance(item, QListWidgetItem):
            item = self.video_results.currentItem()
        if item is None:
            return
        url = QUrl(item.data(Qt.UserRole))
        if url.scheme() == "https" and url.host() in ("youtube.com", "www.youtube.com", "youtu.be"):
            if not QDesktopServices.openUrl(url):
                self.status.setText(self.nt("failed"))

    def save_phone(self):
        try:
            value = store.normalize_phone(self.phone.text()); store.save_settings({"phone_number": value}); self.phone.setText(value)
            self.status.setText(self.nt("saved"))
        except ValueError:
            self.status.setText(self.nt("failed"))

    def add_category(self):
        name, okay = QInputDialog.getText(self, self.nt("add_category"), self.tr("category_label"))
        if okay:
            try:
                store.add_category(name); self.refresh_library()
            except ValueError:
                self.status.setText(self.nt("failed"))

    def rename_category(self):
        old, okay = QInputDialog.getItem(self, self.nt("rename_category"), self.tr("category_label"), [name for name in store.categories() if name != "Sonstiges"], 0, False)
        if not okay or not old:
            return
        new, okay = QInputDialog.getText(self, self.nt("rename"), self.tr("category_label"), text=old)
        if okay:
            try:
                store.rename_category(old, new); self.refresh_library()
            except ValueError:
                self.status.setText(self.nt("failed"))

    def delete_category(self):
        name, okay = QInputDialog.getItem(self, self.nt("delete_category"), self.tr("category_label"), [name for name in store.categories() if name != "Sonstiges"], 0, False)
        if okay and name:
            store.remove_category(name); self.refresh_library()

    def backup(self):
        if self.busy:
            return
        filename, _ = QFileDialog.getSaveFileName(self, self.nt("backup"), "recipes-backup.db", "SQLite (*.db)")
        if filename:
            try:
                store.backup_database(filename); self.status.setText(self.nt("backup_done"))
            except (ValueError, OSError):
                self.status.setText(self.nt("failed"))

    def export(self):
        filename, _ = QFileDialog.getSaveFileName(self, self.nt("export"), "recipes.json", "JSON (*.json)")
        if filename:
            try:
                store.export_recipes(filename); self.status.setText(self.nt("saved"))
            except OSError:
                self.status.setText(self.nt("failed"))

    def restore(self):
        if self.busy:
            return
        filename, _ = QFileDialog.getOpenFileName(self, self.nt("restore"), "", "JSON (*.json)")
        if filename:
            try:
                count = store.restore_recipes(filename); self.refresh_library(); self.status.setText(f"{self.nt('restore_done')}: {count}")
            except (ValueError, OSError):
                self.status.setText(self.nt("failed"))

    def reset(self):
        if self.busy:
            return
        if QMessageBox.warning(self, self.nt("reset"), self.nt("confirm_reset"), QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
            store.reset_all("delete-all"); self.current_id = None; self.phone.clear(); self.setup_pending = True
            self.key.clear(); self.custom_url.clear(); self.use_ai.setChecked(False)
            self.provider.setCurrentIndex(self.provider.findData("llamacpp")); self.fill_models(); self.fill_targets([])
            self.layout_language.setCurrentIndex(self.layout_language.findData("en")); self.language = "en"
            store.initialize(); self.retranslate(); self.refresh_library(); self.status.setText(self.nt("done"))
            self.clear_video_search()

    def show_setup(self):
        if self.busy:
            return
        self.clear_video_search()
        dialog = QDialog(self); dialog.setWindowTitle(self.nt("welcome")); dialog.resize(540, 340)
        layout = QVBoxLayout(dialog)
        intro = QLabel(self.nt("setup_intro")); intro.setWordWrap(True); intro.setTextFormat(Qt.PlainText); layout.addWidget(intro)
        languages = QComboBox()
        for code, name in {**LANGUAGES, **{code: TARGET_LANGUAGES[code] for code in interface_languages.available()}}.items():
            languages.addItem(name, code)
        languages.setCurrentIndex(languages.findData(self.language)); layout.addWidget(languages)
        choices = QComboBox(); choices.addItem(self.nt("no_ai"), "none")
        from .cli_providers import detected
        signed_in = detected()
        for provider in signed_in:
            choices.addItem(self.nt(provider) + " ✓", provider)
        choices.addItem(self.nt("local"), "llamacpp"); layout.addWidget(choices)
        if signed_in:
            choices.setCurrentIndex(1)
        help_label = QLabel(self.nt("setup_help")); help_label.setWordWrap(True); help_label.setTextFormat(Qt.PlainText); layout.addWidget(help_label)
        finish = QPushButton(self.nt("finish")); layout.addWidget(finish)
        def apply():
            self.activate_interface(languages.currentData())
            selection = choices.currentData()
            store.save_settings({"native_setup_done": "1", "ai_enabled": "0" if selection == "none" else "1"})
            if selection == "none":
                store.save_settings({"ai_provider": "", "ai_model": "", "verified_target_languages": "",
                                     **{f"{provider}_model": "" for provider in PROVIDERS}})
                self.selected_config = store.configuration()
                self.use_ai.setChecked(False)
                self.fill_targets([])
                self.model_line.setText(self.model_status())
            self.setup_pending = False; dialog.accept()
            if selection != "none":
                self.provider.setCurrentIndex(self.provider.findData(selection)); self.tabs.setCurrentIndex(2); self.select_and_check()
        finish.clicked.connect(apply); dialog.exec()

    def reveal(self):
        self.tabs.setCurrentIndex(0)
        self.show(); self.raise_(); self.activateWindow()
        if self.setup_pending:
            self.setup_pending = False; QTimer.singleShot(50, self.show_setup)
        elif not self.busy and store.setting("ai_provider") and store.languages_need_check():
            self.run_job(store.check_languages, self.restore_languages, "checking", use_ai=True)

    def restore_languages(self, result):
        self.fill_targets(result["target_languages"] or store.targets())
        self.status.setText(self.nt("model_ready") if result["target_languages"] else self.nt("failed"))

    def hideEvent(self, event):
        self.stop_ai_pending = True
        self.stop_ai_if_hidden()
        super().hideEvent(event)

    def changeEvent(self, event):
        if event.type() == QEvent.WindowStateChange:
            if self.isMinimized():
                self.stop_ai_pending = True
                self.stop_ai_if_hidden()
        super().changeEvent(event)

    def closeEvent(self, event):
        self.hide(); event.ignore()

    def reject(self):
        self.hide()

    def hide(self):
        for child in self.findChildren(QDialog):
            if child.isVisible():
                child.reject()
        super().hide()

    def stop_ai_if_hidden(self):
        if self.isVisible() and not self.isMinimized():
            self.stop_ai_pending = False
            return
        if self.busy or not self.stop_ai_pending:
            return
        self.stop_ai_pending = False
        self.release_gpu_in_background(local_runtime.stop)


class Controller(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.UserAccessOption)
        path = str(socket_path())
        # A live instance is protected by systemd; stale sockets survive crashes.
        from .native_ipc import send
        try:
            send("ping")
        except (OSError, ValueError):
            QLocalServer.removeServer(path)
        else:
            raise RuntimeError("Simple Recipes is already running")
        if not self.server.listen(path):
            raise RuntimeError("Could not open the private recipe control socket")
        self.server.newConnection.connect(self.accept)

    def accept(self):
        while self.server.hasPendingConnections():
            client = self.server.nextPendingConnection()
            client.setProperty("buffer", b"")
            client.readyRead.connect(lambda c=client: self.read(c))
            client.disconnected.connect(client.deleteLater)
            timer = QTimer(client)
            timer.setSingleShot(True)
            timer.timeout.connect(lambda c=client: c.disconnectFromServer() if c.state() != QLocalSocket.UnconnectedState else None)
            timer.start(3000)

    def read(self, client):
        data = bytes(client.property("buffer") or b"") + bytes(client.readAll())
        if len(data) > 4096:
            client.disconnectFromServer(); return
        client.setProperty("buffer", data)
        if b"\n" not in data:
            return
        try:
            request = json.loads(data.split(b"\n", 1)[0])
            command = request.get("command")
            if command == "toggle":
                if self.window.isVisible():
                    self.window.hide()
                else:
                    self.window.reveal()
            elif command == "show":
                self.window.reveal()
            elif command == "hide":
                self.window.hide()
            elif command == "settings":
                self.window.reveal(); self.window.tabs.setCurrentIndex(2)
            elif command == "tab":
                tab_idx = int(request.get("argument", 0))
                self.window.reveal(); self.window.tabs.setCurrentIndex(tab_idx)
            elif command == "recipe":
                rid = int(request.get("argument")); self.window.reveal(); self.window.show_recipe(rid)
            elif command == "quit":
                if self.window.busy:
                    raise ValueError("Busy")
                QTimer.singleShot(0, QApplication.instance().quit)
            elif command != "ping":
                raise ValueError("Unknown command")
            response = {"ready": True, "visible": self.window.isVisible(), "busy": self.window.busy}
        except (ValueError, TypeError, AttributeError):
            response = {"error": "Invalid command or busy"}
        client.write(json.dumps(response).encode() + b"\n"); client.flush(); client.disconnectFromServer()


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--background", action="store_true")
    args = parser.parse_args()
    os.umask(0o077)
    store.initialize()
    app = QApplication(sys.argv[:1]); app.setApplicationName("simple-recipes"); app.setDesktopFileName("simple-recipes")
    app.setQuitOnLastWindowClosed(False)
    app.aboutToQuit.connect(local_runtime.stop)
    apply_theme(app)
    window = RecipeWindow(); controller = Controller(window)
    def on_theme_tick():
        apply_theme(app)
        window.refresh_help()
    theme_timer = QTimer(window); theme_timer.setInterval(10000); theme_timer.timeout.connect(on_theme_tick); theme_timer.start()
    if not args.background:
        QTimer.singleShot(0, window.reveal)
    result = app.exec()
    controller.server.close(); return result


if __name__ == "__main__":
    raise SystemExit(main())
