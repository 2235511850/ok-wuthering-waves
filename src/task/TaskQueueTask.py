"""任务队列执行引擎：从 task_queue.json 读取当前 profile 的 enabled 任务，依次执行。

执行时临时覆盖 task 实例的 config，执行完还原。
"""
from ok import Logger

from src.task.WWOneTimeTask import WWOneTimeTask
from src.task.BaseWWTask import BaseWWTask
from src.task.TaskQueueManager import TaskQueueManager

logger = Logger.get_logger(__name__)

STOP_ON_ERROR = '出错即停止'


class TaskQueueTask(WWOneTimeTask, BaseWWTask):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "📋 任务队列"
        self.description = "按顺序依次执行多个任务"
        self.support_schedule_task = True
        self.visible = False  # 不在 onetime tab 显示，有独立侧边栏入口

        self.default_config = {
            STOP_ON_ERROR: False,
        }
        self.config_description = {
            STOP_ON_ERROR: '开启后，任一任务失败即停止整个队列。'
                           '关闭时，失败任务截图后跳过，继续执行下一个。',
        }
        self.add_exit_after_config()
        self._queue_manager = None

    @property
    def queue_manager(self):
        if self._queue_manager is None:
            self._queue_manager = TaskQueueManager()
        return self._queue_manager

    def _find_task_by_class_name(self, class_name):
        """按类名从已注册任务中查找任务实例。"""
        for task in self.executor.onetime_tasks:
            if type(task).__name__ == class_name:
                return task
        return None

    def _run_entry(self, entry, index, total):
        """执行单个队列条目：覆盖 config → run → 还原。"""
        task_name = entry['display_name']
        task_class = entry['task_class']
        entry_config = entry.get('config', {})

        target_task = self._find_task_by_class_name(task_class)
        if target_task is None:
            self.log_error(f'Task not found: {task_class}')
            return False

        self.info_set('Queue Progress', f'{index + 1}/{total}')
        self.info_set('Running', task_name)
        self.log_info(f'Queue: starting {task_name} ({index + 1}/{total})')

        # 保存原始 config，覆盖为条目配置
        old_config = dict(target_task.config)
        try:
            # 覆盖配置（只覆盖条目中有的 key）
            for key, value in entry_config.items():
                target_task.config[key] = value
            self.run_task_by_class(type(target_task))
            self.log_info(f'Queue: {task_name} completed ({index + 1}/{total})')
            return True
        except Exception as e:
            self.log_error(f'Queue: {task_name} failed', e)
            self.screenshot(f'queue_{task_name}')
            return False
        finally:
            # 还原 config
            target_task.config.clear()
            dict.update(target_task.config, old_config)

    def run(self):
        WWOneTimeTask.run(self)

        manager = self.queue_manager
        manager.load()  # 重新加载最新数据
        entries = [t for t in manager.get_current_tasks() if t.get('enabled', True)]
        stop_on_error = self.config.get(STOP_ON_ERROR, False)

        if not entries:
            self.log_info('No tasks in queue')
            return

        total = len(entries)
        completed = []
        failed = []

        for i, entry in enumerate(entries):
            success = self._run_entry(entry, i, total)
            if success:
                completed.append(entry['display_name'])
            else:
                failed.append(entry['display_name'])
                if stop_on_error:
                    self.info_set('Queue Stopped', f'{entry["display_name"]} failed')
                    break
            self.ensure_main(time_out=30)

        self.info_set('Running', None)
        self.info_set('Queue Progress', f'{total}/{total}')
        self.info_set('Completed', completed)
        self.info_set('Failed', failed)
        self.log_info(f'Queue finished: {len(completed)} completed, {len(failed)} failed', notify=True)


from ok import run_task
from config import config

if __name__ == "__main__":
    run_task(config, task=TaskQueueTask, debug=True)
