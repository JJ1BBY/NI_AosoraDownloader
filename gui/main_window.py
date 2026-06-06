"""メインウィンドウ。"""

import os
from pathlib import Path

from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, QSize, QSortFilterProxyModel, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStyle,
    QStyledItemDelegate,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from aozora.catalog import filter_by_ndc, load_catalog, search_works
from aozora.models import Work
from gui.category_filter import CategoryFilterWidget
from gui.shelf_model import ShelfModel
from gui.workers import CatalogUpdateWorker, DownloadConvertWorker

CSV_PATH = Path(__file__).resolve().parent.parent / "list_person_all_extended_utf8.csv"
SETTINGS_PATH = Path(__file__).resolve().parent.parent / "settings.json"

COLUMNS = ["作品ID", "作品名", "著者", "翻訳者", "文字遣い", "分類", "公開日", "最終更新日", "本箱"]
SHELF_COL = 8

_QSS = """
QMainWindow { background: #F5F1E8; }
QWidget#central { background: #F5F1E8; }
QWidget#topBar { background: #F5F1E8; border-bottom: 1px solid rgba(33,29,24,0.12); }
QTableView {
    background: #FFFDF8;
    alternate-background-color: #f8f4eb;
    gridline-color: rgba(33,29,24,0.06);
    border: none;
}
QHeaderView::section {
    background: #ede9e0;
    color: #6f675b;
    font-weight: bold;
    font-size: 11px;
    padding: 4px 8px;
    border: none;
    border-right: 1px solid rgba(33,29,24,0.10);
    border-bottom: 1px solid rgba(33,29,24,0.18);
}
QFrame#shelfPane {
    background: #FFFDF8;
    border-left: 1px solid rgba(33,29,24,0.12);
}
QLabel#shelfHeading {
    font-family: "Yu Mincho", "游明朝", serif;
    font-size: 16px;
    font-weight: bold;
    color: #211D18;
}
QLabel#shelfBadge {
    background: #3A5A8C;
    color: white;
    border-radius: 9px;
    padding: 1px 8px;
    font-size: 12px;
    font-weight: bold;
    min-width: 18px;
}
QPushButton#downloadBtn {
    background: #3A5A8C;
    color: white;
    border: none;
    border-radius: 10px;
    padding: 12px 16px;
    font-weight: bold;
    font-size: 13px;
}
QPushButton#downloadBtn:hover { background: #2d4a78; }
QPushButton#downloadBtn:disabled { background: #c7beb0; color: #8A8173; }
"""


class CatalogLoaderWorker(QThread):
    """CSVカタログを非同期で読み込むワーカー。"""

    loaded = Signal(list)  # list[Work]
    error = Signal(str)

    def __init__(self, csv_path: Path, parent=None):
        super().__init__(parent)
        self._csv_path = csv_path

    def run(self):
        try:
            works = load_catalog(self._csv_path)
            works = [w for w in works if w.has_text_file]
            self.loaded.emit(works)
        except Exception as e:
            self.error.emit(str(e))


class WorkTableModel(QAbstractTableModel):
    """作品一覧のテーブルモデル。"""

    def __init__(self, works: list[Work] | None = None, parent=None):
        super().__init__(parent)
        self._works: list[Work] = works or []

    def set_works(self, works: list[Work]):
        self.beginResetModel()
        self._works = works
        self.endResetModel()

    def get_work(self, row: int) -> Work | None:
        if 0 <= row < len(self._works):
            return self._works[row]
        return None

    def rowCount(self, parent=QModelIndex()):
        return len(self._works)

    def columnCount(self, parent=QModelIndex()):
        return len(COLUMNS)

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        work = self._works[index.row()]
        col = index.column()
        if col == SHELF_COL:
            # delegate が描画するため DisplayRole は None、UserRole で work_id を提供
            if role == Qt.ItemDataRole.UserRole:
                return work.work_id
            return None
        if role not in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.UserRole):
            return None
        if col == 0:
            return work.work_id
        elif col == 1:
            return work.title
        elif col == 2:
            return work.authors_display
        elif col == 3:
            return work.translators_display
        elif col == 4:
            return work.charset_type
        elif col == 5:
            return work.classification
        elif col == 6:
            return work.release_date
        elif col == 7:
            return work.last_updated
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return COLUMNS[section]
        return None

    def flags(self, index: QModelIndex):
        if index.column() == SHELF_COL:
            return Qt.ItemFlag.ItemIsEnabled  # 選択・編集不可、クリックは view.clicked で処理
        return super().flags(index)


