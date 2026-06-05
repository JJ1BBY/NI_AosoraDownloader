"""分野別フィルタウィジェット。コンパクトな折りたたみ式、複数選択対応。"""

import json
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QPushButton,
    QSizePolicy,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from aozora.ndc import NDC_TREE, NdcNode

_SETTINGS_KEY = "category_filter"
_CK = Qt.CheckState.Checked
_UK = Qt.CheckState.Unchecked
_PK = Qt.CheckState.PartiallyChecked


class CategoryFilterWidget(QWidget):
    """NDC分野別フィルタ。初期状態はコンパクトなヘッダーのみ表示。"""

    selection_changed = Signal(set)  # set[str]: 選択された NDC プレフィックス

    def __init__(self, settings_path: Path, parent=None):
        super().__init__(parent)
        self._settings_path = settings_path
        self._updating = False
        self._build_ui()
        self._populate_tree()
        self._load_selection()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ─ Header（常時表示）─
        header = QFrame()
        header.setFrameShape(QFrame.Shape.StyledPanel)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(6, 3, 6, 3)
        hl.setSpacing(6)

        self._toggle = QPushButton("▶  分野フィルタ")
        self._toggle.setFlat(True)
        self._toggle.setCheckable(True)
        self._toggle.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._toggle.setStyleSheet(
            "QPushButton { font-weight: bold; text-align: left; border: none; }"
            "QPushButton:hover { color: #0066cc; }"
        )
        self._toggle.clicked.connect(self._on_toggle)
        hl.addWidget(self._toggle)

        self._all_btn = QPushButton("全選択")
        self._none_btn = QPushButton("全解除")
        for btn in (self._all_btn, self._none_btn):
            btn.setFixedHeight(22)
            btn.setFixedWidth(58)
        self._all_btn.clicked.connect(self._select_all)
        self._none_btn.clicked.connect(self._select_none)
        hl.addWidget(self._all_btn)
        hl.addWidget(self._none_btn)
        root.addWidget(header)

        # ─ Body（折りたたみ）─
        self._body = QFrame()
        self._body.setVisible(False)
        self._body.setFrameShape(QFrame.Shape.StyledPanel)
        bl = QVBoxLayout(self._body)
        bl.setContentsMargins(4, 4, 4, 4)
        bl.setSpacing(2)

        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setMaximumHeight(250)
        self._tree.setMinimumHeight(120)
        self._tree.setAlternatingRowColors(True)
        self._tree.itemChanged.connect(self._on_item_changed)
        bl.addWidget(self._tree)
        root.addWidget(self._body)

    def _on_toggle(self, checked: bool):
        self._body.setVisible(checked)
        self._toggle.setText(("▼" if checked else "▶") + "  分野フィルタ")

    # ── Tree ──────────────────────────────────────────────────────────────────

    def _populate_tree(self):
        self._tree.blockSignals(True)
        for node in NDC_TREE:
            top = self._make_item(node)
            self._tree.addTopLevelItem(top)
            for child in node.children:
                c = self._make_item(child)
                top.addChild(c)
                for gc in child.children:
                    c.addChild(self._make_item(gc))
        self._tree.blockSignals(False)

    @staticmethod
    def _make_item(node: NdcNode) -> QTreeWidgetItem:
        item = QTreeWidgetItem([node.label])
        item.setData(0, Qt.ItemDataRole.UserRole, node.code)
        item.setCheckState(0, _UK)
        item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
        return item

    # ── Tri-state ─────────────────────────────────────────────────────────────

    def _on_item_changed(self, item: QTreeWidgetItem, column: int):
        if column != 0 or self._updating:
            return
        self._updating = True
        self._tree.blockSignals(True)
        try:
            state = item.checkState(0)
            if state != _PK:
                self._cascade_down(item, state)
            parent = item.parent()
            while parent:
                self._recalc(parent)
                parent = parent.parent()
        finally:
            self._tree.blockSignals(False)
            self._updating = False
        self._emit()
        self._save()

    @staticmethod
    def _cascade_down(item: QTreeWidgetItem, state: Qt.CheckState):
        for i in range(item.childCount()):
            child = item.child(i)
            child.setCheckState(0, state)
            CategoryFilterWidget._cascade_down(child, state)

    @staticmethod
    def _recalc(parent: QTreeWidgetItem):
        n = parent.childCount()
        checked = sum(1 for i in range(n) if parent.child(i).checkState(0) == _CK)
        partial = sum(1 for i in range(n) if parent.child(i).checkState(0) == _PK)
        if checked == n:
            parent.setCheckState(0, _CK)
        elif checked == 0 and partial == 0:
            parent.setCheckState(0, _UK)
        else:
            parent.setCheckState(0, _PK)

    # ── Bulk ops ──────────────────────────────────────────────────────────────

    def _select_all(self):
        self._bulk(_CK)

    def _select_none(self):
        self._bulk(_UK)

    def _bulk(self, state: Qt.CheckState):
        self._tree.blockSignals(True)
        for i in range(self._tree.topLevelItemCount()):
            top = self._tree.topLevelItem(i)
            top.setCheckState(0, state)
            self._cascade_down(top, state)
        self._tree.blockSignals(False)
        self._emit()
        self._save()

    # ── Selection ─────────────────────────────────────────────────────────────

    def get_selected_prefixes(self) -> set[str]:
        """選択された最小プレフィックスセットを返す（親が選択済みなら子は含めない）。"""
        result: set[str] = set()
        self._collect(None, result)
        return result

    def _collect(self, parent: QTreeWidgetItem | None, result: set[str]):
        if parent is None:
            items = [self._tree.topLevelItem(i) for i in range(self._tree.topLevelItemCount())]
        else:
            items = [parent.child(i) for i in range(parent.childCount())]
        for item in items:
            state = item.checkState(0)
            if state == _CK:
                result.add(item.data(0, Qt.ItemDataRole.UserRole))
            elif state == _PK:
                self._collect(item, result)

    def _emit(self):
        self.selection_changed.emit(self.get_selected_prefixes())

    # ── Persistence ───────────────────────────────────────────────────────────

    def _save(self):
        data: dict = {}
        if self._settings_path.exists():
            try:
                data = json.loads(self._settings_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        data[_SETTINGS_KEY] = sorted(self.get_selected_prefixes())
        try:
            self._settings_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    def _load_selection(self):
        if not self._settings_path.exists():
            return
        try:
            data = json.loads(self._settings_path.read_text(encoding="utf-8"))
            codes: set[str] = set(data.get(_SETTINGS_KEY, []))
        except Exception:
            return
        if not codes:
            return
        self._tree.blockSignals(True)
        self._apply_codes(codes, None)
        self._tree.blockSignals(False)

    def _apply_codes(self, codes: set[str], parent: QTreeWidgetItem | None):
        if parent is None:
            items = [self._tree.topLevelItem(i) for i in range(self._tree.topLevelItemCount())]
        else:
            items = [parent.child(i) for i in range(parent.childCount())]
        for item in items:
            code = item.data(0, Qt.ItemDataRole.UserRole)
            if code in codes:
                item.setCheckState(0, _CK)
                self._cascade_down(item, _CK)
            elif item.childCount() > 0:
                self._apply_codes(codes, item)
                self._recalc(item)
