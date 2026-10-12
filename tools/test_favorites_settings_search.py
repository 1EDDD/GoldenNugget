"""Bookmarks stay independent of tweak state; settings search preserves inputs."""
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel, QLineEdit
from src.controllers.favorites import TweakFavorites
from src.gui.ios.tweaks import IOSSectionContent
from src.gui.ios.settings import IOSSettingsPage
from src.gui.ios.components import IOSSectionHeader, IOSSearchField, IOSSearchEmpty
from src.tweaks.tweaks import tweaks


class FavoritesSearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        QSettings.setDefaultFormat(QSettings.IniFormat)
        QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, self.tmp.name)
        self.addCleanup(lambda: QSettings.setDefaultFormat(QSettings.NativeFormat))

    def test_bookmarks_persist_sync_and_respect_compatibility(self):
        manager = SimpleNamespace(get_current_device_version=lambda: '27.0',
                                  get_current_device_model=lambda: 'iPhone17,3')
        window = SimpleNamespace(device_manager=manager)
        one, two = IOSSectionContent(window), IOSSectionContent(window)
        tid = next(tid for card, tid, *_ in one._search_rows if not card.isHidden())
        before = {tid: (t.enabled, repr(t.value)) for tid, t in tweaks.items()}
        one._favorite_buttons[tid].click()
        self.assertIn(tid.name, TweakFavorites().names())
        self.assertTrue(two._favorite_buttons[tid].isChecked())
        self.assertEqual(before, {tid: (t.enabled, repr(t.value)) for tid, t in tweaks.items()})
        one.filter_combo.setCurrentIndex(one.filter_combo.findData('favorites'))
        self.assertEqual([tid for card, tid, *_ in one._search_rows if not card.isHidden()], [tid])
        one.rebuild()
        self.assertTrue(one._favorite_buttons[tid].isChecked())
        one._favorite_buttons[tid].click()
        self.assertFalse(two._favorite_buttons[tid].isChecked())
        self.assertFalse(one.search_empty.isHidden())
        one.close()
        two.close()
        one.deleteLater()
        two.deleteLater()
        self.app.processEvents()

    def test_search_matches_titles_and_sections_without_editing_values(self):
        page = QWidget()
        page.content_layout = QVBoxLayout(page)
        page.search = IOSSearchField()
        page.search_empty = IOSSearchEmpty()
        header = IOSSectionHeader('Backup')
        card = QWidget()
        layout = QVBoxLayout(card)
        layout.addWidget(QLabel('Cache location'))
        value = QLineEdit('private user value')
        layout.addWidget(value)
        other_header = IOSSectionHeader('Appearance')
        other = QLabel('Accent color')
        for widget in (header, card, other_header, other):
            page.content_layout.addWidget(widget)
        IOSSettingsPage._index_search_rows(page)
        page.search.setText('cache')
        IOSSettingsPage._filter_settings(page)
        self.assertFalse(card.isHidden())
        self.assertTrue(other.isHidden())
        page.search.setText('backup')
        IOSSettingsPage._filter_settings(page)
        self.assertFalse(card.isHidden())
        page.search.setText('private user value')
        IOSSettingsPage._filter_settings(page)
        self.assertFalse(page.search_empty.isHidden())
        self.assertTrue(card.isHidden())
        page.search.clear()
        IOSSettingsPage._filter_settings(page)
        self.assertFalse(other.isHidden())
        self.assertEqual(value.text(), 'private user value')


if __name__ == '__main__':
    unittest.main()
