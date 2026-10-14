"""任务队列数据管理：多 profile、JSON 持久化、CRUD 操作。"""
import json
import uuid
from pathlib import Path

QUEUE_FILE = Path('configs/task_queue.json')

# 排除出队列选择的任务：
# - TaskQueueTask 自身防止递归
# - DailyTask 内含子任务，单独排队重复消耗体力
# - MultiAccountDailyTask 自带多账号切换
EXCLUDE_NAMES = {'📋 任务队列', '👥 Multi Account Daily Task', '📅 Daily Task', '📅 每日任务V2(二开)'}

# V2 替换注册后的旧类名迁移（旧 task_queue.json 里的 task_class 自动升级）
LEGACY_CLASS_MIGRATION = {
    'TacetTask': 'TacetV2Task',
    'FarmEchoTask': 'FarmEchoV2Task',
    'DailyTask': 'DailyV2Task',
}


class QueueConfig(dict):
    """轻量 Config 替代品，供 ConfigCard 渲染用。

    继承 dict，提供 get_default / has_user_config 等方法，
    但不自动写文件（由 TaskQueueManager 统一持久化）。
    """

    def __init__(self, values, default, on_change=None):
        super().__init__()
        dict.update(self, values)
        self.default = default
        self._on_change = on_change

    def get_default(self, key):
        return self.default.get(key)

    def has_user_config(self):
        return not all(key.startswith('_') for key in self)

    def reset_to_default(self):
        self.clear()
        dict.update(self, self.default)
        if self._on_change:
            self._on_change()

    def __setitem__(self, key, value):
        if value != self.get(key):
            super().__setitem__(key, value)
            if self._on_change:
                self._on_change()

    def save_file(self):
        pass


def merge_config(saved, default):
    """合并保存的配置和默认配置，补全缺失的 key。"""
    merged = dict(default)
    merged.update(saved)
    return merged


def clean_config(config):
    """清除不应在队列条目中出现的配置项。"""
    return {k: v for k, v in config.items()
            if k not in ('_enabled', 'Exit After Task')}


def clean_default(default):
    """清除默认配置中不应在队列条目中渲染的项。"""
    return {k: v for k, v in default.items()
            if k not in ('_enabled', 'Exit After Task')}


class TaskQueueManager:
    """任务队列数据管理器，负责 profiles 和 task entries 的 CRUD。"""

    def __init__(self):
        self.profiles = {}
        self.current_profile = None
        self.load()

    def load(self):
        if QUEUE_FILE.exists():
            try:
                with open(QUEUE_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.profiles = data.get('profiles', {})
                self.current_profile = data.get('current_profile')
                self._migrate_legacy_classes()
            except (json.JSONDecodeError, IOError):
                pass
        if not self.profiles:
            self.profiles = {'默认': {'tasks': [], 'stop_on_error': False}}
            self.current_profile = '默认'
        if self.current_profile not in self.profiles:
            self.current_profile = list(self.profiles.keys())[0]

    def _migrate_legacy_classes(self):
        """旧类名（TacetTask 等）迁移为 V2 类名，有变化则落盘。"""
        changed = False
        for profile in self.profiles.values():
            for entry in profile.get('tasks', []):
                old = entry.get('task_class')
                new = LEGACY_CLASS_MIGRATION.get(old)
                if new:
                    entry['task_class'] = new
                    changed = True
        if changed:
            self.save()

    def save(self):
        QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {
            'profiles': self.profiles,
            'current_profile': self.current_profile,
        }
        with open(QUEUE_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # --- Profile operations ---
    def get_profile_names(self):
        return list(self.profiles.keys())

    def add_profile(self, name):
        if name and name not in self.profiles:
            self.profiles[name] = {'tasks': [], 'stop_on_error': False}
            self.current_profile = name
            self.save()

    def delete_profile(self, name):
        if name in self.profiles and len(self.profiles) > 1:
            del self.profiles[name]
            if self.current_profile == name:
                self.current_profile = list(self.profiles.keys())[0]
            self.save()

    def switch_profile(self, name):
        if name in self.profiles:
            self.current_profile = name
            self.save()

    # --- Task entry operations ---
    def get_current_tasks(self):
        return self.profiles.get(self.current_profile, {}).get('tasks', [])

    def get_entry(self, entry_id):
        for t in self.get_current_tasks():
            if t['id'] == entry_id:
                return t
        return None

    def add_task(self, task_class, display_name, config):
        entry = {
            'id': str(uuid.uuid4()),
            'task_class': task_class,
            'display_name': display_name,
            'config': clean_config(config),
            'enabled': True,
        }
        profile = self.profiles.setdefault(self.current_profile, {})
        profile.setdefault('tasks', []).append(entry)
        self.save()
        return entry

    def remove_task(self, entry_id):
        tasks = self.get_current_tasks()
        self.profiles[self.current_profile]['tasks'] = [
            t for t in tasks if t['id'] != entry_id
        ]
        self.save()

    def move_task(self, entry_id, direction):
        tasks = self.get_current_tasks()
        for i, t in enumerate(tasks):
            if t['id'] == entry_id:
                if direction == 'up' and i > 0:
                    tasks[i], tasks[i - 1] = tasks[i - 1], tasks[i]
                elif direction == 'down' and i < len(tasks) - 1:
                    tasks[i], tasks[i + 1] = tasks[i + 1], tasks[i]
                break
        self.save()

    def update_task_config(self, entry_id, config):
        for t in self.get_current_tasks():
            if t['id'] == entry_id:
                t['config'] = dict(config)
                break
        self.save()

    def update_task_entry(self, entry):
        """整体更新一个条目（保持 id 不变），用于名称等字段同步。"""
        for i, t in enumerate(self.get_current_tasks()):
            if t['id'] == entry['id']:
                self.profiles[self.current_profile]['tasks'][i] = entry
                break
        self.save()

    def set_task_enabled(self, entry_id, enabled):
        for t in self.get_current_tasks():
            if t['id'] == entry_id:
                t['enabled'] = enabled
                break
        self.save()

    def get_stop_on_error(self):
        return self.profiles.get(self.current_profile, {}).get('stop_on_error', False)

    def set_stop_on_error(self, value):
        self.profiles.setdefault(self.current_profile, {})['stop_on_error'] = value
        self.save()
