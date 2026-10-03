"""Native PySide6 recipe library, with direct SQLite access and private local IPC."""
import argparse
import html
import json
import os
from pathlib import Path
import re
import sys
import tomllib
from urllib.parse import quote

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Qt, Signal, Slot, QUrl, QSize
from PySide6.QtGui import QColor, QDesktopServices, QFont, QKeySequence, QPalette, QShortcut, QPixmap, QIcon, QPainter
from PySide6.QtNetwork import QLocalServer, QLocalSocket, QNetworkAccessManager, QNetworkRequest, QNetworkReply
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QListView, QMessageBox, QPushButton, QScrollArea, QSpinBox,
    QSplitter, QStyledItemDelegate, QStyleOptionViewItem, QTabWidget, QTextBrowser, QTextEdit, QVBoxLayout, QWidget)

from . import recipe_store as store
from . import interface_languages
from . import local_runtime
from .ai_config import PROVIDERS, get_providers_dict, mask_key
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


def apply_theme(app):
    theme = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))) / "omarchy/current/theme"
    try:
        colors = tomllib.loads((theme / "colors.toml").read_text())
    except (OSError, ValueError):
        colors = {"background": "#202020", "foreground": "#e0e0e0", "accent": "#d7a66c", "lighter_background": "#303030"}
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
    muted = colors.get("muted", "#867658")
    app.setStyleSheet("""
        QWidget { color: FG; }
        QDialog, QTabWidget::pane, QScrollArea { background: BG; }
        QPushButton { background: SURFACE; border: 1px solid MUTED; border-radius: 7px; padding: 8px 12px; }
        QPushButton:hover { border-color: ACCENT; }
        QPushButton:disabled { color: MUTED; border-color: SURFACE; }
        QLineEdit, QComboBox, QSpinBox { background: SURFACE; border: 1px solid MUTED; border-radius: 6px; padding: 7px; min-height: 20px; }
        QLineEdit { selection-background-color: ACCENT; }
        QTabWidget::pane { border: 0; }
        QTabBar::tab { background: SURFACE; padding: 12px 20px; margin-right: 5px; border-radius: 6px; }
        QTabBar::tab:selected { border-bottom: 2px solid ACCENT; }
        QListWidget { background: BG; border: 0; }
        QListWidget::item { background: SURFACE; color: FG; padding: 8px; border-radius: 8px; }
        QListWidget::item:selected { border: 1px solid ACCENT; }
        QGroupBox { margin-top: 12px; padding-top: 12px; }
        QGroupBox#importCard { background: SURFACE; border: 1px solid MUTED; border-radius: 10px; margin-top: 0; }
        QPushButton#primaryAction { border-color: ACCENT; min-width: 85px; }
        QLabel#hero { font-size: 26px; font-weight: 600; margin-top: 12px; }
        QTextBrowser { background: BG; border: 0; padding: 12px; }
    """.replace("SURFACE", surface).replace("ACCENT", accent).replace("MUTED", muted).replace("FG", fg).replace("BG", bg))



class VideoDelegate(QStyledItemDelegate):
    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        option.decorationPosition = QStyleOptionViewItem.Left
        option.displayAlignment = Qt.AlignLeft | Qt.AlignVCenter


