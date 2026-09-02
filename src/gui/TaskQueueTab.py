"""任务队列 Tab — 多 profile 管理任务队列，每个条目独立配置。

UI 结构：
  工具栏：[选择配置 ▾] [新建] [删除] | [添加任务 ▾] [出错即停止 ◯] [▶ 全部运行]
  卡片列表：每个条目一张 ConfigCard，带启用开关 + 上移/下移/删除/单独运行按钮
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel, ComboBox, FluentIcon, NavigationItemPosition,
    PrimaryPushButton, PrimaryToolButton, PushButton, SwitchButton,
    MessageBoxBase, SubtitleLabel, ToolButton,
)

from ok import Logger, og
from ok.ui.qt.widget.CustomTab import CustomTab
from ok.ui.qt.tasks.ConfigCard import ConfigCard
from ok.core.events import communicate
from src.task.TaskQueueManager import (
    TaskQueueManager, QueueConfig, EXCLUDE_NAMES,
    merge_config, clean_default,
)
from src.task.TaskQueueTask import TaskQueueTask

logger = Logger.get_logger(__name__)


class InputDialog(MessageBoxBase):
    """简单的文本输入对话框。"""

    def __init__(self, title, label, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.widget.setMinimumWidth(300)
        self.title_label = SubtitleLabel(title, self.widget)
        self.viewLayout.addWidget(self.title_label)
        self.label = BodyLabel(label, self.widget)
        self.viewLayout.addWidget(self.label)
        from qfluentwidgets import LineEdit
        self.line_edit = LineEdit(self.widget)
        self.viewLayout.addWidget(self.line_edit)
        self.yesButton.setText(self.tr('确定'))
        self.cancelButton.setText(self.tr('取消'))

    def get_text(self):
        return self.line_edit.text().strip()


class QueueEntryCard(QWidget):
    """单个队列条目卡片：标题行 + ConfigCard 配置区。"""

    def __init__(self, entry, task_template, on_config_changed, on_remove, on_move,
                 on_toggle, on_run_single, parent=None):
        super().__init__(parent)
        self.entry = entry
        self.task_template = task_template
        self._on_config_changed = on_config_changed
        self._on_remove = on_remove
        self._on_move = on_move
        self._on_toggle = on_toggle
        self._on_run_single = on_run_single

        # 卡片高度随内容自适应，不撑满剩余空间（避免条目少时居中+自适应间距）
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # --- 标题行 ---
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)

        self.enabled_switch = SwitchButton()
        self.enabled_switch.setChecked(entry.get('enabled', True))
        self.enabled_switch.checkedChanged.connect(self._on_enabled_changed)
        header.addWidget(self.enabled_switch)

        self.name_label = BodyLabel(entry.get('display_name_i18n', entry['display_name']))
        header.addWidget(self.name_label, stretch=1)

        # 上移/下移/删除/单独运行（ToolButton 纯图标按钮，图标居中渲染）
        self.up_btn = ToolButton(FluentIcon.UP)
        self.up_btn.setFixedSize(32, 32)
        self.up_btn.setToolTip('上移')
        self.up_btn.clicked.connect(lambda: self._on_move(entry['id'], 'up'))
        header.addWidget(self.up_btn)

        self.down_btn = ToolButton(FluentIcon.DOWN)
        self.down_btn.setFixedSize(32, 32)
        self.down_btn.setToolTip('下移')
        self.down_btn.clicked.connect(lambda: self._on_move(entry['id'], 'down'))
        header.addWidget(self.down_btn)

        self.run_btn = PrimaryToolButton(FluentIcon.PLAY)
        self.run_btn.setFixedSize(32, 32)
        self.run_btn.setToolTip('单独运行')
        self.run_btn.clicked.connect(lambda: self._on_run_single(entry['id']))
        header.addWidget(self.run_btn)

        self.del_btn = ToolButton(FluentIcon.DELETE)
        self.del_btn.setFixedSize(32, 32)
        self.del_btn.setToolTip('删除')
        self.del_btn.clicked.connect(lambda: self._on_remove(entry['id']))
        header.addWidget(self.del_btn)

        layout.addLayout(header)

        # --- 配置区（ConfigCard） ---
        default = clean_default(dict(task_template.default_config))
        merged = merge_config(entry.get('config', {}), default)

        def _save_callback():
            self._on_config_changed(entry['id'], dict(self.config_card.config))

        self.queue_config = QueueConfig(merged, default, on_change=_save_callback)

        self.config_card = ConfigCard(
            task=task_template,
            name=entry.get('display_name_i18n', entry['display_name']),
            config=self.queue_config,
            description='',
            default_config=default,
            config_description=dict(task_template.config_description) if task_template.config_description else {},
            config_type=dict(task_template.config_type) if task_template.config_type else {},
            config_icon=None,
        )
        self.config_card.setExpand(True)
        layout.addWidget(self.config_card)

    def _on_enabled_changed(self, checked):
        self._on_toggle(self.entry['id'], checked)

    def set_running(self, running):
        """队列运行中禁用操作按钮。"""
        self.up_btn.setEnabled(not running)
        self.down_btn.setEnabled(not running)
        self.run_btn.setEnabled(not running)
        self.del_btn.setEnabled(not running)
        self.enabled_switch.setEnabled(not running)


class TaskQueueTab(CustomTab):
    """侧边栏独立 Tab — 任务队列管理。"""

    def __init__(self):
        super().__init__()
        self.manager = TaskQueueManager()
        self.entry_cards = []  # QueueEntryCard 列表
        self._is_running = False

        self._build_toolbar()
        self._build_add_task_area()
        self.refresh_entries()

        communicate.task.connect(self._on_task_status)
        communicate.task_list_updated.connect(self._on_task_list_updated)

    @property
    def name(self):
        return self.tr("任务队列")

    @property
    def icon(self):
        return FluentIcon.MENU

    @property
    def position(self):
        return NavigationItemPosition.SCROLL

    @property
    def add_after_default_tabs(self):
        return False

    # --- UI 构建 ---
    def _build_toolbar(self):
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(0, 4, 0, 4)

        self.profile_combo = ComboBox()
        self._refresh_profiles()
        self.profile_combo.currentTextChanged.connect(self._on_profile_changed)
        toolbar.addWidget(BodyLabel(self.tr('配置:')))
        toolbar.addWidget(self.profile_combo)

        new_btn = PushButton(FluentIcon.ADD, self.tr('新建'))
        new_btn.clicked.connect(self._on_new_profile)
        toolbar.addWidget(new_btn)

        del_btn = PushButton(FluentIcon.DELETE, self.tr('删除配置'))
        del_btn.clicked.connect(self._on_delete_profile)
        toolbar.addWidget(del_btn)

        toolbar.addStretch(1)

        self.stop_on_error_switch = SwitchButton()
        self.stop_on_error_switch.setChecked(self.manager.get_stop_on_error())
        self.stop_on_error_switch.checkedChanged.connect(self._on_stop_on_error_changed)
        toolbar.addWidget(BodyLabel(self.tr('出错即停止')))
        toolbar.addWidget(self.stop_on_error_switch)

        self.run_all_btn = PrimaryPushButton(FluentIcon.PLAY, self.tr('全部运行'))
        self.run_all_btn.clicked.connect(self._on_run_all)
        toolbar.addWidget(self.run_all_btn)

        self.addLayout(toolbar)

    def _build_add_task_area(self):
        add_layout = QHBoxLayout()
        add_layout.setContentsMargins(0, 4, 0, 4)

        self.task_combo = ComboBox()
        self.task_combo.setPlaceholderText(self.tr('选择任务添加到队列...'))
        self._refresh_task_combo()
        add_layout.addWidget(self.task_combo, stretch=1)

        add_btn = PushButton(FluentIcon.ADD, self.tr('添加'))
        add_btn.clicked.connect(self._on_add_task)
        add_layout.addWidget(add_btn)

        self.addLayout(add_layout)

    # --- 刷新 UI ---
    def _refresh_profiles(self):
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        for name in self.manager.get_profile_names():
            self.profile_combo.addItem(name)
        self.profile_combo.setCurrentText(self.manager.current_profile)
        self.profile_combo.blockSignals(False)

    def _refresh_task_combo(self):
        """刷新可选任务下拉列表。"""
        self.task_combo.clear()
        self.task_combo.addItem('')
        if og.executor and og.executor.onetime_tasks:
            for task in og.executor.onetime_tasks:
                if task.name in EXCLUDE_NAMES:
                    continue
                if not getattr(task, 'visible', True):
                    continue
                display = og.app.tr(task.name) if og.app else task.name
                self.task_combo.addItem(display)

    def refresh_entries(self):
        """重新渲染当前 profile 的所有条目卡片。"""
        # 清除旧卡片
        for card in self.entry_cards:
            self.removeWidget(card)
            card.deleteLater()
        self.entry_cards.clear()

        entries = self.manager.get_current_tasks()
        for entry in entries:
            task_template = self._find_task_template(entry['task_class'])
            if task_template is None:
                logger.warning(f'Task template not found: {entry["task_class"]}')
                continue

            # 显示名经过 tr() 翻译（display_name 存英文，框架 i18n 自动翻译）
            entry['display_name_i18n'] = og.app.tr(entry['display_name']) if og.app else entry['display_name']

            card = QueueEntryCard(
                entry=entry,
                task_template=task_template,
                on_config_changed=self._on_config_changed,
                on_remove=self._on_remove_task,
                on_move=self._on_move_task,
                on_toggle=self._on_toggle_task,
                on_run_single=self._on_run_single,
            )
            card.set_running(self._is_running)
            self.add_widget(card)
            self.entry_cards.append(card)

    # --- 事件处理 ---
    def _on_profile_changed(self, name):
        if name and name != self.manager.current_profile:
            self.manager.switch_profile(name)
            self.stop_on_error_switch.setChecked(self.manager.get_stop_on_error())
            self.refresh_entries()

    def _on_new_profile(self):
        dialog = InputDialog(self.tr('新建配置'), self.tr('输入配置名称:'), self.window())
        if dialog.exec():
            name = dialog.get_text()
            if name:
                self.manager.add_profile(name)
                self._refresh_profiles()
                self.refresh_entries()

    def _on_delete_profile(self):
        if len(self.manager.profiles) <= 1:
            return
        name = self.manager.current_profile
        from qfluentwidgets import MessageBox
        msg = MessageBox(self.tr('确认删除'), self.tr(f'确定删除配置「{name}」?'), self.window())
        if msg.exec():
            self.manager.delete_profile(name)
            self._refresh_profiles()
            self.refresh_entries()

    def _on_add_task(self):
        task_name = self.task_combo.currentText()
        if not task_name:
            return
        task_template = self._find_task_by_display_name(task_name)
        if task_template is None:
            return
        # 用任务默认配置创建条目，display_name 存原始英文（i18n 翻译在显示时进行）
        default = clean_default(dict(task_template.default_config))
        entry = self.manager.add_task(
            task_class=type(task_template).__name__,
            display_name=task_template.name,
            config=dict(default),
        )
        self.refresh_entries()

    def _on_remove_task(self, entry_id):
        self.manager.remove_task(entry_id)
        self.refresh_entries()

    def _on_move_task(self, entry_id, direction):
        self.manager.move_task(entry_id, direction)
        self.refresh_entries()

    def _on_toggle_task(self, entry_id, enabled):
        self.manager.set_task_enabled(entry_id, enabled)

    def _on_config_changed(self, entry_id, config):
        self.manager.update_task_config(entry_id, config)

    def _on_stop_on_error_changed(self, checked):
        self.manager.set_stop_on_error(checked)

    def _on_run_all(self):
        """启动 TaskQueueTask 执行整个队列。"""
        task = og.executor.get_task_by_class(TaskQueueTask)
        if task:
            # 同步 stop_on_error 到 task config
            task.config['出错即停止'] = self.manager.get_stop_on_error()
            task.enable()

    def _on_run_single(self, entry_id):
        """单独运行一个任务条目。"""
        if self._is_running:
            return
        entry = self.manager.get_entry(entry_id)
        if entry is None:
            return
        task_template = self._find_task_template(entry['task_class'])
        if task_template is None:
            return
        # 覆盖 config 后启动
        old_config = dict(task_template.config)
        for key, value in entry.get('config', {}).items():
            task_template.config[key] = value
        # TODO: 还原 config 需要在任务完成后执行
        # 暂时用 communicate.task_done 信号监听完成
        class _RestoreGuard:
            def __init__(self, task, old_cfg):
                self.task = task
                self.old_cfg = old_cfg
                self.restored = False

            def restore(self, *_):
                if not self.restored:
                    self.task.config.clear()
                    dict.update(self.task.config, self.old_cfg)
                    self.restored = True
                    communicate.task_done.disconnect(self.restore)

        guard = _RestoreGuard(task_template, old_config)
        communicate.task_done.connect(guard.restore)
        task_template.enable()

    def _on_task_status(self, task):
        """监听任务状态变化，更新运行状态。"""
        if isinstance(task, TaskQueueTask) or (task is None and self._is_running):
            running = task is not None and getattr(task, 'running', False)
            self._is_running = running
            for card in self.entry_cards:
                card.set_running(running)

    def _on_task_list_updated(self):
        """任务列表更新时刷新下拉列表。"""
        self._refresh_task_combo()

    # --- 工具方法 ---
    def _find_task_template(self, class_name):
        """按类名从已注册 onetime tasks 中查找。"""
        if not og.executor:
            return None
        for task in og.executor.onetime_tasks:
            if type(task).__name__ == class_name:
                return task
        return None

    def _find_task_by_display_name(self, display_name):
        """按显示名查找任务实例（display_name 可能是翻译后的名字）。"""
        if not og.executor:
            return None
        for task in og.executor.onetime_tasks:
            tr_name = og.app.tr(task.name) if og.app else task.name
            if tr_name == display_name or task.name == display_name:
                return task
        return None
