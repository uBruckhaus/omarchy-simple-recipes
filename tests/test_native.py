import json
import os
import sqlite3
import threading
import time
from unittest.mock import ANY, patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QT_QPA_PLATFORMTHEME"] = ""
os.environ["QT_STYLE_OVERRIDE"] = "Fusion"

from PySide6.QtCore import QThread, Qt
from PySide6.QtWidgets import QApplication
import pytest
from sqlalchemy import select

from app import recipe_store as store
from app.database import SessionLocal
from app.models import Category, Recipe, Setting
from app.native import Controller, Editor, RecipeWindow
from app.native_ipc import send
from app.native_locales import KEYS, TEXT


@pytest.fixture(scope="module")
def qt_app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def native_record():
    store.initialize()
    rid = store.new_recipe()
    store.update_recipe(rid, {"title": "Native test soup", "ingredients": ["2 g salt", "1 L water"],
                             "instructions": ["Add salt.", "Boil for 5 minutes."], "tags": ["test"]})
    yield rid
    store.delete_recipe(rid)


@pytest.fixture
def window(qt_app):
    with SessionLocal() as db:
        original = {row.key: row.value for row in db.scalars(select(Setting))}
    store.save_settings({"ai_provider": "llamacpp", "llamacpp_model": "test-model", "ui_language": "en", "recipe_target_language": "en"})
    with patch("app.native.get_providers_dict", return_value={**__import__('app.ai_config', fromlist=['PROVIDERS']).PROVIDERS}), patch.object(store, "languages_need_check", return_value=False), patch("app.native.local_runtime.ensure"), patch("app.native.local_runtime.stop"):
        instance = RecipeWindow(); instance.setup_pending = False
        yield instance
        instance.pool.waitForDone(1000); qt_app.processEvents(); instance.hide(); instance.deleteLater(); qt_app.processEvents()
    with SessionLocal() as db:
        for row in db.scalars(select(Setting)):
            db.delete(row)
        db.flush()
        db.add_all([Setting(key=key, value=value) for key, value in original.items()]); db.commit()


def wait_events(qt_app, predicate, seconds=3):
    deadline = time.monotonic() + seconds
    while not predicate() and time.monotonic() < deadline:
        qt_app.processEvents(); time.sleep(.005)
    assert predicate()


def test_native_window_shows_sqlite_recipe_and_changes_favorite(window, native_record):
    window.show_recipe(native_record)
    assert "Native test soup" in window.detail.toPlainText()
    assert "1 L water" in window.detail.toPlainText()
    window.toggle_favorite(); assert store.recipe(native_record)["favorite"]
    window.favorite_filter.setChecked(True)
    assert native_record in [window.list.item(i).data(Qt.UserRole) for i in range(window.list.count())]
    window.toggle_tried(); assert store.recipe(native_record)["tried"]


def test_editor_saves_directly_to_same_database(window, native_record):
    editor = Editor(window, store.recipe(native_record))
    editor.title.setText("Edited native soup"); editor.ingredients.setPlainText("3 g salt\n1 L water"); editor.save()
    assert store.recipe(native_record)["title"] == "Edited native soup"
    assert store.recipe(native_record)["ingredients"] == ["3 g salt", "1 L water"]


def test_recipe_html_is_escaped(window, native_record):
    store.update_recipe(native_record, {"title": "<script>native test</script>", "ingredients": ["<b>salt</b>"]})
    window.show_recipe(native_record)
    assert "<script>native test</script>" in window.detail.toPlainText()
    assert "<b>salt</b>" in window.detail.toPlainText()


def test_worker_keeps_gui_responsive_and_callback_runs_on_ui_thread(window, qt_app):
    release = threading.Event(); seen = []
    assert window.run_job(lambda: (release.wait(1), "result")[1], lambda value: seen.append((value, QThread.currentThread() == qt_app.thread())))
    assert window.busy and not window.select_button.isEnabled()
    assert not window.run_job(lambda: "another", lambda _: None)
    window.show(); window.hide(); assert window.busy
    release.set(); wait_events(qt_app, lambda: not window.busy)
    assert seen == [("result", True)]


def test_model_selection_runs_loader_then_lists_verified_languages(window, qt_app):
    with patch.object(store, "select_model") as select_model, patch.object(store, "check_languages", return_value={"target_languages": [
        {"code": "en", "name": "English"}, {"code": "zh", "name": "中文"}]}) as check:
        window.model.setCurrentText("chosen-model"); window.select_and_check()
        wait_events(qt_app, lambda: not window.busy)
    assert select_model.call_args.args[:2] == ("llamacpp", "chosen-model")
    check.assert_called_once()
    assert window.target.findData("zh") >= 0 and window.settings_target.findData("zh") >= 0
    window.model.setCurrentText("another-model")
    assert window.target.count() == 0 and window.use_ai.isEnabled()


def test_all_five_layouts_are_complete_and_switch_in_place(window):
    for language in ("en", "de", "fr", "it", "es"):
        assert set(TEXT[language]) == set(KEYS)
        window.layout_language.setCurrentIndex(window.layout_language.findData(language))
        assert window.tabs.tabText(0) == TEXT[language]["import_tab"]
        assert window.tabs.tabText(1) == TEXT[language]["library"]
        assert store.setting("ui_language") == language


