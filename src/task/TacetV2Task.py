# TacetV2Task.py
# ============================================================
# 二开副本：基于上游 TacetTask.py（上游原版保留不动）
# 改进点：
#   1. 无音区选择改为名称下拉（tacet_names.py 维护，带角色/属性备注）
#   2. structure 从 TACET_GROUPS 动态派生（新增无音区只需改 tacet_names.py）
#   3. farm_tacet 名称→序号转换 wrapper，主体逻辑完全跟上游走（上游更新零同步成本）
#   4. BookTargetMixin：F2 列表点击增强（校准滚动/story 弹窗/日志）
# ============================================================
from src.task.BookTargetMixin import BookTargetMixin
from src.task.TacetTask import TacetTask
from src.task.tacet_names import TACET_NAMES, TACET_GROUPS


# 注意: BookTargetMixin 必须放在继承列表第一位（原因见 FarmEchoV2Task 注释）。
class TacetV2Task(BookTargetMixin, TacetTask):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "🌊 无音区V2(二开)"
        self.description = "Farms the selected Tacet Suppression, until no stamina. Must be able to teleport (F2)."
        self.support_schedule_task = True
        self.default_config['Which Tacet Suppression to Farm'] = TACET_NAMES[0]
        self.structure = [len(group) for group in TACET_GROUPS]
        self.total_number = sum(self.structure)
        self.config_description['Which Tacet Suppression to Farm'] = 'Select the Tacet Suppression to farm.'
        self.config_type['Which Tacet Suppression to Farm'] = {
            'type': 'drop_down',
            'options': TACET_NAMES,
        }

    def _normalize_tacet_config(self, config):
        """名称→序号转换，兼容旧数字配置与 DailyV2Task 传入的 config。"""
        value = config.get('Which Tacet Suppression to Farm', TACET_NAMES[0])
        if not isinstance(value, int):
            if value not in TACET_NAMES:  # 列表更新后旧配置名失效，回退第一个
                self.log_info(f'tacet target "{value}" not in list, falling back to {TACET_NAMES[0]}')
                config['Which Tacet Suppression to Farm'] = TACET_NAMES[0]
                return config
            config['Which Tacet Suppression to Farm'] = TACET_NAMES.index(value) + 1
            self.log_info(f'TacetV2Task: tacet target "{value}" -> #{TACET_NAMES.index(value) + 1}')
        return config

    def farm_tacet(self, daily=False, used_stamina=0, config=None, max_recovery_retries=3):
        """转换名称配置后，主体逻辑交给上游 farm_tacet。"""
        if config is None:
            config = self.config
        config = self._normalize_tacet_config(config)
        return super().farm_tacet(daily=daily, used_stamina=used_stamina, config=config,
                                   max_recovery_retries=max_recovery_retries)