class ShelfButtonDelegate(QStyledItemDelegate):
    """本箱列のトグルボタンを描画するデリゲート。"""

    def __init__(self, shelf: ShelfModel, parent=None):
        super().__init__(parent)
        self._shelf = shelf

    def paint(self, painter: QPainter, option, index: QModelIndex):
        work_id = index.data(Qt.ItemDataRole.UserRole)
        if not work_id:
            return

        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = option.rect.adjusted(6, 5, -6, -5)
        accent = QColor("#3A5A8C")

        if self._shelf.contains(work_id):
            painter.setBrush(accent)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(rect, 5, 5)
            painter.setPen(QColor("white"))
            text = "✓ 追加済"
        else:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(accent, 1.5))
            painter.drawRoundedRect(rect, 5, 5)
            painter.setPen(accent)
            text = "＋ 本箱"

        f = painter.font()
        f.setPointSize(9)
        painter.setFont(f)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
        painter.restore()

    def sizeHint(self, option, index):
        return QSize(96, 30)


class ShelfPane(QFrame):
    """本箱ペイン（右レール）。"""

    download_requested = Signal()
    dir_select_requested = Signal()

    def __init__(self, shelf: ShelfModel, output_dir: str, parent=None):
        super().__init__(parent)
        self.setObjectName("shelfPane")
        self._shelf = shelf
        self._output_dir = output_dir
        self._build_ui()
        self._shelf.changed.connect(self._refresh)
        self._refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Heading + badge
        heading_row = QHBoxLayout()
        heading_row.setSpacing(8)
        heading = QLabel("本箱")
        heading.setObjectName("shelfHeading")
        heading_row.addWidget(heading)
        self._badge = QLabel("0")
        self._badge.setObjectName("shelfBadge")
        self._badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        heading_row.addWidget(self._badge)
        heading_row.addStretch()
        layout.addLayout(heading_row)

        # Scrollable work list
        self._list_container = QWidget()
        self._list_container.setStyleSheet("background: transparent;")
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(4)
        self._list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._list_container)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(scroll, 1)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: rgba(33,29,24,0.12);")
        layout.addWidget(sep)

        # Output options
        self._include_images_cb = QCheckBox("挿絵を含める")
        self._include_images_cb.setChecked(True)
        self._include_images_cb.setToolTip("挿絵をEPUBに含めます")
        layout.addWidget(self._include_images_cb)

        self._author_in_filename_cb = QCheckBox("ファイル名に著者名")
        self._author_in_filename_cb.setChecked(False)
        self._author_in_filename_cb.setToolTip("[著者名] 作品名.epub の形式で出力します")
        layout.addWidget(self._author_in_filename_cb)

        # Save dir
        self._dir_btn = QPushButton(f"保存先: {self._shorten_path(self._output_dir)}")
        self._dir_btn.setToolTip(self._output_dir)
        self._dir_btn.clicked.connect(self.dir_select_requested)
        layout.addWidget(self._dir_btn)

        # Progress + status
        self._progress = QProgressBar()
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        self._status_label = QLabel("")
        self._status_label.setWordWrap(True)
        self._status_label.setStyleSheet("font-size: 11px; color: #6f675b;")
        layout.addWidget(self._status_label)

        # Download button
        self._download_btn = QPushButton("ダウンロード")
        self._download_btn.setObjectName("downloadBtn")
        self._download_btn.setEnabled(False)
        self._download_btn.clicked.connect(self.download_requested)
        layout.addWidget(self._download_btn)

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def include_images(self) -> bool:
        return self._include_images_cb.isChecked()

    @property
    def author_in_filename(self) -> bool:
        return self._author_in_filename_cb.isChecked()

    def set_output_dir(self, path: str):
        self._output_dir = path
        self._dir_btn.setText(f"保存先: {self._shorten_path(path)}")
        self._dir_btn.setToolTip(path)

    def set_progress(self, percent: int, message: str):
        self._progress.setVisible(True)
        self._progress.setValue(percent)
        self._status_label.setText(message)

    def set_status(self, message: str):
        self._status_label.setText(message)

    def set_downloading(self, downloading: bool):
        self._download_btn.setEnabled(not downloading and len(self._shelf) > 0)
        self._progress.setVisible(downloading)
        if not downloading:
            self._progress.setValue(0)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _refresh(self):
        count = len(self._shelf)
        self._badge.setText(str(count))
        self._download_btn.setEnabled(count > 0)
        self._download_btn.setText(f"{count}作品をダウンロード" if count > 0 else "ダウンロード")

        # Rebuild work list
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

        for work in self._shelf.works():
            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 2, 0, 2)
            rl.setSpacing(6)

            lbl = QLabel(work.title)
            lbl.setWordWrap(True)
            lbl.setStyleSheet("font-size: 12px; color: #211D18;")
            rl.addWidget(lbl, 1)

            rm_btn = QPushButton("×")
            rm_btn.setFixedSize(22, 22)
            rm_btn.setStyleSheet(
                "QPushButton { border: 1px solid #b6ac9b; border-radius: 4px;"
                " color: #8A8173; background: transparent; font-size: 12px; }"
                "QPushButton:hover { color: #c0392b; border-color: #c0392b; }"
            )
            wid = work.work_id
            rm_btn.clicked.connect(lambda checked, w=wid: self._shelf.remove(w))
            rl.addWidget(rm_btn)

            self._list_layout.addWidget(row)

    @staticmethod
    def _shorten_path(path: str) -> str:
        home = str(Path.home())
        if path.startswith(home):
            return "~" + path[len(home):]
        return path[-40:] if len(path) > 40 else path


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("青空文庫ダウンローダー")
        self.resize(1200, 700)

        self._all_works: list[Work] = []
        self._worker: DownloadConvertWorker | None = None
        self._catalog_loader: CatalogLoaderWorker | None = None
        self._catalog_updater: CatalogUpdateWorker | None = None
        self._output_dir = str(Path.home() / "Downloads")
        self._shelf = ShelfModel(self)

        self._setup_ui()
        self.setStyleSheet(_QSS)
        self._load_data()

    def _setup_ui(self):
        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── 上部: 検索バー ────────────────────────────────────────────────────
        top_bar = QWidget()
        top_bar.setObjectName("topBar")
        filter_layout = QHBoxLayout(top_bar)
        filter_layout.setContentsMargins(12, 8, 12, 8)
        filter_layout.setSpacing(8)

        filter_layout.addWidget(QLabel("著者名:"))
        self._author_input = QLineEdit()
        self._author_input.setPlaceholderText("著者名で絞り込み")
        self._author_input.setClearButtonEnabled(True)
        filter_layout.addWidget(self._author_input)

        filter_layout.addWidget(QLabel("タイトル:"))
        self._title_input = QLineEdit()
        self._title_input.setPlaceholderText("タイトルで検索")
        self._title_input.setClearButtonEnabled(True)
        filter_layout.addWidget(self._title_input)

        self._search_btn = QPushButton("検索")
        filter_layout.addWidget(self._search_btn)

        self._update_catalog_btn = QPushButton("カタログ更新")
        self._update_catalog_btn.setToolTip("青空文庫からカタログCSVを再ダウンロードします")
        filter_layout.addWidget(self._update_catalog_btn)
        filter_layout.addStretch()

        # カタログ読み込み中のみ表示するステータス
        self._catalog_status = QLabel("")
        self._catalog_status.setStyleSheet("font-size: 12px; color: #6f675b;")
        filter_layout.addWidget(self._catalog_status)

        self._catalog_progress = QProgressBar()
        self._catalog_progress.setFixedWidth(150)
        self._catalog_progress.setVisible(False)
        filter_layout.addWidget(self._catalog_progress)

        main_layout.addWidget(top_bar)

        # ── ボディ: 左・中央・右の3カラム ─────────────────────────────────────
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        # 左: 分野フィルタ（常時展開）
        self._category_filter = CategoryFilterWidget(SETTINGS_PATH)
        self._category_filter.setFixedWidth(210)
        body.addWidget(self._category_filter)

        # 中央: 作品カウント + テーブル
        center = QVBoxLayout()
        center.setContentsMargins(0, 0, 0, 0)
        center.setSpacing(0)

        self._count_label = QLabel("0 作品")
        self._count_label.setContentsMargins(10, 4, 10, 4)
        self._count_label.setStyleSheet("font-size: 12px; color: #8A8173;")
        center.addWidget(self._count_label)

        self._model = WorkTableModel()
        self._proxy = QSortFilterProxyModel()
        self._proxy.setSourceModel(self._model)
        self._proxy.setSortCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._proxy.setSortRole(Qt.ItemDataRole.UserRole)

        self._table = QTableView()
        self._table.setModel(self._proxy)
        self._table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self._table.setSortingEnabled(True)
        self._table.setAlternatingRowColors(True)
        self._table.setShowGrid(False)
        self._table.horizontalHeader().setStretchLastSection(False)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self._table.verticalHeader().setVisible(False)
        self._table.verticalHeader().setDefaultSectionSize(28)

        self._shelf_delegate = ShelfButtonDelegate(self._shelf, self._table)
        self._table.setItemDelegateForColumn(SHELF_COL, self._shelf_delegate)
        self._table.setColumnWidth(SHELF_COL, 96)

        center.addWidget(self._table, 1)
        body.addLayout(center, 1)

        # 右: 本箱ペイン
        self._shelf_pane = ShelfPane(self._shelf, self._output_dir)
        self._shelf_pane.setFixedWidth(270)
        body.addWidget(self._shelf_pane)

        main_layout.addLayout(body, 1)

        # ── デバウンスタイマー ─────────────────────────────────────────────────
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300)
        self._search_timer.timeout.connect(self._apply_filter)

        # ── シグナル接続 ───────────────────────────────────────────────────────
        self._search_btn.clicked.connect(self._apply_filter)
        self._author_input.returnPressed.connect(self._apply_filter)
        self._title_input.returnPressed.connect(self._apply_filter)
        self._author_input.textChanged.connect(self._search_timer.start)
        self._title_input.textChanged.connect(self._search_timer.start)
        self._category_filter.selection_changed.connect(lambda _: self._search_timer.start())
        self._update_catalog_btn.clicked.connect(self._on_update_catalog)
        self._table.clicked.connect(self._on_table_clicked)
        self._shelf.changed.connect(self._table.viewport().update)
        self._shelf_pane.download_requested.connect(self._on_download)
        self._shelf_pane.dir_select_requested.connect(self._on_select_dir)

    def _on_table_clicked(self, index: QModelIndex):
        if index.column() == SHELF_COL:
            src = self._proxy.mapToSource(index)
            work = self._model.get_work(src.row())
            if work and work.has_text_file:
                self._shelf.toggle(work)

    def _load_data(self):
        if not CSV_PATH.exists():
            QMessageBox.critical(self, "エラー", f"CSVファイルが見つかりません:\n{CSV_PATH}")
            return
        self._catalog_status.setText("データ読み込み中...")
        self._search_btn.setEnabled(False)
        self._catalog_progress.setVisible(True)
        self._catalog_progress.setRange(0, 0)

        self._catalog_loader = CatalogLoaderWorker(CSV_PATH)
        self._catalog_loader.loaded.connect(self._on_catalog_loaded)
        self._catalog_loader.error.connect(self._on_catalog_error)
        self._catalog_loader.start()

    def _on_catalog_loaded(self, works: list[Work]):
        self._all_works = works
        self._apply_filter()
        self._update_count()
        self._catalog_status.setText("")
        self._search_btn.setEnabled(True)
        self._catalog_progress.setVisible(False)
        self._catalog_progress.setRange(0, 100)
        if self._catalog_loader is not None:
            self._catalog_loader.deleteLater()
            self._catalog_loader = None

        # 列幅の初期調整
        self._table.setColumnWidth(0, 50)
        self._table.setColumnWidth(1, 160)
        self._table.setColumnWidth(2, 95)
        self._table.setColumnWidth(3, 65)
        self._table.setColumnWidth(4, 70)
        self._table.setColumnWidth(5, 50)
        self._table.setColumnWidth(6, 75)
        self._table.setColumnWidth(7, 75)
        self._table.setColumnWidth(SHELF_COL, 96)

    def _on_catalog_error(self, message: str):
        self._catalog_status.setText("")
        self._search_btn.setEnabled(True)
        self._catalog_progress.setVisible(False)
        self._catalog_progress.setRange(0, 100)
        if self._catalog_loader is not None:
            self._catalog_loader.deleteLater()
            self._catalog_loader = None
        QMessageBox.critical(self, "エラー", f"データ読み込みに失敗しました:\n{message}")

    def _on_update_catalog(self):
        self._update_catalog_btn.setEnabled(False)
        self._search_btn.setEnabled(False)
        self._catalog_progress.setVisible(True)
        self._catalog_progress.setRange(0, 100)

        self._catalog_updater = CatalogUpdateWorker(CSV_PATH)
        self._catalog_updater.progress.connect(self._on_catalog_update_progress)
        self._catalog_updater.completed.connect(self._on_catalog_update_finished)
        self._catalog_updater.update_error.connect(self._on_catalog_update_error)
        self._catalog_updater.finished.connect(self._catalog_updater.deleteLater)
        self._catalog_updater.start()

    def _on_catalog_update_progress(self, percent: int, message: str):
        self._catalog_progress.setValue(percent)
        self._catalog_status.setText(message)

    def _on_catalog_update_finished(self):
        self._catalog_updater = None
        self._update_catalog_btn.setEnabled(True)
        self._catalog_status.setText("カタログを再読み込み中...")
        self._load_data()

    def _on_catalog_update_error(self, message: str):
        self._catalog_updater = None
        self._update_catalog_btn.setEnabled(True)
        self._search_btn.setEnabled(True)
        self._catalog_progress.setVisible(False)
        self._catalog_status.setText("")
        QMessageBox.critical(self, "エラー", f"カタログの更新に失敗しました:\n{message}")

    def _apply_filter(self):
        author = self._author_input.text().strip()
        title = self._title_input.text().strip()
        results = self._all_works
        if author or title:
            results = search_works(results, author=author, title=title)
        prefixes = self._category_filter.get_selected_prefixes()
        if prefixes:
            results = filter_by_ndc(results, prefixes)
        self._model.set_works(results)
        self._update_count()

    def _update_count(self):
        count = self._proxy.rowCount()
        self._count_label.setText(f"{count} 作品")

    def _on_select_dir(self):
        dir_path = QFileDialog.getExistingDirectory(self, "保存先フォルダ", self._output_dir)
        if dir_path:
            try:
                os.makedirs(dir_path, exist_ok=True)
            except OSError as e:
                QMessageBox.warning(self, "警告", f"保存先フォルダにアクセスできません:\n{e}")
                return
            self._output_dir = dir_path
            self._shelf_pane.set_output_dir(dir_path)

    def _on_download(self):
        works_to_download = [w for w in self._shelf.works() if w.has_text_file]
        if not works_to_download:
            return

        try:
            os.makedirs(self._output_dir, exist_ok=True)
        except OSError as e:
            QMessageBox.critical(self, "エラー", f"保存先フォルダを作成できません:\n{e}")
            return

        self._search_btn.setEnabled(False)
        self._shelf_pane.set_downloading(True)

        self._worker = DownloadConvertWorker(
            works_to_download,
            self._output_dir,
            include_images=self._shelf_pane.include_images,
            author_in_filename=self._shelf_pane.author_in_filename,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.error_occurred.connect(self._on_error)
        self._worker.finished_all.connect(self._on_finished)
        self._worker.start()

    def _on_progress(self, percent: int, message: str):
        self._shelf_pane.set_progress(percent, message)

    def _on_error(self, work_id: str, message: str):
        self._shelf_pane.set_status(f"エラー (作品ID {work_id}): {message}")

    def _on_finished(self, success: int, errors: int):
        self._search_btn.setEnabled(True)
        self._shelf_pane.set_downloading(False)
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None
        msg = f"完了: {success}件成功"
        if errors:
            msg += f"、{errors}件エラー"
        self._shelf_pane.set_status(msg)
        QMessageBox.information(self, "完了", msg)