class VideoResults(QListWidget):
    def __init__(self):
        super().__init__()
        self.setViewMode(QListView.IconMode); self.setItemDelegate(VideoDelegate(self))
        self.setFlow(QListView.LeftToRight); self.setWrapping(True)
        self.setResizeMode(QListView.Adjust); self.setMovement(QListView.Static)
        self.setUniformItemSizes(True); self.setWordWrap(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.resize_cards()

    def resize_cards(self):
        width = max(180, (self.viewport().width() - 24) // 2)
        self.setGridSize(QSize(width, 124))
        for index in range(self.count()):
            self.item(index).setSizeHint(QSize(width - 12, 112))


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
        self.resize(660, 650)
        form = QFormLayout()
        self.title = QLineEdit(data["title"]); self.title.setMaxLength(300)
        self.emoji = QLineEdit(data["emoji"]); self.emoji.setMaxLength(8)
        self.category = QComboBox(); self.category.addItems(store.categories()); self.category.setCurrentText(data["category"])
        self.ingredients = QTextEdit(); self.ingredients.setPlainText("\n".join(data["ingredients"]))
        self.instructions = QTextEdit(); self.instructions.setPlainText("\n".join(data["instructions"]))
        self.tags = QLineEdit(", ".join(data["tags"]))
        self.duration = QSpinBox(); self.duration.setRange(0, 100000); self.duration.setValue(data["duration_minutes"] or 0)
        self.calories = QSpinBox(); self.calories.setRange(0, 100000); self.calories.setValue(data["calories"] or 0)
        self.servings = QLineEdit(data["servings"])
        for key, widget in (("title", self.title), ("emoji", self.emoji), ("category_label", self.category),
                            ("ingredients", self.ingredients), ("instructions", self.instructions), ("tags", self.tags),
                            ("duration", self.duration), ("servings", self.servings), ("calories", self.calories)):
            form.addRow(parent.tr(key), widget)
        layout = QVBoxLayout(self); layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText(parent.nt("save"))
        buttons.button(QDialogButtonBox.Cancel).setText(parent.nt("cancel"))
        buttons.accepted.connect(self.save); buttons.rejected.connect(self.reject); layout.addWidget(buttons)

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
        self.setWindowTitle(parent.tr("cooking_mode_title")); self.resize(800, 560)
        layout = QVBoxLayout(self)
        typography = QHBoxLayout(); layout.addLayout(typography)
        typography.addWidget(QLabel(parent.nt("font_size")))
        self.text_size = QSpinBox(); self.text_size.setRange(18, 48); self.text_size.setSuffix(" px")
        try:
            size = int(store.setting("cooking_text_size", "26"))
        except ValueError:
            size = 26
        self.text_size.setValue(size); typography.addWidget(self.text_size); typography.addStretch()
        self.step_label = QLabel(); layout.addWidget(self.step_label)
        self.step = QTextBrowser(); layout.addWidget(self.step)
        self.step.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        row = QHBoxLayout(); layout.addLayout(row)
        self.prev = QPushButton(parent.nt("previous")); self.prev.clicked.connect(lambda: self.move(-1)); row.addWidget(self.prev)
        self.next = QPushButton(parent.nt("next")); self.next.clicked.connect(lambda: self.move(1)); row.addWidget(self.next)
        self.minutes = QSpinBox(); self.minutes.setRange(1, 1440); row.addWidget(self.minutes)
        self.start = QPushButton(parent.tr("timer_start")); self.start.clicked.connect(self.start_timer); row.addWidget(self.start)
        self.timer_label = QLabel(); layout.addWidget(self.timer_label)
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
        self.setup_pending = not store.setting("native_setup_done") and not any(store.setting(key) for key in ("ai_provider", "ai_model", "ui_language", "phone_number"))
        self.ui_texts = []
        self.tab_keys = []
        outer = QVBoxLayout(self)
        self.tabs = QTabWidget(); outer.addWidget(self.tabs)
        self.status = QLabel(); self.status.setWordWrap(True); self.status.setTextFormat(Qt.PlainText); outer.addWidget(self.status)
        self.build_library(); self.build_import(); self.build_settings(); self.build_help()
        pages = {key: self.tabs.widget(index) for index, key in enumerate(self.tab_keys)}
        self.tabs.clear(); self.tab_keys = []
        for key in ("import_tab", "library", "settings", "help"):
            self.add_tab(pages[key], key)
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
        self.refresh_help()

    def build_library(self):
        page = QWidget(); layout = QVBoxLayout(page)
        row = QHBoxLayout(); layout.addLayout(row)
        self.search = QLineEdit(); self.search.textChanged.connect(self.refresh_library); row.addWidget(self.search, 2)
        self.favorite_filter = self.bound(QCheckBox(), "favorites", False); self.favorite_filter.toggled.connect(self.refresh_library); row.addWidget(self.favorite_filter)
        self.category_filter = QComboBox(); self.category_filter.currentIndexChanged.connect(self.refresh_library); row.addWidget(self.category_filter)
        self.sort = QComboBox()
        for sort in ("newest", "oldest", "title", "duration", "calories", "tried"):
            self.sort.addItem(sort, sort)
        self.sort.currentIndexChanged.connect(self.refresh_library); row.addWidget(self.sort)
        self.group_categories = self.bound(QCheckBox(), "group_category"); self.group_categories.setChecked(True); self.group_categories.toggled.connect(self.refresh_library); row.addWidget(self.group_categories)
        split = QSplitter(); layout.addWidget(split, 1)
        self.list = QListWidget(); self.list.setIconSize(QSize(120, 80)); self.list.setSpacing(8); self.list.setWordWrap(True); self.list.currentItemChanged.connect(self.show_selected); split.addWidget(self.list)
        right = QWidget(); detail = QVBoxLayout(right)
        self.detail = QTextBrowser(); self.detail.setOpenExternalLinks(False); detail.addWidget(self.detail, 1)
        category_row = QHBoxLayout(); detail.addLayout(category_row)
        category_row.addWidget(self.label("category_label", False))
        self.recipe_category = QComboBox(); self.recipe_category.setMaximumWidth(260); self.recipe_category.currentIndexChanged.connect(self.assign_category); category_row.addWidget(self.recipe_category); category_row.addStretch()
        self.favorite_button = self.button("favorites", self.toggle_favorite, False)
        self.tried_button = self.button("status_tried", self.toggle_tried, False)
        actions = QHBoxLayout(); detail.addLayout(actions)
        actions.addWidget(self.favorite_button); actions.addWidget(self.tried_button)
        self.edit_button = self.button("edit", self.edit); actions.addWidget(self.edit_button)
        self.delete_button = self.button("delete", self.delete); actions.addWidget(self.delete_button)
        actions2 = QHBoxLayout(); detail.addLayout(actions2)
        actions2.addWidget(self.button("copy", self.copy_recipe))
        actions2.addWidget(self.button("source", self.open_source))
        actions2.addWidget(self.button("cooking_mode_title", self.cook, False))
        actions3 = QHBoxLayout(); detail.addLayout(actions3)
        actions3.addWidget(self.button("share_all", self.share, False))
        self.reprocess_button = self.button("use_ai_label", self.reprocess, False); actions3.addWidget(self.reprocess_button)
        split.addWidget(right); split.setSizes([380, 600])
        bottom = QHBoxLayout(); layout.addLayout(bottom)
        self.new_button = self.button("new", self.new_recipe); bottom.addWidget(self.new_button)
        bottom.addStretch(); bottom.addWidget(self.button("close", self.hide))
        self.add_tab(page, "library")

    def build_import(self):
        page = QWidget(); outer = QVBoxLayout(page); outer.setContentsMargins(16, 10, 16, 10); outer.setSpacing(8)
        hero = self.label("hero_title", False); hero.setTextFormat(Qt.RichText); hero.setObjectName("hero"); outer.addWidget(hero)
        outer.addWidget(self.label("hero_subtitle", False))
        card = QGroupBox(); card.setObjectName("importCard"); layout = QVBoxLayout(card); layout.setContentsMargins(14, 8, 14, 8); layout.setSpacing(6)
        outer.addWidget(card)
        layout.addWidget(self.label("import_label", False))
        row = QHBoxLayout(); layout.addLayout(row)
        self.url = QLineEdit(); self.url.returnPressed.connect(self.import_link); row.addWidget(self.url, 1)
        self.import_button = self.button("import_tab", self.import_link); self.import_button.setObjectName("primaryAction"); row.addWidget(self.import_button)
        options = QHBoxLayout(); layout.addLayout(options)
        self.use_ai = self.bound(QCheckBox(), "use_ai_label", False); self.use_ai.setChecked(bool(store.setting("ai_provider")) and store.setting("ai_enabled", "1") != "0"); options.addWidget(self.use_ai)
        self.use_ai.toggled.connect(lambda checked: store.save_settings({"ai_enabled": "1" if checked else "0"}))
        options.addSpacing(12); options.addWidget(self.label("target_lang_label", False))
        self.target = QComboBox(); self.target.setMinimumWidth(175); self.target.setMaximumWidth(270); self.target.currentIndexChanged.connect(self.target_changed); options.addWidget(self.target); options.addStretch()
        self.model_line = QLabel(); self.model_line.setTextFormat(Qt.PlainText); self.model_line.setWordWrap(True); layout.addWidget(self.model_line)
        tools = QHBoxLayout(); layout.addLayout(tools)
        hint = self.label("target_hint"); tools.addWidget(hint, 1)
        tools.addWidget(self.button("settings", lambda: self.tabs.setCurrentIndex(2)))
        search_card = QGroupBox(); search_card.setObjectName("importCard"); search_layout = QVBoxLayout(search_card); search_layout.setContentsMargins(14, 8, 14, 8); search_layout.setSpacing(6); outer.addWidget(search_card, 1)
        search_layout.addWidget(self.label("video_search"))
        search_row = QHBoxLayout(); search_layout.addLayout(search_row)
        self.video_query = QLineEdit(); self.video_query.setPlaceholderText(t("video_placeholder", self.language)); self.video_query.returnPressed.connect(self.video_search); search_row.addWidget(self.video_query, 1)
        self.video_button = self.button("search", self.video_search); search_row.addWidget(self.video_button)
        search_options = QHBoxLayout(); search_layout.addLayout(search_options)
        search_options.addWidget(self.label("result_count"))
        self.video_count = QSpinBox(); self.video_count.setRange(1, 50); self.video_count.setValue(int(store.setting("video_result_count", "10"))); self.video_count.setMaximumWidth(85); search_options.addWidget(self.video_count)
        search_options.addSpacing(4); search_options.addWidget(self.label("search_language"))
        self.video_language = QComboBox(); self.video_language.addItem(self.nt("all_languages"), "")
        for code, name in TARGET_LANGUAGES.items():
            self.video_language.addItem(name, code)
        self.video_language.setCurrentIndex(max(0, self.video_language.findData(store.setting("video_search_language"))))
        self.video_language.setMaximumWidth(190); search_options.addWidget(self.video_language)
        filters = search_options
        self.video_filter = QLineEdit(); self.video_filter.setMaximumWidth(180); self.video_filter.setPlaceholderText(t("search_placeholder", self.language)); self.video_filter.textChanged.connect(self.render_videos); filters.addWidget(self.video_filter)
        self.video_group = QComboBox(); self.video_group.setMinimumWidth(120); self.video_group.setMaximumWidth(160); self.video_group.addItem(self.nt("all_channels"), ""); self.video_group.currentIndexChanged.connect(self.render_videos); filters.addWidget(self.video_group); filters.addStretch()
        self.video_results = VideoResults(); self.video_results.setIconSize(QSize(120, 80)); self.video_results.setSpacing(8); self.video_results.itemActivated.connect(self.preview_video); search_layout.addWidget(self.video_results, 1)
        video_actions = QHBoxLayout(); search_layout.addLayout(video_actions)
        self.video_preview_button = self.button("preview_video", self.preview_video); self.video_preview_button.setEnabled(False); video_actions.addWidget(self.video_preview_button)
        self.video_pick_button = self.button("choose_video", lambda: self.pick_video(self.video_results.currentItem())); self.video_pick_button.setEnabled(False); video_actions.addWidget(self.video_pick_button); video_actions.addStretch()
        self.video_results.currentItemChanged.connect(self.video_selection_changed)
        self.add_tab(page, "import_tab")

    def build_settings(self):
        page = QWidget(); page_layout = QVBoxLayout(page)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); page_layout.addWidget(scroll)
        content = QWidget(); layout = QVBoxLayout(content); scroll.setWidget(content)
        form = QFormLayout(); form.setFieldGrowthPolicy(QFormLayout.FieldsStayAtSizeHint); layout.addLayout(form)
        self.layout_language = QComboBox()
        for code, name in {**LANGUAGES, **{row["code"]: row["name"] for row in store.targets()}}.items():
            self.layout_language.addItem(name, code)
        self.layout_language.setCurrentIndex(self.layout_language.findData(self.language))
        self.layout_language.currentIndexChanged.connect(self.layout_changed)
        form.addRow(self.label("lang_layout_label", False), self.layout_language)
        self.provider = QComboBox()
        for code, cfg in PROVIDERS.items():
            self.provider.addItem(cfg["name"], code)
        self.provider.setCurrentIndex(self.provider.findData(self.selected_config["provider"]))
        self.provider.currentIndexChanged.connect(self.provider_changed)
        form.addRow(self.label("provider_label", False), self.provider)
        self.model = QComboBox(); self.model.setEditable(True); self.model.currentTextChanged.connect(self.model_edited)
        form.addRow(self.label("model_label", False), self.model)
        self.custom_url = QLineEdit(store.setting("custom_base_url")); self.custom_url.textChanged.connect(self.model_edited)
        self.custom_url_label = self.label("server_url_label", False); form.addRow(self.custom_url_label, self.custom_url)
        self.key = QLineEdit(); self.key.setEchoMode(QLineEdit.Password); self.key.textChanged.connect(self.model_edited)
        self.key_label = self.label("api_key_label", False); form.addRow(self.key_label, self.key)
        self.provider_help = QLabel(); self.provider_help.setTextFormat(Qt.PlainText); self.provider_help.setWordWrap(True); layout.addWidget(self.provider_help)
        self.select_button = self.button("select_check", self.select_and_check); layout.addWidget(self.select_button, 0, Qt.AlignLeft)
        self.settings_target = QComboBox(); self.settings_target.currentIndexChanged.connect(self.settings_target_changed)
        target_form = QFormLayout(); target_form.addRow(self.label("target_lang_label", False), self.settings_target); layout.addLayout(target_form)
        self.language_status = QLabel(); self.language_status.setTextFormat(Qt.PlainText); self.language_status.setWordWrap(True); layout.addWidget(self.language_status)
        layout.addWidget(self.label("privacy"))
        self.phone = QLineEdit(store.setting("phone_number")); phone_form = QFormLayout()
        phone_form.addRow(self.label("phone_label", False), self.phone); layout.addLayout(phone_form)
        self.phone_button = self.button("phone_save_btn", self.save_phone, False); layout.addWidget(self.phone_button, 0, Qt.AlignLeft)
        for key, method in (("add_category", self.add_category), ("rename_category", self.rename_category), ("delete_category", self.delete_category),
                            ("backup", self.backup), ("export", self.export), ("restore", self.restore), ("setup", self.show_setup), ("reset", self.reset)):
            layout.addWidget(self.button(key, method), 0, Qt.AlignLeft)
        layout.addStretch()
        self.add_tab(page, "settings")

    def build_help(self):
        self.help_view = QTextBrowser(); self.help_view.setOpenExternalLinks(True)
        self.add_tab(self.help_view, "help")

    def refresh_help(self):
        guide = Path(__file__).resolve().parent.parent / "USER_GUIDE.md"
        try:
            contents = guide.read_text()
        except OSError:
            contents = self.nt("setup_help")
        self.help_view.setMarkdown("# " + self.nt("help") + "\n\n" + self.nt("setup_help") + "\n\n" + self.nt("privacy") + "\n\n" + contents)

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
        for widget in (self.favorite_button, self.tried_button, self.edit_button, self.delete_button, self.reprocess_button):
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
        self.tried_button.setText(("✓ " if data["tried"] else "") + t("status_tried", self.language))

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
        self.on_job_failure = failure_callback
        def work():
            if use_ai:
                local_runtime.ensure()
            return function()
        worker = Worker(work); self.worker = worker
        worker.signals.finished.connect(lambda result: self.finish_job(callback, result))
        worker.signals.failed.connect(self.fail_job); self.pool.start(worker)
        return True

    def set_busy(self, busy):
        for widget in (self.provider, self.model, self.key, self.custom_url, self.select_button, self.layout_language,
                       self.import_button, self.video_button, self.new_button, self.edit_button, self.delete_button, self.reprocess_button):
            widget.setEnabled(not busy)
        if not busy:
            self.show_selected(self.list.currentItem())

    def finish_job(self, callback, result):
        self.busy = False; self.set_busy(False); self.worker = None
        self.status.setText(self.nt("done")); callback(result)
        self.on_job_failure = None
        self.stop_ai_if_hidden()

    def fail_job(self, reason="failed"):
        self.busy = False; self.set_busy(False); self.worker = None; self.status.setText(self.nt(reason))
        # A model may have loaded successfully before its language probe failed.
        self.selected_config = store.configuration(); self.fill_targets(store.targets()); self.model_line.setText(self.model_status())
        failed = getattr(self, "on_job_failure", None); self.on_job_failure = None
        if failed:
            failed(reason)
        self.stop_ai_if_hidden()

    def model_status(self):
        if not store.setting("ai_provider"):
            return self.nt("no_ai")
        cfg = store.configuration()
        return PROVIDERS[cfg["provider"]]["name"] + " · " + cfg["model"]

    def provider_changed(self, *_):
        self.key.clear(); self.fill_models()

    def fill_models(self):
        provider = self.provider.currentData()
        cfg = get_providers_dict()[provider]
        saved = store.setting(f"{provider}_model") or (self.selected_config["model"] if provider == self.selected_config["provider"] else cfg["default_model"])
        self.model.blockSignals(True); self.model.clear(); self.model.addItems(cfg["models"])
        self.model.setCurrentText(saved); self.model.blockSignals(False)
        needs_key = cfg.get("needs_key") or provider == "custom"
        self.key.setVisible(bool(needs_key)); self.key_label.setVisible(bool(needs_key))
        self.key.setPlaceholderText(mask_key(store.setting(f"{provider}_api_key")))
        self.custom_url.setVisible(provider == "custom"); self.custom_url_label.setVisible(provider == "custom")
        self.provider_help.setText(cfg["help"])
        self.model_edited()

    def model_edited(self, *_):
        self.fill_targets([])

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

    def select_and_check(self):
        provider = self.provider.currentData(); model = self.model.currentText().strip()
        key = self.key.text(); url = self.custom_url.text().strip()
        def work():
            store.select_model(provider, model, key, url)
            return store.check_languages()
        def finished(result):
            self.selected_config = store.configuration(); self.fill_targets(result["target_languages"])
            self.model_line.setText(self.model_status()); self.key.clear()
            # Clearing the edit field fires model_edited; restore verified choices.
            self.fill_targets(result["target_languages"])
            self.use_ai.setChecked(store.setting("ai_enabled", "1") != "0")
            self.status.setText(self.nt("model_ready"))
        self.run_job(work, finished, "checking", use_ai=True)

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
        choices = {**LANGUAGES, **{row["code"]: row["name"] for row in languages}}
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
                self.show_translation_failure("raw")
        self.run_job(lambda: store.import_recipe(url, ai, target), done, use_ai=ai)

    def reprocess(self):
        if self.current_id:
            rid = self.current_id
            target = self.target.currentData() or store.setting("recipe_target_language", "en")
            self.run_job(lambda: store.reprocess(rid, target), self.show_recipe, failure_callback=self.show_translation_failure, use_ai=True)
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
        self.run_job(lambda: store.search_videos(query, count, language), done)

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

    def video_selection_changed(self, item, *_):
        self.video_preview_button.setEnabled(bool(item)); self.video_pick_button.setEnabled(bool(item))

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
        for code, name in {**LANGUAGES, **{code: TARGET_LANGUAGES[code] for code in TARGET_LANGUAGES if code not in LANGUAGES and interface_languages.load(code)}}.items():
            languages.addItem(name, code)
        languages.setCurrentIndex(languages.findData(self.language)); layout.addWidget(languages)
        choices = QComboBox(); choices.addItem(self.nt("no_ai"), "none")
        from .codex_provider import available as codex_available
        if codex_available():
            choices.addItem(self.nt("codex"), "codex")
        choices.addItem(self.nt("local"), "llamacpp"); layout.addWidget(choices)
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

    def closeEvent(self, event):
        self.hide(); event.ignore()

    def reject(self):
        self.hide()

    def hide(self):
        for child in self.findChildren(QDialog):
            if child.isVisible():
                child.reject()
        super().hide()
        self.stop_ai_pending = True
        self.stop_ai_if_hidden()

    def stop_ai_if_hidden(self):
        if self.isVisible():
            self.stop_ai_pending = False
            return
        if self.busy or not self.stop_ai_pending:
            return
        self.stop_ai_pending = False
        worker = Worker(local_runtime.stop); self.ai_workers.append(worker)
        def finished(*_):
            if worker in self.ai_workers:
                self.ai_workers.remove(worker)
        worker.signals.finished.connect(finished); worker.signals.failed.connect(finished)
        self.pool.start(worker)


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
    apply_theme(app)
    window = RecipeWindow(); controller = Controller(window)
    theme_timer = QTimer(window); theme_timer.setInterval(10000); theme_timer.timeout.connect(lambda: apply_theme(app)); theme_timer.start()
    if not args.background:
        QTimer.singleShot(0, window.reveal)
    result = app.exec()
    controller.server.close(); return result


if __name__ == "__main__":
    raise SystemExit(main())
