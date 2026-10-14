# DailyV2Task.py
# ============================================================
# 二开副本：基于上游 DailyTask.py（上游原版保留不动）
# 改进点：
#   1. 每日任务的无音区选择改为名称下拉（与 TacetV2Task 统一）
#   2. run 完全继承上游——farm 联动靠替换注册：
#      config.py 用本类替换 DailyTask、TacetV2Task 替换 TacetTask 后，
#      上游 run 里的 get_task_by_class(TacetTask) 按 isinstance 自动命中 V2 实例
# ============================================================
from src.task.DailyTask import DailyTask
from src.task.tacet_names import TACET_NAMES


class DailyV2Task(DailyTask):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "📅 每日任务V2(二开)"
        self.default_config['Which Tacet Suppression to Farm'] = TACET_NAMES[0]
        self.config_description['Which Tacet Suppression to Farm'] = 'Select the Tacet Suppression to farm.'
        self.config_type['Which Tacet Suppression to Farm'] = {
            'type': 'drop_down',
            'options': TACET_NAMES,
        }
