"""本箱：ダウンロード対象の作品を保持するモデル。テーブル選択から独立。"""

from PySide6.QtCore import QObject, Signal

from aozora.models import Work


class ShelfModel(QObject):
    """本箱。ダウンロード対象の作品IDを保持し、変化を changed シグナルで通知する。"""

    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: dict[str, Work] = {}  # work_id -> Work（挿入順保持）

    def add(self, work: Work):
        if work.work_id not in self._items:
            self._items[work.work_id] = work
            self.changed.emit()

    def remove(self, work_id: str):
        if self._items.pop(work_id, None) is not None:
            self.changed.emit()

    def toggle(self, work: Work):
        self.remove(work.work_id) if self.contains(work.work_id) else self.add(work)

    def clear(self):
        if self._items:
            self._items.clear()
            self.changed.emit()

    def contains(self, work_id: str) -> bool:
        return work_id in self._items

    def works(self) -> list[Work]:
        return list(self._items.values())

    def __len__(self) -> int:
        return len(self._items)
