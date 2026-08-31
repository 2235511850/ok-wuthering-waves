# WeightPresetTab.py
# ============================================================
# 导航栏Tab页: 评分权重预设管理
# 支持方案的增删改, 左侧列表选方案, 右侧编辑权重
# ============================================================
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QTableWidgetItem, QHeaderView, QAbstractItemView, QListWidgetItem
from qfluentwidgets import (
    BodyLabel, ComboBox, FluentIcon, LineEdit, ListWidget,
    MessageBox, PrimaryPushButton, PushButton, SubtitleLabel, TableWidget,
    DoubleSpinBox, MessageBoxBase,
)

from ok import Logger
from ok.gui.util.app import show_info_bar
from ok.gui.widget.CustomTab import CustomTab
from src.weight_presets import (
    WEIGHT_STATS, load_presets, add_preset, update_preset, delete_preset,
    reset_to_builtin, get_preset_names, compute_max_score,
)

logger = Logger.get_logger(__name__)


class AddPresetDialog(MessageBoxBase):
    """新增方案对话框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.widget.setMinimumWidth(420)
        self.viewLayout.addWidget(SubtitleLabel('新建评分权重方案', self.widget))

        self.name_edit = LineEdit(self.widget)
        self.name_edit.setPlaceholderText('方案名称（如：共解C、长离）')
        self.viewLayout.addWidget(BodyLabel('方案名称', self.widget))
        self.viewLayout.addWidget(self.name_edit)

        self.type_combo = ComboBox(self.widget)
        self.type_combo.addItems(['通用', '角色'])
        self.viewLayout.addWidget(BodyLabel('方案类型', self.widget))
        self.viewLayout.addWidget(self.type_combo)

        self.yesButton.setText('创建')
        self.cancelButton.setText('取消')

    def values(self):
        return self.name_edit.text().strip(), self.type_combo.currentText()


class WeightPresetTab(CustomTab):
    """评分权重预设管理Tab页"""

    def __init__(self):
        super().__init__()
        self.current_preset = None
        self.loading_table = False

        # --- 布局: 左右分栏 (不能直接对 self.view 设布局, 基类已有 vBoxLayout) ---
        container = QWidget()
        splitter_layout = QHBoxLayout(container)
        splitter_layout.setContentsMargins(0, 0, 0, 0)

        # === 左侧: 方案列表 ===
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 8, 0)
        left_layout.addWidget(BodyLabel('方案列表'))

        self.preset_list = ListWidget(left)
        self.preset_list.setMinimumWidth(200)
        self.preset_list.setMaximumWidth(280)
        self.preset_list.currentRowChanged.connect(self._preset_selected)
        left_layout.addWidget(self.preset_list, 1)

        # 筛选下拉
        self.filter_combo = ComboBox(left)
        self.filter_combo.addItems(['全部', '通用', '角色'])
        self.filter_combo.currentIndexChanged.connect(self._refresh_list)
        left_layout.addWidget(BodyLabel('类型筛选', left))
        left_layout.addWidget(self.filter_combo)

        # 增删按钮
        btn_row = QHBoxLayout()
        self.add_btn = PrimaryPushButton(FluentIcon.ADD, '新增')
        self.add_btn.clicked.connect(self._add_preset)
        self.del_btn = PushButton(FluentIcon.DELETE, '删除')
        self.del_btn.clicked.connect(self._delete_preset)
        btn_row.addWidget(self.add_btn)
        btn_row.addWidget(self.del_btn)
        left_layout.addLayout(btn_row)

        # 重置按钮
        self.reset_btn = PushButton(FluentIcon.SYNC, '重置为默认')
        self.reset_btn.clicked.connect(self._reset_to_builtin)
        left_layout.addWidget(self.reset_btn)

        # === 右侧: 权重编辑表格 ===
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(8, 0, 0, 0)

        # 顶部: 方案名称 + 类型 + 预估满分
        top_row = QHBoxLayout()
        self.preset_name_label = BodyLabel('请选择左侧方案', right)
        self.preset_name_label.setStyleSheet('font-size: 16px; font-weight: bold;')
        self.preset_type_label = BodyLabel('', right)
        self.max_score_label = BodyLabel('', right)
        self.max_score_label.setStyleSheet('font-size: 14px; font-weight: bold; color: #0078d4;')
        top_row.addWidget(self.preset_name_label, 1)
        top_row.addWidget(self.preset_type_label)
        top_row.addWidget(self.max_score_label)
        right_layout.addLayout(top_row)

        # 权重表格
        self.table = TableWidget(right)
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(['副词条', '权重'])
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.SelectedClicked)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.setColumnWidth(1, 200)
        self.table.setRowCount(len(WEIGHT_STATS))
        for row, stat_name in enumerate(WEIGHT_STATS):
            name_item = QTableWidgetItem(stat_name)
            name_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.table.setItem(row, 0, name_item)
            spin = DoubleSpinBox(right)
            spin.setRange(0.0, 5.0)
            spin.setSingleStep(0.1)
            spin.setDecimals(2)
            spin.setValue(0.0)
            self.table.setCellWidget(row, 1, spin)
        right_layout.addWidget(self.table, 1)

        # 底部: 保存
        bottom_row = QHBoxLayout()
        self.status_label = BodyLabel('')
        bottom_row.addWidget(self.status_label, 1)
        self.save_btn = PrimaryPushButton(FluentIcon.SAVE, '保存修改')
        self.save_btn.clicked.connect(self._save_preset)
        self.save_btn.setEnabled(False)
        bottom_row.addWidget(self.save_btn)
        right_layout.addLayout(bottom_row)

        # 组装
        splitter_layout.addWidget(left)
        splitter_layout.addWidget(right, 1)

        self.add_widget(container, stretch=1)

        self._set_edit_enabled(False)
        self._refresh_list()

    @property
    def name(self):
        return '评分权重预设'

    @property
    def icon(self):
        return FluentIcon.BOOK_SHELF

    # ============================================================
    # 列表操作
    # ============================================================
    def _refresh_list(self, select_name=None):
        preset_type = self.filter_combo.currentText() if hasattr(self, 'filter_combo') else '全部'
        names = get_preset_names(preset_type if preset_type != '全部' else None)
        self.preset_list.blockSignals(True)
        self.preset_list.clear()
        select_row = -1
        for row, name in enumerate(names):
            item = QListWidgetItem(name)
            self.preset_list.addItem(item)
            if name == select_name:
                select_row = row
        self.preset_list.blockSignals(False)
        if select_row >= 0:
            self.preset_list.setCurrentRow(select_row)
        elif names:
            self.preset_list.setCurrentRow(0)
        else:
            self.current_preset = None
            self._set_edit_enabled(False)

    def _preset_selected(self, row):
        if row < 0:
            return
        item = self.preset_list.item(row)
        if item is None:
            return
        name = item.text()
        self.current_preset = name
        self._load_preset_to_table(name)
        self._set_edit_enabled(True)

    def _load_preset_to_table(self, name):
        presets = load_presets()
        info = presets.get(name)
        if info is None:
            return
        self.loading_table = True
        self.preset_name_label.setText(name)
        self.preset_type_label.setText(f'[{info.get("type", "")}]')
        weights = info.get('weights', {})
        for row, stat_name in enumerate(WEIGHT_STATS):
            spin = self.table.cellWidget(row, 1)
            if spin:
                spin.setValue(float(weights.get(stat_name, 0.0)))
        self.loading_table = False
        self._update_max_score(weights)
        self.status_label.setText('')

    # ============================================================
    # 增删改
    # ============================================================
    def _add_preset(self):
        dialog = AddPresetDialog(self.window())
        if not dialog.exec():
            return
        name, preset_type = dialog.values()
        if not name:
            show_info_bar(self.window(), '方案名称不能为空', title='错误', error=True)
            return
        # 新方案默认所有权重为0
        weights = {stat: 0.0 for stat in WEIGHT_STATS}
        ok, err = add_preset(name, preset_type, weights)
        if ok:
            self._refresh_list(name)
            show_info_bar(self.window(), f'方案[{name}]已创建', title='成功')
        else:
            show_info_bar(self.window(), err, title='错误', error=True)

    def _delete_preset(self):
        if not self.current_preset:
            return
        name = self.current_preset
        box = MessageBox('删除方案', f'确认删除方案[{name}]?', self.window())
        if not box.exec():
            return
        ok, err = delete_preset(name)
        if ok:
            self.current_preset = None
            self._refresh_list()
            self._set_edit_enabled(False)
            show_info_bar(self.window(), f'方案[{name}]已删除', title='成功')
        else:
            show_info_bar(self.window(), err, title='错误', error=True)

    def _save_preset(self):
        if not self.current_preset:
            return
        weights = {}
        for row, stat_name in enumerate(WEIGHT_STATS):
            spin = self.table.cellWidget(row, 1)
            if spin:
                weights[stat_name] = round(spin.value(), 2)
        ok, err = update_preset(self.current_preset, weights)
        if ok:
            self._update_max_score(weights)
            self.status_label.setText('已保存')
            show_info_bar(self.window(), f'方案[{self.current_preset}]已保存', title='成功')
        else:
            show_info_bar(self.window(), err, title='错误', error=True)

    def _reset_to_builtin(self):
        box = MessageBox('重置默认', '确认重置所有方案为内置默认? 此操作会清除自定义方案!', self.window())
        if not box.exec():
            return
        reset_to_builtin()
        self.current_preset = None
        self._refresh_list()
        self._set_edit_enabled(False)
        show_info_bar(self.window(), '已重置为内置默认方案', title='成功')

    def _set_edit_enabled(self, enabled):
        self.table.setEnabled(enabled)
        self.save_btn.setEnabled(enabled)
        self.del_btn.setEnabled(enabled)
        if not enabled:
            self.preset_name_label.setText('请选择左侧方案')
            self.preset_type_label.setText('')
            self.max_score_label.setText('')
            self.loading_table = True
            for row in range(len(WEIGHT_STATS)):
                spin = self.table.cellWidget(row, 1)
                if spin:
                    spin.setValue(0.0)
            self.loading_table = False
            self.status_label.setText('')

    def _update_max_score(self, weights):
        """计算并显示5条满值副词条的理论满分"""
        max_score = compute_max_score(weights)
        self.max_score_label.setText(f'预估满分: {max_score:.1f}')
