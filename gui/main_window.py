"""メインウィンドウ。"""

import os
from pathlib import Path

from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, QSortFilterProxyModel, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from aozora.catalog import load_catalog, search_works
from aozora.models import Work
from gui.workers import DownloadConvertWorker


COLUMNS = ["作品ID", "作品名", "著者", "翻訳者", "文字遣い", "分類"]


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
        if not index.isValid() or role != Qt.ItemDataRole.DisplayRole:
            return None
        work = self._works[index.row()]
        col = index.column()
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
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return COLUMNS[section]
        return None


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("青空文庫ダウンローダー")
        self.resize(900, 600)

        self._all_works: list[Work] = []
        self._worker: DownloadConvertWorker | None = None
        self._catalog_loader: CatalogLoaderWorker | None = None
        self._output_dir = str(Path.home() / "Downloads")

        self._setup_ui()
        self._load_data()

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # フィルターバー
        filter_layout = QHBoxLayout()
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
        layout.addLayout(filter_layout)

        # テーブル
        self._model = WorkTableModel()
        self._proxy = QSortFilterProxyModel()
        self._proxy.setSourceModel(self._model)
        self._proxy.setSortCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)

        self._table = QTableView()
        self._table.setModel(self._proxy)
        self._table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableView.SelectionMode.ExtendedSelection)
        self._table.setSortingEnabled(True)
        self._table.setAlternatingRowColors(True)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive
        )
        self._table.verticalHeader().setVisible(False)
        layout.addWidget(self._table)

        # ステータス行
        status_layout = QHBoxLayout()
        self._count_label = QLabel("0 作品")
        status_layout.addWidget(self._count_label)

        status_layout.addStretch()

        self._include_images_cb = QCheckBox("画像を含める")
        self._include_images_cb.setChecked(True)
        self._include_images_cb.setToolTip("カバー画像と挿絵をEPUBに含めます")
        status_layout.addWidget(self._include_images_cb)

        self._author_in_filename_cb = QCheckBox("ファイル名に著者名")
        self._author_in_filename_cb.setChecked(False)
        self._author_in_filename_cb.setToolTip("[著者名] 作品名.epub の形式で出力します")
        status_layout.addWidget(self._author_in_filename_cb)

        self._dir_btn = QPushButton(f"保存先: {self._output_dir}")
        self._dir_btn.setToolTip(self._output_dir)
        status_layout.addWidget(self._dir_btn)

        self._download_btn = QPushButton("ダウンロード && EPUB変換")
        self._download_btn.setEnabled(False)
        status_layout.addWidget(self._download_btn)
        layout.addLayout(status_layout)

        # プログレスバー
        self._progress = QProgressBar()
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        self._status_label = QLabel("")
        layout.addWidget(self._status_label)

        # シグナル接続
        self._search_btn.clicked.connect(self._on_search)
        self._author_input.returnPressed.connect(self._on_search)
        self._title_input.returnPressed.connect(self._on_search)
        self._dir_btn.clicked.connect(self._on_select_dir)
        self._download_btn.clicked.connect(self._on_download)
        self._table.selectionModel().selectionChanged.connect(self._on_selection_changed)

    def _load_data(self):
        csv_path = Path(__file__).resolve().parent.parent / "list_person_all_extended_utf8.csv"
        if not csv_path.exists():
            QMessageBox.critical(self, "エラー", f"CSVファイルが見つかりません:\n{csv_path}")
            return
        self._status_label.setText("データ読み込み中...")
        self._search_btn.setEnabled(False)
        self._progress.setVisible(True)
        self._progress.setRange(0, 0)  # インデターミネートモード

        self._catalog_loader = CatalogLoaderWorker(csv_path)
        self._catalog_loader.loaded.connect(self._on_catalog_loaded)
        self._catalog_loader.error.connect(self._on_catalog_error)
        self._catalog_loader.start()

    def _on_catalog_loaded(self, works: list[Work]):
        self._all_works = works
        self._model.set_works(self._all_works)
        self._update_count()
        self._status_label.setText("")
        self._search_btn.setEnabled(True)
        self._progress.setVisible(False)
        self._progress.setRange(0, 100)
        if self._catalog_loader is not None:
            self._catalog_loader.deleteLater()
            self._catalog_loader = None

        # 列幅の初期調整
        self._table.setColumnWidth(0, 70)
        self._table.setColumnWidth(1, 300)
        self._table.setColumnWidth(2, 150)
        self._table.setColumnWidth(3, 100)
        self._table.setColumnWidth(4, 90)

    def _on_catalog_error(self, message: str):
        self._status_label.setText("")
        self._search_btn.setEnabled(True)
        self._progress.setVisible(False)
        self._progress.setRange(0, 100)
        if self._catalog_loader is not None:
            self._catalog_loader.deleteLater()
            self._catalog_loader = None
        QMessageBox.critical(self, "エラー", f"データ読み込みに失敗しました:\n{message}")

    def _on_search(self):
        author = self._author_input.text().strip()
        title = self._title_input.text().strip()
        if not author and not title:
            self._model.set_works(self._all_works)
        else:
            results = search_works(self._all_works, author=author, title=title)
            self._model.set_works(results)
        self._update_count()

    def _update_count(self):
        count = self._proxy.rowCount()
        self._count_label.setText(f"{count} 作品")

    def _on_selection_changed(self):
        selected = self._table.selectionModel().selectedRows()
        self._download_btn.setEnabled(len(selected) > 0)
        if selected:
            self._download_btn.setText(f"ダウンロード && EPUB変換 ({len(selected)}件)")
        else:
            self._download_btn.setText("ダウンロード && EPUB変換")

    def _on_select_dir(self):
        dir_path = QFileDialog.getExistingDirectory(self, "保存先フォルダ", self._output_dir)
        if dir_path:
            try:
                os.makedirs(dir_path, exist_ok=True)
            except OSError as e:
                QMessageBox.warning(self, "警告", f"保存先フォルダにアクセスできません:\n{e}")
                return
            self._output_dir = dir_path
            self._dir_btn.setText(f"保存先: {dir_path}")
            self._dir_btn.setToolTip(dir_path)

    def _on_download(self):
        selected_rows = self._table.selectionModel().selectedRows()
        if not selected_rows:
            return

        works_to_download: list[Work] = []
        for idx in selected_rows:
            source_idx = self._proxy.mapToSource(idx)
            work = self._model.get_work(source_idx.row())
            if work and work.has_text_file:
                works_to_download.append(work)

        if not works_to_download:
            QMessageBox.warning(self, "警告", "テキストファイルURLを持つ作品が選択されていません。")
            return

        try:
            os.makedirs(self._output_dir, exist_ok=True)
        except OSError as e:
            QMessageBox.critical(self, "エラー", f"保存先フォルダを作成できません:\n{e}")
            return

        self._download_btn.setEnabled(False)
        self._search_btn.setEnabled(False)
        self._progress.setVisible(True)
        self._progress.setValue(0)

        include_images = self._include_images_cb.isChecked()
        author_in_filename = self._author_in_filename_cb.isChecked()
        self._worker = DownloadConvertWorker(
            works_to_download,
            self._output_dir,
            include_images=include_images,
            author_in_filename=author_in_filename,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.error_occurred.connect(self._on_error)
        self._worker.finished_all.connect(self._on_finished)
        self._worker.start()

    def _on_progress(self, percent: int, message: str):
        self._progress.setValue(percent)
        self._status_label.setText(message)

    def _on_error(self, work_id: str, message: str):
        self._status_label.setText(f"エラー (作品ID {work_id}): {message}")

    def _on_finished(self, success: int, errors: int):
        self._progress.setVisible(False)
        self._download_btn.setEnabled(True)
        self._search_btn.setEnabled(True)
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None

        msg = f"完了: {success}件成功"
        if errors:
            msg += f"、{errors}件エラー"
        self._status_label.setText(msg)
        QMessageBox.information(self, "完了", msg)
