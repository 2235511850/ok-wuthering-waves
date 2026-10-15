# FarmEchoV2Task.py
# ============================================================
# 二开副本：基于上游 FarmEchoTask.py（上游原版保留不动）
# 改进点：
#   1. 战歌重奏/强敌讨伐/梦魇祓除传送目标全部改为名称下拉（boss_names.py 维护）
#   2. 梦魇祓除入口（上游叫 Special Nightmare 数字版，本版为 Nightmare Challenge 名称下拉，序号偏移5跳过梦魇聚落）
#   3. teleport_to_configured_boss 完整重写：名称→序号 + story 弹窗分支（确认后跳过组队挑战）
#   4. BookTargetMixin：F2 列表点击增强（校准滚动/story 弹窗/日志）
#   5. boss/weekly 总数从 boss_names.py 动态派生（上游硬编码 9/20 已过时）
# ============================================================
from ok import Logger
from src.task.BookTargetMixin import BookTargetMixin
from src.task.FarmEchoTask import FarmEchoTask
from src.task.boss_names import (
    BOSS_CHALLENGE_NAMES, WEEKLY_CHALLENGE_NAMES,
    BOSS_CHALLENGE_STRUCTURE, WEEKLY_CHALLENGE_STRUCTURE,
    NIGHTMARE_CHALLENGE_NAMES, NIGHTMARE_CHALLENGE_STRUCTURE,
    NIGHTMARE_CHALLENGE_TOTAL, NIGHTMARE_NEST_COUNT,
)

logger = Logger.get_logger(__name__)


# 注意: BookTargetMixin 必须放在继承列表第一位。
# 若写成 (FarmEchoTask, BookTargetMixin)，MRO 中 BaseWWTask 会先于 Mixin 出现，
# 上游的 click_on_book_target 会拦截 Mixin 的增强版（弹窗兼容/日志全部失效）。
class FarmEchoV2Task(BookTargetMixin, FarmEchoTask):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "🌀 刷4C声骸V2(二开)"
        self.description = "Click Start after Entering Dungeon or Teleporting to The Boss"
        self.default_config['Which Weekly Boss to Teleport'] = WEEKLY_CHALLENGE_NAMES[0]
        self.default_config['Which Boss Challenge to Teleport'] = BOSS_CHALLENGE_NAMES[0]
        self.default_config.pop('Which Special Nightmare to Teleport', None)
        self.default_config['Which Nightmare Boss to Teleport'] = NIGHTMARE_CHALLENGE_NAMES[0]
        self.config_description['Which Weekly Boss to Teleport'] = '选择要传送的战歌重奏boss'
        self.config_description['Which Boss Challenge to Teleport'] = '选择要传送的强敌讨伐boss'
        self.config_description['Which Nightmare Boss to Teleport'] = '选择要传送的梦魇祓除boss'
        self.book_structures = {
            'Boss Challenge': BOSS_CHALLENGE_STRUCTURE,
            'Weekly Challenge': WEEKLY_CHALLENGE_STRUCTURE,
            'Nightmare Challenge': NIGHTMARE_CHALLENGE_STRUCTURE,
        }
        self.total_weekly_number = sum(WEEKLY_CHALLENGE_STRUCTURE)
        self.total_boss_number = sum(BOSS_CHALLENGE_STRUCTURE)
        self.total_nightmare_number = NIGHTMARE_CHALLENGE_TOTAL
        self.config_type['Teleport to Boss'] = {'type': "drop_down",
                                                'options': ['No', 'Weekly Challenge',
                                                            'Boss Challenge',
                                                            'Nightmare Challenge'],
                                                'sub_configs': {
                                                    'Weekly Challenge': ['Which Weekly Boss to Teleport', 'Boss Level'],
                                                    'Boss Challenge': ['Which Boss Challenge to Teleport',
                                                                       'Boss Level'],
                                                    'Nightmare Challenge': ['Which Nightmare Boss to Teleport'],
                                                }}
        self.config_type['Which Weekly Boss to Teleport'] = {'type': "drop_down",
                                                             'options': WEEKLY_CHALLENGE_NAMES}
        self.config_type['Which Boss Challenge to Teleport'] = {'type': "drop_down",
                                                                'options': BOSS_CHALLENGE_NAMES}
        self.config_type['Which Nightmare Boss to Teleport'] = {'type': "drop_down",
                                                                'options': NIGHTMARE_CHALLENGE_NAMES}

    def teleport_to_configured_boss(self):
        teleport_to_boss = self.config.get('Teleport to Boss', 'No')
        self.log_info(f'teleport_to_configured_boss start: Teleport to Boss={teleport_to_boss}')
        self.ensure_main(time_out=180)
        structure = None
        if teleport_to_boss == 'Weekly Challenge':
            feature = 'zhange'
            config_key = 'Which Weekly Boss to Teleport'
            boss_names = WEEKLY_CHALLENGE_NAMES
            total_number = self.total_weekly_number
        elif teleport_to_boss == 'Boss Challenge':
            feature = 'qiangdi'
            config_key = 'Which Boss Challenge to Teleport'
            boss_names = BOSS_CHALLENGE_NAMES
            total_number = self.total_boss_number
        elif teleport_to_boss == 'Nightmare Challenge':
            feature = 'mengyan'
            config_key = 'Which Nightmare Boss to Teleport'
            boss_names = NIGHTMARE_CHALLENGE_NAMES
            total_number = self.total_nightmare_number
        else:
            raise RuntimeError(f'Unknown Teleport to Boss config: {teleport_to_boss}')

        boss_name = self.config.get(config_key, boss_names[0])
        if boss_name not in boss_names:  # 列表更新后旧配置名失效，回退第一个
            self.log_info(f'teleport target "{boss_name}" not in list, falling back to {boss_names[0]}')
            self.config[config_key] = boss_names[0]
            boss_name = boss_names[0]

        # For Nightmare Challenge, boss serial number is offset by the nest group
        # (5 nests come before the 10 nightmare bosses in the F2 book)
        if teleport_to_boss == 'Nightmare Challenge':
            serial_number = boss_names.index(boss_name) + 1 + NIGHTMARE_NEST_COUNT
        else:
            serial_number = boss_names.index(boss_name) + 1
        self.log_info(f'teleport target: {boss_name} (#{serial_number}/{total_number})')
        self.info_set('Teleport to Boss', f'{teleport_to_boss} {boss_name} #{serial_number}')
        self.openF2Book('gray_book_boss')
        self.open_boss_book(feature)
        structure = self.book_structures.get(teleport_to_boss)
        self.log_info(f'book_structures: {self.book_structures}, structure for {teleport_to_boss}: {structure}')
        self.log_info(
            f'calling click_on_book_target(serial_number={serial_number}, total_number={total_number}, structure={structure})')
        is_team = self.click_on_book_target(serial_number, total_number, structure)
        self.log_info(f'click_on_book_target returned is_team={is_team}')
        if is_team == 'story':
            # Story dialog confirmed: already loaded into boss realm, skip team challenge
            self.log_info('story dialog: already in realm, skip click_team_challenge')
        elif is_team:
            if teleport_to_boss == 'Weekly Challenge':
                self.click_configured_boss_level()
                self.click_solo_challenge()
            self.click_team_challenge()
            self.wait_in_team_and_world(time_out=120)
            self.sleep(2)
        else:
            self.realm_entry_at_heal_point = False  # 传送到 boss 附近再走进本, 退本不会回到信标
            self.wait_click_travel()
            self.wait_in_team_and_world(time_out=120)
            self.sleep(2)
        return is_team == True or is_team == 'story'