def test_private_ipc_toggle_hides_and_shows_without_http(window, qt_app, monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    controller = Controller(window)
    def command(name):
        result = []; thread = threading.Thread(target=lambda: result.append(send(name)))
        thread.start(); wait_events(qt_app, lambda: not thread.is_alive()); thread.join()
        return result[0]
    assert command("ping")["ready"]
    assert command("toggle")["visible"]
    assert not command("toggle")["visible"]
    assert command("settings")["visible"] and window.tabs.currentIndex() == 2
    controller.server.close()


def test_failed_ai_import_preserves_raw_recipe(native_record):
    url = "https://example.com/native-fallback"
    extracted = {"title": "Raw soup", "ingredients": ["2 g salt"], "instructions": ["Add salt"], "source_url": url}
    with patch.object(store, "extract", return_value=extracted), patch.object(store, "require_translation", side_effect=ValueError("private credential")):
        result = store.import_recipe(url, True)
    assert result["without_ai"] and "private" not in str(result)
    assert store.recipe(result["id"])["title"] == "Raw soup"
    store.delete_recipe(result["id"])


def test_failed_reprocessing_does_not_change_saved_recipe(native_record):
    with patch.object(store, "require_translation", side_effect=ValueError("Unverified")):
        with pytest.raises(ValueError):
            store.reprocess(native_record, "fr")
    assert store.recipe(native_record)["title"] == "Native test soup"


def test_export_restore_backup_and_duplicate_handling(native_record, tmp_path):
    destination = tmp_path / "recipes.json"; backup = tmp_path / "backup.db"
    store.export_recipes(destination); payload = json.loads(destination.read_text())
    assert payload["format"] == "simple-recipes" and "settings" not in payload
    before = len(store.recipes()); assert store.restore_recipes(destination) == 0
    store.backup_database(backup)
    with sqlite3.connect(backup) as connection:
        assert connection.execute("SELECT title FROM recipes WHERE id=?", (native_record,)).fetchone()[0] == "Native test soup"
    store.delete_recipe(native_record)
    assert store.restore_recipes(destination) == 1 and len(store.recipes()) == before
    restored = next(row for row in store.recipes() if row["title"] == "Native test soup")
    store.delete_recipe(restored["id"])


def test_native_reset_clears_legacy_phone_and_every_stored_kind(tmp_path):
    # Exercise destructive reset only against independent SQLite connections.
    from sqlalchemy import create_engine, func
    from sqlalchemy.orm import sessionmaker
    from app.database import Base
    test_engine = create_engine(f"sqlite:///{tmp_path/'reset.db'}")
    Base.metadata.create_all(test_engine); session = sessionmaker(bind=test_engine)
    with session() as db:
        db.add(Recipe(title="Reset fixture", source_url="https://example.com/reset-native"))
        db.add(Setting(key="phone_number", value="+491709999999")); db.add(Category(name="Test", icon="")); db.commit()
    with test_engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE users (id INTEGER PRIMARY KEY, phone_number TEXT)")
        connection.exec_driver_sql("INSERT INTO users(phone_number) VALUES ('+491709999999')")
    with patch.object(store, "SessionLocal", session), patch.object(store, "engine", test_engine):
        with pytest.raises(ValueError):
            store.reset_all("wrong")
        store.reset_all("delete-all")
    with session() as db:
        for model in (Recipe, Category, Setting):
            assert db.scalar(select(func.count()).select_from(model)) == 0
    with test_engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT phone_number FROM users").fetchone()[0] == ""


def test_invalid_restore_is_atomic(native_record, tmp_path):
    filename = tmp_path / "bad.json"
    filename.write_text(json.dumps({"format": "simple-recipes", "version": 1, "recipes": [
        {"title": "Will roll back", "source_url": "https://example.com/native-rollback"}, {"title": None}]}))
    with pytest.raises(ValueError):
        store.restore_recipes(filename)
    assert not store.recipes("Will roll back")


@pytest.mark.parametrize("number,normalized", [("", ""), ("0170 1234567", "+491701234567"), ("0033 123456789", "+33123456789")])
def test_native_phone_normalization(number, normalized):
    assert store.normalize_phone(number) == normalized


def test_import_translates_ingredients_and_steps_in_one_operation():
    url = 'https://example.com/automatic-translation-native'
    extracted = {'title': 'Soup', 'source_url': url, 'raw_text': 'Ingredients:\n2 g salt\nInstructions:\nAdd salt.', 'ingredients': [], 'instructions': []}
    translated = {'title': 'Soupe', 'ingredients': ['2 g de sel'], 'instructions': ['Ajoutez le sel.']}
    with patch.object(store, 'extract', return_value=extracted), patch.object(store, 'require_translation'), patch.object(store, 'normalize', return_value=translated) as normalizer:
        result = store.import_recipe(url, True, 'fr')
    try:
        saved = store.recipe(result['id'])
        assert saved['ingredients'] == ['2 g de sel'] and saved['instructions'] == ['Ajoutez le sel.']
        assert normalizer.call_args.args[0]['ingredients'] == ['2 g salt']
        assert normalizer.call_args.kwargs['target_lang'] == 'fr'
    finally:
        store.delete_recipe(result['id'])


def test_import_starts_first_and_help_is_last(window):
    assert window.tab_keys == ['import_tab', 'library', 'settings', 'help']
    assert window.tabs.currentIndex() == 0
    assert not window.setup_pending


def test_setup_without_ai_clears_previous_selection(window):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QDialog, QPushButton

    window.video_query.setText('lasagne')
    window.video_rows = [{'title': 'Lasagne', 'url': 'https://youtu.be/test', 'group': 'Chef'}]
    window.render_videos()

    def finish_setup():
        dialog = next(child for child in window.findChildren(QDialog) if child.isVisible())
        dialog.findChild(QPushButton).click()

    QTimer.singleShot(0, finish_setup)
    with patch('app.cli_providers.detected', return_value=[]):
        window.show_setup()
    assert store.setting('ai_provider') == ''
    assert store.setting('ai_model') == ''
    assert store.setting('llamacpp_model') == ''
    assert store.setting('ai_enabled') == '0'
    assert not window.use_ai.isChecked()
    assert window.model_line.text() == window.nt('no_ai')
    assert window.target.count() == 0
    assert store.targets() == []
    assert store.setting('native_setup_done') == '1'
    assert window.video_query.text() == ''
    assert window.video_results.count() == 0


def test_reset_clears_youtube_search_and_preferences(window):
    from PySide6.QtWidgets import QMessageBox
    window.video_query.setText('pasta')
    window.video_filter.setText('pasta')
    window.video_count.setValue(30)
    window.video_language.setCurrentIndex(window.video_language.findData('de'))
    window.video_rows = [{'title': 'Pasta', 'url': 'https://youtu.be/test', 'group': 'Chef'}]
    window.video_group.addItem('Chef', 'Chef')
    window.render_videos()
    window.video_results.setCurrentRow(0)
    window.url.setText('https://youtu.be/test')
    with patch.object(QMessageBox, 'warning', return_value=QMessageBox.Yes):
        window.reset()
    assert window.video_query.text() == window.video_filter.text() == window.url.text() == ''
    assert window.video_rows == [] and window.video_results.count() == 0
    assert window.video_group.count() == 1
    assert window.video_count.value() == 10 and window.video_language.currentData() == ''
    assert not window.video_preview_button.isEnabled()
    assert store.setting('video_result_count') == '10' and store.setting('video_search_language') == ''


def test_selecting_target_enables_translation_for_import(window):
    window.use_ai.setChecked(False)
    window.fill_targets([{'code': 'en', 'name': 'English'}, {'code': 'de', 'name': 'Deutsch'}])
    window.target.setCurrentIndex(window.target.findData('de'))
    assert window.use_ai.isChecked()
    assert store.setting('ai_enabled') == '1'
    window.url.setText('https://example.org/german-recipe')
    with patch.object(window, 'run_job') as job:
        window.import_link()
    assert job.call_args.kwargs['use_ai'] is True
    with patch.object(store, 'import_recipe') as importer:
        job.call_args.args[0]()
    importer.assert_called_once_with('https://example.org/german-recipe', True, 'de', progress=ANY)


def test_reprocess_recovers_missing_ingredients_from_source(native_record):
    store.update_recipe(native_record, {'ingredients': [], 'source_url': 'https://example.org/recipe'})
    with SessionLocal() as db:
        db.get(Recipe, native_record).source_url = 'https://example.org/recipe'
        db.commit()
    translated = {'ingredients': ['2 g Salz'], 'instructions': ['Salz hinzufügen.']}
    with patch.object(store, 'require_translation'), patch.object(store, 'extract', return_value={
        'ingredients': ['2 g salt'], 'raw_text': 'Ingredients: 2 g salt'
    }) as extract, patch.object(store, 'normalize', return_value=translated) as normalize:
        store.reprocess(native_record, 'de')
    extract.assert_called_once_with('https://example.org/recipe')
    assert normalize.call_args.args[0]['ingredients'] == ['2 g salt']
    assert normalize.call_args.args[0]['instructions'] == ['Add salt.', 'Boil for 5 minutes.']
    assert normalize.call_args.args[1] == 'Ingredients: 2 g salt'
    assert store.recipe(native_record)['ingredients'] == ['2 g Salz']


def test_verified_languages_survive_cache_clear_and_restore_last_selection(window):
    from app.translation import clear_translation_cache
    store.save_settings({'recipe_target_language': 'ja'})
    expected = [{'code': 'en', 'name': 'English'}, {'code': 'ja', 'name': '日本語'}]
    with patch.object(store, 'available_languages', return_value={'target_languages': expected}):
        store.check_languages()
    clear_translation_cache()
    window.fill_targets(store.targets())
    assert window.target.currentData() == 'ja'
    assert window.settings_target.currentData() == 'ja'
    assert window.target.count() == 2
    store.save_settings({'llamacpp_model': 'different-model'})
    assert store.targets() == []


def test_daily_reopening_does_not_repeat_completed_language_setup():
    original = store.setting('verified_target_languages')
    try:
        store.save_settings({'verified_target_languages': json.dumps({'fingerprint': store.language_fingerprint(store.configuration()), 'checked_at': 0, 'codes': ['ja', 'en']})})
        assert not store.languages_need_check()
    finally:
        store.save_settings({'verified_target_languages': original})


def test_video_search_result_count_language_duration_and_two_columns(window, qt_app):
    window.show(); qt_app.processEvents()
    window.video_query.setText('soup'); window.video_count.setValue(12)
    window.video_language.setCurrentIndex(window.video_language.findData('ja'))
    rows = [{'title': 'Soup video ' + str(i), 'url': 'https://youtube.com/watch?v=test' + str(i), 'duration': 125, 'group': 'Cooking'} for i in range(4)]
    with patch.object(store, 'search_videos', return_value=rows) as search:
        window.video_search(); wait_events(qt_app, lambda: not window.busy)
    search.assert_called_once_with('soup', 12, 'ja')
    assert store.setting('video_result_count') == '12'
    assert store.setting('video_search_language') == 'ja'
    assert '2:05' in window.video_results.item(0).text()
    assert not window.video_results.item(0).icon().isNull()
    qt_app.processEvents()
    first = window.video_results.visualItemRect(window.video_results.item(0))
    second = window.video_results.visualItemRect(window.video_results.item(1))
    assert first.y() == second.y() and second.x() > first.x()
    window.video_filter.setText('video 1'); assert window.video_results.count() == 1


def test_video_search_api_preferences_and_metadata():
    import yt_dlp
    from unittest.mock import MagicMock
    downloader = MagicMock()
    downloader.__enter__.return_value = downloader
    downloader.extract_info.return_value = {'entries': [{'id': 'abc', 'title': 'Soup', 'duration': 3601, 'channel': 'Chef'}]}
    with patch.object(yt_dlp, 'YoutubeDL', return_value=downloader) as factory:
        rows = store.search_videos('soup', 20, 'de')
    assert downloader.extract_info.call_args.args[0] == 'ytsearch20:soup German'
    assert factory.call_args.args[0]['extractor_args']['youtube']['lang'] == ['de']
    assert rows[0]['duration'] == 3601 and 'abc/mqdefault.jpg' in rows[0]['thumbnail']
    with patch.object(yt_dlp, 'YoutubeDL', return_value=downloader) as factory:
        store.search_videos('soup', 5)
    assert 'extractor_args' not in factory.call_args.args[0]
    with pytest.raises(ValueError):
        store.search_videos('soup', 100)


def test_successful_thumbnail_reply_replaces_placeholder(window, qt_app):
    from PySide6.QtCore import QObject, Signal, QByteArray, QBuffer, QIODevice
    from PySide6.QtGui import QPixmap, QColor
    from PySide6.QtNetwork import QNetworkReply
    class Reply(QObject):
        finished = Signal()
        downloadProgress = Signal(int, int)
        def error(self):
            return QNetworkReply.NoError
        def readAll(self):
            return encoded
        def abort(self):
            pass
    image = QPixmap(120, 80); image.fill(QColor('#55aa77'))
    encoded = QByteArray(); buffer = QBuffer(encoded); buffer.open(QIODevice.WriteOnly); image.save(buffer, 'PNG'); buffer.close()
    reply = Reply(window)
    window.video_rows = [{'title': 'Preview', 'url': 'https://youtube.com/watch?v=example', 'thumbnail': 'https://i.ytimg.com/vi/example/mqdefault.jpg'}]
    with patch.object(window.network, 'get', return_value=reply):
        window.render_videos()
    item = window.video_results.item(0)
    placeholder = item.icon().cacheKey()
    reply.finished.emit(); qt_app.processEvents()
    assert item.icon().cacheKey() != placeholder
    assert 'https://i.ytimg.com/vi/example/mqdefault.jpg' in window.previews


def test_preview_opens_youtube_without_importing_and_click_fills_url(window):
    url = 'https://www.youtube.com/watch?v=example'
    window.video_rows = [{'title': 'Soup preview', 'url': url, 'duration': 120}]
    window.render_videos(); item = window.video_results.item(0)
    assert not window.video_preview_button.isEnabled()
    window.video_results.setCurrentItem(item)
    assert window.video_preview_button.isEnabled()
    before = len(store.recipes())
    with patch('app.native.QDesktopServices.openUrl', return_value=True) as open_url:
        window.video_preview_button.click()
        assert open_url.call_args.args[0].toString() == url
        window.video_results.itemActivated.emit(item)
        assert open_url.call_count == 2
    assert len(store.recipes()) == before and not window.url.text()
    window.video_results.itemClicked.emit(item); assert window.url.text() == url
    window.video_filter.setText('no match')
    assert not window.video_preview_button.isEnabled()


def test_category_headers_and_direct_recipe_assignment(window, native_record):
    store.update_recipe(native_record, {'category': 'Suppe'})
    window.show_recipe(native_record)
    headers = [window.list.item(i) for i in range(window.list.count()) if window.list.item(i).data(Qt.UserRole) is None]
    assert any('Soup (' in header.text() for header in headers)
    assert all(not header.flags() & Qt.ItemIsSelectable for header in headers)
    assert window.current_id == native_record
    window.recipe_category.setCurrentIndex(window.recipe_category.findData('Salat'))
    assert store.recipe(native_record)['category'] == 'Salat'
    assert window.current_id == native_record and window.recipe_category.currentData() == 'Salat'
    window.group_categories.setChecked(False)
    assert all(window.list.item(i).data(Qt.UserRole) is not None for i in range(window.list.count()))
    assert not any(key == 'image' for _, key, _ in window.ui_texts)


def test_cooking_text_size_is_larger_selectable_and_remembered(window, native_record):
    from app.native import CookingDialog
    store.save_settings({'cooking_text_size': '26'})
    dialog = CookingDialog(window, store.recipe(native_record))
    assert dialog.text_size.value() == 26 and '26px' in dialog.step.styleSheet()
    assert dialog.step.textInteractionFlags() & Qt.TextSelectableByMouse
    dialog.text_size.setValue(36)
    assert store.setting('cooking_text_size') == '36'
    assert '36px' in dialog.step.styleSheet() and '36px' in dialog.timer_label.styleSheet()
    dialog.move(1)
    assert 'Boil' in dialog.step.toPlainText() and '36px' in dialog.step.styleSheet()
    reopened = CookingDialog(window, store.recipe(native_record))
    assert reopened.text_size.value() == 36
    dialog.close(); reopened.close()


def test_incomplete_recipe_translation_does_not_overwrite_original(native_record):
    original = store.recipe(native_record)
    with patch.object(store, 'require_translation'), patch.object(store, 'normalize', return_value={'title':'Partially translated','instructions':['Übersetzter Schritt']}):
        with pytest.raises(ValueError, match='incomplete'):
            store.reprocess(native_record, 'de')
    saved = store.recipe(native_record)
    assert saved['title'] == original['title'] and saved['ingredients'] == original['ingredients'] and saved['instructions'] == original['instructions']


def test_recipe_retranslation_saves_both_sections_and_uses_interface_units(window, native_record):
    store.save_settings({'ui_language': 'de'})
    translated = {'title':'Suppe','ingredients':['2 g Salz','1 L Wasser'],'instructions':['Salz hinzufügen.','Fünf Minuten kochen.']}
    with patch.object(store, 'require_translation'), patch.object(store, 'normalize', return_value=translated) as normalize:
        store.reprocess(native_record, 'de')
    assert normalize.call_args.kwargs['ui_lang'] == 'de'
    assert store.recipe(native_record)['ingredients'] == translated['ingredients']
    assert store.recipe(native_record)['instructions'] == translated['instructions']


@pytest.fixture
def no_shipped_locales():
    from app import interface_languages
    with patch.object(interface_languages, 'shipped', return_value={}):
        yield


def test_verified_targets_are_available_as_interface_languages(window, qt_app, no_shipped_locales):
    from app import interface_languages
    options = [{'code':'ja','name':'日本語'}, {'code':'pt-BR','name':'Português (Brasil)'}]
    window.fill_targets(options)
    assert window.layout_language.findData('ja') >= 0
    assert window.layout_language.findData('pt-BR') >= 0
    values = dict(interface_languages.source_strings())
    values['native.import_tab'] = 'インポート'; values['ui.ingredients'] = '材料'
    def generate(code):
        store.save_settings({'interface_translation_' + code: json.dumps(values, ensure_ascii=False)})
        return code
    with patch.object(interface_languages, 'generate', side_effect=generate) as translate, patch.object(store, 'targets', return_value=options):
        window.layout_language.setCurrentIndex(window.layout_language.findData('ja'))
        wait_events(qt_app, lambda: not window.busy)
    translate.assert_called_once_with('ja')
    assert window.language == 'ja' and window.tabs.tabText(0) == 'インポート'
    assert window.layout_language.currentData() == 'ja'
    assert store.setting('ui_language') == 'ja'
    assert store.setting('recipe_target_language') == 'ja'
    assert window.target.currentData() == 'ja'
    assert interface_languages.load('ja')
    with patch.object(store, 'targets', return_value=options), patch.object(interface_languages, 'generate') as translate:
        window.layout_language.setCurrentIndex(window.layout_language.findData('en'))
        window.layout_language.setCurrentIndex(window.layout_language.findData('ja'))
    translate.assert_not_called()
    assert window.language == 'ja'


def test_incomplete_interface_translation_keeps_existing_locale(window, qt_app, no_shipped_locales):
    from app import interface_languages
    window.fill_targets([{'code':'sv','name':'Svenska'}])
    with patch.object(interface_languages, 'generate', side_effect=ValueError('Incomplete')):
        window.layout_language.setCurrentIndex(window.layout_language.findData('sv'))
        wait_events(qt_app, lambda: not window.busy)
    assert window.language == 'en' and store.setting('ui_language') == 'en'
    assert window.layout_language.currentData() == 'en'


def test_changing_interface_sets_target_and_target_can_change_independently(window):
    options = [{'code':'en','name':'English'}, {'code':'de','name':'Deutsch'}, {'code':'fr','name':'Français'}]
    with patch.object(store, 'targets', return_value=options):
        window.fill_targets(options)
        window.layout_language.setCurrentIndex(window.layout_language.findData('fr'))
        assert store.setting('ui_language') == 'fr' and store.setting('recipe_target_language') == 'fr'
        assert window.target.currentData() == 'fr' and window.settings_target.currentData() == 'fr'
        window.target.setCurrentIndex(window.target.findData('de'))
        assert store.setting('recipe_target_language') == 'de' and window.language == 'fr'


def test_unreachable_translation_model_shows_clear_error_and_preserves_recipe(window, native_record, qt_app):
    original = store.recipe(native_record)
    window.show(); window.show_recipe(native_record)
    with patch.object(store, 'require_translation', side_effect=ValueError('Server unavailable')):
        window.reprocess_button.click(); wait_events(qt_app, lambda: not window.busy)
    assert window.failure_notice.isVisible()
    assert 'unavailable' in window.failure_notice.text() and 'not changed' in window.failure_notice.text()
    assert store.recipe(native_record)['instructions'] == original['instructions']
    window.failure_notice.close()


def test_translate_button_saves_and_displays_actual_ingredients_and_steps(window, native_record, qt_app):
    window.show_recipe(native_record)
    options = [{'code':'en','name':'English'}, {'code':'it','name':'Italiano'}]
    with patch.object(store, 'targets', return_value=options):
        window.fill_targets(options); window.layout_language.setCurrentIndex(window.layout_language.findData('it'))
    result = {'title':'Zuppa','ingredients':['2 g di sale','1 L di acqua'],'instructions':['Aggiungere il sale.','Far bollire per cinque minuti.']}
    with patch.object(store, 'require_translation'), patch.object(store, 'normalize', return_value=result) as normalize:
        window.reprocess_button.click(); wait_events(qt_app, lambda: not window.busy)
    assert normalize.call_args.kwargs['target_lang'] == 'it'
    assert store.recipe(native_record)['ingredients'] == result['ingredients']
    assert '2 g di sale' in window.detail.toPlainText() and 'Aggiungere il sale.' in window.detail.toPlainText()
    assert window.current_id == native_record


def test_hiding_plugin_stops_local_ai_and_next_ai_job_starts_it(window, qt_app):
    with patch('app.native.local_runtime.stop') as stop, patch('app.native.local_runtime.ensure') as start:
        window.show(); window.hide()
        wait_events(qt_app, lambda: not window.ai_workers)
        stop.assert_called_once()
        window.show(); result = []
        window.run_job(lambda: 'translated', result.append, use_ai=True)
        wait_events(qt_app, lambda: not window.busy)
        start.assert_called_once(); assert result == ['translated']


def test_hide_waits_for_running_translation_before_releasing_gpu(window, qt_app):
    release = threading.Event(); started = threading.Event()
    def translate():
        started.set(); release.wait(2); return 'done'
    with patch('app.native.local_runtime.stop') as stop:
        window.show(); window.run_job(translate, lambda _: None)
        wait_events(qt_app, started.is_set); window.hide()
        assert window.stop_ai_pending and window.busy
        stop.assert_not_called()
        release.set(); wait_events(qt_app, lambda: not window.busy and not window.ai_workers)
        stop.assert_called_once()


def test_local_runtime_starts_llama_loads_saved_model_and_stops_service():
    from app import local_runtime
    cfg = {'provider':'llamacpp','model':'saved-model','base_url':'http://127.0.0.1:8080/v1'}
    started = []
    with patch.object(store,'configuration',return_value=cfg), patch.object(local_runtime,'release_all') as release, \
         patch.object(local_runtime,'llama_models',side_effect=lambda: [] if started else None), \
         patch('app.local_runtime.subprocess.run',side_effect=lambda command, **_: started.append(command)), \
         patch.object(local_runtime,'require_vram'), patch('app.local_runtime.load_model') as load:
        local_runtime.ensure()
    assert started[0] == ['systemctl','--user','start','llama-server.service']
    release.assert_called_once_with(keep='llamacpp')
    load.assert_called_once_with('saved-model','llamacpp')
    local_runtime._used.clear()


def test_import_page_has_food_icon(window):
    assert hasattr(window, "header_food_icon")
    assert not window.header_food_icon.pixmap().isNull()
    assert window.header_food_icon.width() == 38
    assert window.header_food_icon.height() == 38


def test_select_button_is_placed_beneath_model_selection(window):
    model_row, _ = window.ai_form.getWidgetPosition(window.model)
    btn_row, _ = window.ai_form.getWidgetPosition(window.select_button)
    assert btn_row == model_row + 1


def test_local_runtime_ensure_with_target_provider_and_model():
    from app import local_runtime
    cfg = {'provider':'custom','model':'old-model','base_url':'http://127.0.0.1:8080/v1'}
    with patch.object(store,'configuration',return_value=cfg), patch.object(local_runtime,'release_all'), \
         patch.object(local_runtime,'ensure_llamacpp') as ensure_llama:
        local_runtime.ensure(provider='llamacpp', model='new-model')
    ensure_llama.assert_called_once_with('new-model')
    local_runtime._used.clear()


def test_uninstalled_and_unconfigured_providers_are_grayed_out(window):
    # Check that provider items are properly formatted and colored
    model = window.provider.model()
    colors = __import__('app.native', fromlist=['get_theme_colors']).get_theme_colors()
    muted_color = colors.get("muted", "#867658").lower()

    # Find LM Studio (local, not installed)
    with patch('app.ai_config.lmstudio_cli', return_value=''), patch('app.ai_config.lmstudio_running', return_value=False):
        window.fill_provider_list()
    lm_idx = window.provider.findData("lmstudio")
    assert lm_idx >= 0
    lm_item = model.item(lm_idx)
    assert not lm_item.isEnabled()
    assert lm_item.foreground().color().name().lower() == muted_color

    # Find OpenAI (online, not configured)
    openai_idx = window.provider.findData("openai")
    assert openai_idx >= 0
    openai_item = model.item(openai_idx)
    assert openai_item.isEnabled()  # Can be selected to input key
    assert openai_item.foreground().color().name().lower() == muted_color
    assert "nicht eingerichtet" in openai_item.text() or "not configured" in openai_item.text()

    # Find llamacpp (configured/ready)
    llama_idx = window.provider.findData("llamacpp")
    assert llama_idx >= 0
    llama_item = model.item(llama_idx)
    assert llama_item.isEnabled()


def test_entering_api_key_enables_select_button(window):
    openai_idx = window.provider.findData("openai")
    window.provider.setCurrentIndex(openai_idx)
    assert window.provider.currentData() == "openai"
    assert not window.key.isHidden()
    # With no key, select button is disabled
    assert not window.select_button.isEnabled()
    # When key is entered, select button becomes enabled
    window.key.setText("sk-testkey123")
    assert window.select_button.isEnabled()


def test_help_headers_are_colored_by_theme(window):
    colors = __import__('app.native', fromlist=['get_theme_colors']).get_theme_colors()
    accent = colors.get("accent", "#d7a66c").lower()
    window.refresh_help()
    html = window.help_view.toHtml().lower()
    assert f"color:{accent}" in html or f"color: {accent}" in html


def test_settings_help_texts_placed_in_separate_rows_without_overlap(window):
    # Provider combo and its help label
    prov_row, _ = window.ai_form.getWidgetPosition(window.provider)
    prov_help_row, _ = window.ai_form.getWidgetPosition(window.provider_help)
    assert prov_help_row == prov_row + 1

    # Target language combo and its status label (Languages card, below the AI card)
    target_row, _ = window.lang_form.getWidgetPosition(window.settings_target)
    target_status_row, _ = window.lang_form.getWidgetPosition(window.language_status)
    assert target_status_row == target_row + 1


def test_video_results_two_per_row_and_snap_scrolling(window, qt_app):
    window.show(); qt_app.processEvents()
    window.video_rows = [{'title': f'Video #{i}', 'url': f'http://y/{i}', 'duration': 100, 'group': 'Test'} for i in range(16)]
    window.render_videos()
    qt_app.processEvents()

    vr = window.video_results
    assert vr.count() == 16
    # At least one row; taller windows show more rows.
    assert vr.height() >= vr.ROW_HEIGHT

    # Check 2 cards per row: items 0 & 1 on row 0, item 2 on row 1
    r0 = vr.visualItemRect(vr.item(0))
    r1 = vr.visualItemRect(vr.item(1))
    r2 = vr.visualItemRect(vr.item(2))
    assert r0.y() == r1.y()
    assert r1.x() > r0.x()

    # Rows are exactly one card height apart
    assert r2.y() - r0.y() == vr.ROW_HEIGHT

    # Scroll snapping: step down to next row
    vr.verticalScrollBar().setValue(vr.ROW_HEIGHT)
    qt_app.processEvents()
    r2_scrolled = vr.visualItemRect(vr.item(2))
    assert r2_scrolled.y() == 0

    # Snapping helper
    vr.verticalScrollBar().setValue(vr.ROW_HEIGHT + 30)
    vr.snap_to_nearest()
    wait_events(qt_app, lambda: vr.verticalScrollBar().value() == vr.ROW_HEIGHT)
    assert vr.verticalScrollBar().value() == vr.ROW_HEIGHT


def test_changing_provider_and_model_updates_import_page_immediately(window, qt_app):
    # Set to codex first
    codex_idx = window.provider.findData("codex")
    if codex_idx >= 0:
        window.provider.setCurrentIndex(codex_idx)
        qt_app.processEvents()
        assert "Codex" in window.model_line.text()
        assert store.setting("ai_provider") == "codex"

    # Now change to llamacpp
    lcpp_idx = window.provider.findData("llamacpp")
    assert lcpp_idx >= 0
    window.provider.setCurrentIndex(lcpp_idx)
    qt_app.processEvents()
    assert "llama.cpp" in window.model_line.text()
    assert store.setting("ai_provider") == "llamacpp"

    # Now change model name
    window.model.setCurrentText("my-test-model-42")
    qt_app.processEvents()
    assert "my-test-model-42" in window.model_line.text()
    assert store.setting("ai_model") == "my-test-model-42"

    # Switch to tab 0 (Import tab)
    window.tabs.setCurrentIndex(0)
    qt_app.processEvents()
    assert "llama.cpp" in window.model_line.text()
    assert "my-test-model-42" in window.model_line.text()







def test_clicking_video_card_fills_import_url(window):
    url = 'https://www.youtube.com/watch?v=clicked'
    window.url.clear()
    window.video_rows = [{'title': 'Clicked soup', 'url': url, 'duration': 60}]
    window.render_videos()
    window.video_results.itemClicked.emit(window.video_results.item(0))
    assert window.url.text() == url
    assert window.status.text() == window.nt('video_picked')


def test_busy_banner_shows_job_steps_and_result(window, qt_app):
    release = threading.Event(); reported = threading.Event()
    def job():
        window.job_progress.emit('progress_ai'); reported.set(); release.wait(2); return 'ok'
    window.show()
    window.run_job(job, lambda _: window.status.setText(window.nt('import_done')), 'importing')
    wait_events(qt_app, reported.is_set); wait_events(qt_app, lambda: window.busy_step.isVisible())
    assert window.busy_banner.isVisible() and window.busy_progress.isVisible()
    assert window.nt('importing') in window.busy_title.text()
    assert window.nt('progress_ai') in window.busy_step.text()
    release.set(); wait_events(qt_app, lambda: not window.busy)
    assert window.busy_banner.isVisible() and not window.busy_progress.isVisible()
    assert window.nt('import_done') in window.busy_title.text()
    assert window.busy_banner.property('state') == 'done'
    window.dismiss_banner(); assert not window.busy_banner.isVisible()
    window.hide()


def test_failed_job_marks_banner_failed(window, qt_app):
    def job():
        raise RuntimeError('boom')
    window.run_job(job, lambda _: None, 'importing')
    wait_events(qt_app, lambda: not window.busy)
    assert window.busy_banner.property('state') == 'failed'
    assert window.nt('failed') in window.busy_title.text()
    window.dismiss_banner()


def test_setup_preselects_signed_in_claude(window):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QComboBox, QDialog
    seen = []
    def inspect_setup():
        dialog = next(child for child in window.findChildren(QDialog) if child.isVisible())
        choices = dialog.findChildren(QComboBox)[1]
        seen.append(choices.currentData()); dialog.reject()
    QTimer.singleShot(0, inspect_setup)
    with patch('app.cli_providers.detected', return_value=['claude', 'codex']):
        window.show_setup()
    assert seen == ['claude']


def test_ai_import_reports_why_no_recipe_was_extracted(native_record):
    url = 'https://www.youtube.com/watch?v=noRecipe'
    extracted = {'title': 'Vlog', 'ingredients': [], 'instructions': [], 'source_url': url,
                 'raw_text': 'Vlog\nsubscribe', 'transcript': 'today we cook nothing'}
    steps = []
    with patch.object(store, 'extract', return_value=extracted), patch.object(store, 'require_translation'), \
         patch.object(store, 'normalize', return_value={'title': 'Vlog', 'ingredients': [], 'instructions': []}) as normalize:
        result = store.import_recipe(url, True, 'en', progress=steps.append)
    assert result['without_ai'] and result['ai_error'] == 'ai_no_recipe'
    assert 'today we cook nothing' in normalize.call_args.args[1]
    assert steps == ['progress_reading', 'progress_checking', 'progress_ai', 'progress_saving']
    store.delete_recipe(result['id'])


def test_ai_import_reports_unavailable_model(native_record):
    url = 'https://example.com/unavailable-model'
    extracted = {'title': 'Soup', 'ingredients': ['salt'], 'instructions': ['Cook'], 'source_url': url}
    with patch.object(store, 'extract', return_value=extracted), patch.object(store, 'require_translation', side_effect=ValueError('down')):
        result = store.import_recipe(url, True)
    assert result['ai_error'] == 'translation_unavailable'
    store.delete_recipe(result['id'])


def test_import_ai_row_shows_check_button_only_until_languages_are_verified(window):
    store.save_settings({'ai_provider': 'llamacpp'})
    window.fill_targets([])
    assert not window.ai_hint.isHidden() and not window.check_button.isHidden()
    window.fill_targets([{'code': 'en', 'name': 'English'}])
    assert window.ai_hint.isHidden() and window.check_button.isHidden()
    store.save_settings({'ai_provider': ''})
    window.fill_targets([])
    assert window.ai_hint.text() == window.nt('ai_off_hint') and window.check_button.isHidden()


def test_video_filters_appear_only_with_results(window):
    window.video_rows = []; window.render_videos()
    assert window.video_filter_row.isHidden()
    window.video_rows = [{'title': 'Soup', 'url': 'https://youtu.be/x', 'group': 'Chef'}]; window.render_videos()
    assert not window.video_filter_row.isHidden()


def test_settings_cards_put_ai_before_languages(window):
    ai_card = window.provider.parentWidget(); lang_card = window.layout_language.parentWidget()
    column = ai_card.parentWidget().layout()
    assert column.indexOf(ai_card) == 0 and column.indexOf(lang_card) == 1
    assert window.settings_target.parentWidget() is lang_card


def test_switching_provider_in_settings_releases_gpu_in_background(window, qt_app):
    with patch('app.native.local_runtime.release_unselected') as release:
        window.provider.setCurrentIndex(window.provider.findData('claude'))
        wait_events(qt_app, lambda: release.called and not window.ai_workers)
    release.assert_called_with('claude')
