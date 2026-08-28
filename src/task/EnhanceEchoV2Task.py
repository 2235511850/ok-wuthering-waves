# EnhanceEchoV2Task.py
# ============================================================
# 二开副本：基于上游 EnhanceEchoTask.py（上游原版保留不动）
# 改进点：
#   1. 分批评估（三种模式：保守/标准/激进）
#   2. 自定义材料放入（金色密音筒批量添加）
#   3. 加权评分制替代原版硬规则闸门
# ============================================================
import re
import time
import os

from ok import FindFeature, Logger
from ok.feature.Box import get_bounding_box
from ok.util.file import clear_folder
from src.scene.WWScene import WWScene
from src.task.BaseWWTask import BaseWWTask

logger = Logger.get_logger(__name__)

number_pattern = re.compile(r"^[\d.%％ ]+$")
property_pattern = re.compile(r"[\u4e00-\u9fff]{2,}")

# ============================================================
# A1 数据层：副词条数值范围（下限, 上限）
# ============================================================
STAT_RANGES = {
    '暴击':               (6.3, 10.5),
    '暴击伤害':           (12.6, 21.0),
    '攻击百分比':         (6.4, 11.6),
    '生命百分比':         (6.4, 11.6),
    '防御百分比':         (8.1, 14.7),
    '共鸣效率':           (6.8, 12.4),
    '共鸣技能伤害加成':   (6.4, 11.6),
    '共鸣解放伤害加成':   (6.4, 11.6),
    '普攻伤害加成':       (6.4, 11.6),
    '重击伤害加成':       (6.4, 11.6),
    '攻击':               (30, 60),
    '生命':               (320, 580),
    '防御':               (40, 70),
}

# 所有可识别的标准属性名（用于 config 对齐）
ALL_STAT_NAMES = list(STAT_RANGES.keys())


class EnhanceEchoV2Task(BaseWWTask, FindFeature):

    # ============================================================
    # UI 坐标占位符（B阶段需截图后替换为真实值）
    # 格式: (x1, y1, x2, y2) 屏幕归一化坐标 0-1
    # ============================================================
    UI_COORDS = {
        '加号按钮':       (0.14, 0.64, 0.21, 0.71),
        '金色密音筒':     (0.35, 0.34, 0.44, 0.44),
        '弹窗返回':       (0.87, 0.12, 0.94, 0.18),
        '设置按钮':       (0.04, 0.55, 0.11, 0.62),
        '阶段放入选项':   (0.08, 0.57, 0.24, 0.64),
        '快速放入选项':   (0.08, 0.65, 0.24, 0.72),
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "⬆️ 批量强化声骸V2(二开)"
        self.description = "点击B进入背包, 在过滤器中选择需要强化的声骸, 并按照等级从0排序后开始."
        self.fail_reason = ""
        self.supported_languages = ["zh_CN", "zh_TW"]

        # ============================================================
        # A3 GUI 配置项
        # ============================================================
        self.default_config.update({
            # --- 筛选模式 ---
            '筛选模式': '保守',

            # --- 硬性底线（独立开关） ---
            '必须暴击': True,
            '必须暴击伤害': True,

            # --- 各阶段评分阈值 ---
            '保守-15级评分阈值': 10.0,
            '保守-20级评分阈值': 20.0,
            '保守-25级评分阈值': 30.0,
            '标准-20级评分阈值': 20.0,
            '标准-25级评分阈值': 30.0,
            '激进-25级评分阈值': 30.0,

            # --- 各词条权重（0-2.0，0=无效词条） ---
            '权重_暴击':             1.8,
            '权重_暴击伤害':         0.9,
            '权重_攻击百分比':       1.0,
            '权重_生命百分比':       0.5,
            '权重_防御百分比':       0.4,
            '权重_共鸣效率':         0.5,
            '权重_共鸣技能伤害加成': 1.0,
            '权重_共鸣解放伤害加成': 1.0,
            '权重_普攻伤害加成':     1.0,
            '权重_重击伤害加成':     1.0,
            '权重_攻击':             0.1,
            '权重_生命':             0.01,
            '权重_防御':             0.01,

            # --- 其他 ---
            'Pause after Success': True,
        })

        # 筛选模式：下拉单选（框架自动推断：有 options + 默认值是 str → drop_down）
        self.config_type['筛选模式'] = {
            'options': ['保守', '标准', '激进'],
        }

        self.config_description = {
            '筛选模式': '保守=0→15→20→25三级止损（最省材料）; 标准=0→20→25两级止损; 激进=0→25快速放入一步到位（最费材料）',
            '必须暴击': '开启后声骸最终必须拥有暴击词条，剩余孔位不足以凑齐则提前弃置',
            '必须暴击伤害': '开启后声骸最终必须拥有暴击伤害词条，剩余孔位不足以凑齐则提前弃置',
            '保守-15级评分阈值': '保守模式15级（3条词条）时的评分下限，低于此值弃置',
            '保守-20级评分阈值': '保守模式20级（4条词条）时的评分下限',
            '保守-25级评分阈值': '保守模式25级（5条满级）时的最终评分下限',
            '标准-20级评分阈值': '标准模式20级（4条词条）时的评分下限',
            '标准-25级评分阈值': '标准模式25级满级时的最终评分下限',
            '激进-25级评分阈值': '激进模式25级满级时的最终评分下限',
            '权重_暴击': '暴击率词条权重，0=无效，建议1.8',
            '权重_暴击伤害': '暴击伤害词条权重，建议0.9',
            '权重_攻击百分比': '攻击百分比词条权重，建议1.0',
            '权重_生命百分比': '生命百分比词条权重，奶/肉角色建议0.5+',
            '权重_防御百分比': '防御百分比词条权重，防御角色建议0.4+',
            '权重_共鸣效率': '共鸣效率词条权重，辅助建议0.5+',
            '权重_共鸣技能伤害加成': '共鸣技能伤害加成词条权重',
            '权重_共鸣解放伤害加成': '共鸣解放伤害加成词条权重',
            '权重_普攻伤害加成': '普攻伤害加成词条权重',
            '权重_重击伤害加成': '重击伤害加成词条权重',
            '权重_攻击': '固定攻击（小攻击）词条权重，数值30-60',
            '权重_生命': '固定生命词条权重，数值320-580',
            '权重_防御': '固定防御词条权重，数值40-70',
            'Pause after Success': '成功时发送通知并暂停任务',
        }

    # ============================================================
    # A4 主循环 run()
    # ============================================================
    def run(self):
        self.info_set('成功声骸数量', 0)
        self.info_set('失败声骸数量', 0)
        clear_folder('screenshots')

        while True:
            # --- 外层循环：找到0级声骸并点击培养 ---
            enhance = self.find_echo_enhance()
            if not enhance:
                raise Exception('必须在背包声骸界面过滤后开始!')
            current_level = self.is_0_level()
            if not current_level:
                total = self.info_get('成功声骸数量') + self.info_get('失败声骸数量')
                if self.debug:
                    self.screenshot('无可强化声骸')
                self.log_info(f'无可强化声骸, 任务结束! 强化{total}个, '
                              f'符合条件{self.info_get("成功声骸数量")}个', notify=True)
                if self.info_get('成功声骸数量') >= 1:
                    try:
                        os.startfile(os.path.abspath("screenshots"))
                    except Exception as e:
                        self.log_error(f"无法打开截图文件夹: {e}")
                return

            # 点击培养进入强化界面
            start = time.time()
            while time.time() - start < 5:
                if enhance:
                    self.click(enhance, after_sleep=0.5)
                enhance = self.find_echo_enhance()
                if not enhance:
                    break

            # --- 按筛选模式执行强化流程 ---
            mode = self.config.get('筛选模式')
            self.log_info(f'开始强化, 筛选模式: {mode}')

            if mode == '保守':
                self._flow_conservative()
            elif mode == '标准':
                self._flow_standard()
            elif mode == '激进':
                self._flow_aggressive()
            else:
                raise Exception(f'未知筛选模式: {mode}')

    # ============================================================
    # 三种筛选流程
    # ============================================================
    def _flow_conservative(self):
        """保守模式: 0→15评 → 阶段放入升20评 → 阶段放入升25评"""
        # 阶段1: 自定义放8个金色密音筒 → 升15
        self.add_custom_materials(8)
        r = self.evaluate_stage(self.config.get('保守-15级评分阈值'), '15级')
        if r is not True:
            return  # False=已弃置, None=已上锁(不会在15级发生)

        # 阶段2: 阶段放入 → 升20
        self.stage_add_materials()
        r = self.evaluate_stage(self.config.get('保守-20级评分阈值'), '20级')
        if r is not True:
            return

        # 阶段3: 阶段放入 → 升25
        self.stage_add_materials()
        self.evaluate_stage(self.config.get('保守-25级评分阈值'), '25级')

    def _flow_standard(self):
        """标准模式: 0→20评 → 阶段放入升25评"""
        # 阶段1: 自定义放16个金色密音筒 → 升20
        self.add_custom_materials(16)
        r = self.evaluate_stage(self.config.get('标准-20级评分阈值'), '20级')
        if r is not True:
            return

        # 阶段2: 阶段放入 → 升25
        self.stage_add_materials()
        self.evaluate_stage(self.config.get('标准-25级评分阈值'), '25级')

    def _flow_aggressive(self):
        """激进模式: 快速放入 → 直升25 → 评"""
        self.quick_add_materials()
        self.evaluate_stage(self.config.get('激进-25级评分阈值'), '25级')

    # ============================================================
    # 材料放入方法（坐标为占位符，B阶段需截图定位）
    # ============================================================
    def _click_placeholder(self, name, after_sleep=0.3):
        """点击占位坐标UI元素"""
        x1, y1, x2, y2 = self.UI_COORDS[name]
        box = self.box_of_screen(x1, y1, x2, y2)
        self.click(box, after_sleep=after_sleep)
        self.log_info(f'点击 [{name}] (占位坐标, 待B阶段校准)')

    def add_custom_materials(self, count):
        """自定义添加材料: 点加号 → 弹窗选金色密音筒×count → 返回

        ⚠️ 坐标为占位符，B阶段需截图定位
        """
        self.log_info(f'自定义添加金色密音筒 ×{count}')
        # 点加号打开弹窗
        self._click_placeholder('加号按钮', after_sleep=0.5)
        # 在弹窗中选金色密音筒
        for i in range(count):
            self._click_placeholder('金色密音筒', after_sleep=0.15)
        # 返回上一页面
        self._click_placeholder('弹窗返回', after_sleep=0.5)

    def stage_add_materials(self):
        """阶段放入材料（衔接阶段 15→20, 20→25）

        复用原版逻辑: 反复点击 OCR 找到的"阶段放入"按钮直到消失
        """
        self.log_info('阶段放入材料...')
        start_wait = time.time()
        have_add_mat = False
        while time.time() - start_wait < 5:
            add_mat = self.find_add_mat()
            if add_mat:
                have_add_mat = True
                self.click(add_mat, after_sleep=0.3)
            else:
                self.next_frame()
                if have_add_mat:
                    break
        if not have_add_mat:
            raise Exception('无法找到阶段放入按钮, 检查强化设置!')
        self.log_info('阶段放入完成')

    def quick_add_materials(self):
        """快速放入材料（激进模式: 0→25一步到位）

        ⚠️ 坐标为占位符，B阶段需截图定位
        流程: 设置选"快速放入" → 点"一键放入"
        """
        self.log_info('快速放入材料(0→25)...')
        # 设置选快速放入
        self._click_placeholder('设置按钮', after_sleep=0.3)
        self._click_placeholder('快速放入选项', after_sleep=0.3)
        # 点一键放入
        self.find_and_click_one_click_add()

    def find_and_click_one_click_add(self):
        """查找并点击"一键放入"按钮

        ⚠️ 暂用 OCR 搜索，坐标区域为占位值，B阶段需校准
        """
        if not self.wait_click_ocr(0.25, 0.85, 0.50, 0.95, match=['一键放入'],
                                   settle_time=0.1, after_sleep=0.5):
            self.log_error('找不到一键放入按钮!')
            raise Exception('找不到一键放入按钮!')
        self.log_info('点击一键放入')

    # ============================================================
    # 强化+调谐 + OCR 读取（从原版提取复用）
    # ============================================================
    def enhance_and_tune(self):
        """点击强化并调谐, 处理调谐弹窗"""
        if not self.wait_click_ocr(0.1, 0.88, 0.29, 0.96, match=['强化并调谐'],
                                   settle_time=0.1, after_sleep=1.5):
            if self.ocr(0.17, 0.88, 0.29, 0.96, match=['强化']):
                raise Exception('强化设置需要开启同步调谐!')
            else:
                raise Exception('找不到 强化并调谐!')
        while handle := self.wait_ocr(0.24, 0.18, 0.75, 0.98,
                                      match=[re.compile('不再提示'), '调谐成功', re.compile('点击任')],
                                      time_out=2):
            if handle[0].name in ['本次登录不再提示', '本次登入不再提示']:
                self.click_skip_dialog_confirm()
            elif handle[0].name in ['点击任意位置返回', '调谐成功']:
                self.click(handle, after_sleep=1)
            else:
                self.sleep(0.5)
        self.sleep(0.1)

    def ocr_read_stats(self):
        """OCR 读取当前词条属性和数值
        返回: (properties, values)
        """
        texts = self.ocr(0.09, 0.3, 0.40, 0.53)
        self.log_info(f'ocr values: {texts}')
        properties = [p for p in self.find_boxes(texts, match=property_pattern) if '辅音' not in p.name]
        for p in properties:
            match = property_pattern.search(p.name)
            if match:
                p.name = match.group()
        values = self.find_boxes(texts, match=number_pattern)
        self.info_set('属性', properties)
        self.info_set('值', values)
        return properties, values

    # ============================================================
    # A2 评分引擎
    # ============================================================
    @staticmethod
    def _normalize_stat(name, val_str):
        """标准化属性名: OCR识别的原始文本 → 标准属性名
        返回: (标准名, 数值)

        注意: 暴击伤害必须在暴击之前匹配（否则"暴击伤害"会被"暴击"截获）
        """
        if '暴击伤害' in name:
            pname = '暴击伤害'
        elif '暴击' in name:
            pname = '暴击'
        elif '攻击' in name:
            pname = '攻击' + ('百分比' if '%' in val_str or '％' in val_str else '')
        elif '生命' in name:
            pname = '生命' + ('百分比' if '%' in val_str or '％' in val_str else '')
        elif '防御' in name:
            pname = '防御' + ('百分比' if '%' in val_str or '％' in val_str else '')
        elif '效率' in name:
            pname = '共鸣效率'
        elif '普攻' in name:
            pname = '普攻伤害加成'
        elif '重击' in name:
            pname = '重击伤害加成'
        elif '解放' in name:
            pname = '共鸣解放伤害加成'
        elif '技能' in name:
            pname = '共鸣技能伤害加成'
        else:
            pname = name  # 未识别，保留原名

        value = parse_number(val_str)
        return pname, value

    @staticmethod
    def _pair_stats(properties, values):
        """将属性与数值按 Y 坐标最近原则配对
        返回: [(属性名, 数值文本), ...]
        """
        paired = []
        unmatched = values.copy()
        for prop in properties:
            matched_text = "0"
            if unmatched:
                closest = min(unmatched, key=lambda v: abs(prop.y - v.y))
                matched_text = closest.name
                unmatched.remove(closest)
            paired.append((prop.name, matched_text))
        return paired

    def _compute_score(self, paired_stats):
        """计算加权评分
        返回: (score, has_crit_rate, has_crit_dmg, total_count)
        """
        has_crit_rate = False
        has_crit_dmg = False
        score = 0.0
        detail = []  # 仅用于日志

        for p_raw, v_str in paired_stats:
            pname, value = self._normalize_stat(p_raw, v_str)

            if pname == '暴击':
                has_crit_rate = True
            elif pname == '暴击伤害':
                has_crit_dmg = True

            weight = self.config.get(f'权重_{pname}', 0) or 0
            if weight > 0:
                line_score = weight * value
                score += line_score
                detail.append(f'{pname}={value}×{weight}={line_score:.1f}')
            else:
                detail.append(f'{pname}={value}[权重0,跳过]')

        self.log_info(f'词条明细: {" | ".join(detail)}')
        return score, has_crit_rate, has_crit_dmg, len(paired_stats)

    def evaluate_stage(self, threshold, stage_label):
        """评分判定一个阶段: 强化+调谐 → OCR → 评分 → 判定

        返回: True=通过继续, False=不通过已弃置, None=满级已上锁
        """
        # 1. 强化并调谐 + 处理弹窗
        self.enhance_and_tune()

        # 2. OCR 读取词条
        properties, values = self.ocr_read_stats()
        if not properties:
            self.log_info(f'[{stage_label}] 未读到词条, 弃置')
            self.fail_reason = f'{stage_label}_未读到词条'
            self.trash_and_esc()
            return False

        # 3. 计算评分
        paired = self._pair_stats(properties, values)
        score, has_crit_rate, has_crit_dmg, total_count = self._compute_score(paired)

        self.info_set('当前评分', round(score, 1))
        self.info_set('词条数', total_count)
        self.log_info(f'[{stage_label}] 评分={score:.1f} 阈值={threshold} | '
                      f'暴击={has_crit_rate} 爆伤={has_crit_dmg} | {total_count}条')

        # 4. 硬性底线检查: 剩余孔位能否凑齐必须的暴击/暴击伤害
        must_crit = self.config.get('必须暴击')
        must_crit_dmg = self.config.get('必须暴击伤害')
        if must_crit or must_crit_dmg:
            missing = (1 if must_crit and not has_crit_rate else 0) + \
                      (1 if must_crit_dmg and not has_crit_dmg else 0)
            remaining = 5 - total_count
            if missing > 0 and remaining < missing:
                self.fail_reason = f'{stage_label}_硬底线_缺{missing}孔剩{remaining}'
                self.log_info(f'[{stage_label}] 剩余{remaining}孔无法凑齐硬底线(缺{missing}), 弃置')
                self.trash_and_esc()
                return False

        # 5. 评分阈值判定
        if score < threshold:
            self.fail_reason = f'{stage_label}_评分{score:.1f}<{threshold}'
            self.log_info(f'[{stage_label}] 评分 {score:.1f} < {threshold}, 弃置')
            self.trash_and_esc()
            return False

        # 6. 通过! 满级则上锁
        if total_count >= 5:
            self.lock_and_esc()
            return None

        self.log_info(f'[{stage_label}] 通过, 继续下阶段')
        return True

    # ============================================================
    # 原版方法（保留不动）
    # ============================================================
    def find_echo_enhance(self):
        return self.ocr(0.82, 0.86, 0.97, 0.96, match='培养')

    def is_0_level(self):
        return self.ocr(0.65, 0.35, 1, 0.57, match=re.compile('声骸技能'))

    def find_add_mat(self):
        return self.wait_ocr(0.09, 0.6, 0.38, 0.86, match=['阶段放入'], time_out=1)

    def find_confirm(self):
        button_box = self.box_of_screen(0.60, 0.65, 0.82, 0.82)
        if confirm := self.find_one('echo_enhance_confirm', box=button_box, threshold=0.7):
            return [confirm]
        return self.ocr(box=button_box, match='确认')

    def esc(self):
        start = time.time()
        while not self.find_echo_enhance() and time.time() - start < 10:
            self.send_key('esc', interval=4, after_sleep=0.2)
        self.sleep(0.1)

    def trash_and_esc(self):
        self.info_incr('失败声骸数量')
        start = time.time()
        success = False
        drop_status_box = get_bounding_box([
            self.get_box_by_name('echo_dropped'),
            self.get_box_by_name('echo_not_dropped'),
        ]).scale(1.05)
        while time.time() - start < 5:
            drop_status = self.find_best_match_in_box(drop_status_box,
                                                      ['echo_dropped', 'echo_not_dropped'], threshold=0.7)
            if not drop_status:
                raise Exception('无法找到声骸弃置状态!')
            if drop_status.name == 'echo_not_dropped':
                self.send_key('z', after_sleep=1)
            else:
                self.log_info('成功弃置!')
                success = True
                break
        if not success:
            raise Exception('弃置失败!')
        safe_reason = re.sub(r'[<>:"/\\|?*]', '', self.fail_reason)
        self.screenshot_echo(f'failed/{self.info_get("失败声骸数量")}_{safe_reason}')
        self.esc()
        self.log_info('不符合条件 丢弃')
        self.wait_ocr(0.82, 0.86, 0.97, 0.96, match='培养', settle_time=0.1)

    def screenshot_echo(self, name):
        echo = self.box_of_screen(0.09, 0.09, 0.37, 0.55).crop_frame(self.frame)
        self.screenshot(name=name, frame=echo)

    def lock_and_esc(self):
        self.info_incr('成功声骸数量')
        start = time.time()
        success = False
        lock_status_box = get_bounding_box([
            self.get_box_by_name('echo_locked'),
            self.get_box_by_name('echo_not_locked'),
        ]).scale(1.05)
        while time.time() - start < 5:
            drop_status = self.find_best_match_in_box(lock_status_box,
                                                      ['echo_locked', 'echo_not_locked'], threshold=0.7)
            if not drop_status:
                raise Exception('无法找到声骸上锁状态!')
            if drop_status.name == 'echo_not_locked':
                self.send_key('c', after_sleep=1)
            else:
                self.log_info('成功上锁!')
                success = True
                break
        if not success:
            raise Exception('上锁失败!')
        self.screenshot_echo(f'success/{self.info_get("成功声骸数量")}')
        self.log_info('成功并上锁')
        if self.config.get('Pause after Success'):
            self.log_info('符合条件的声骸，已暂停任务', notify=True)
            self.pause()
        self.esc()
        self.wait_ocr(0.82, 0.86, 0.97, 0.96, match='培养', settle_time=0.1)

    # ============================================================
    # 原版 check_echo_stats（保留参考，V2 不再调用）
    # 配置项已移除，此方法仅作为硬规则逻辑的参考
    # ============================================================
    def check_echo_stats(self, properties, values):
        pass  # 原版硬规则已弃用，详见 git 历史


def parse_number(text):
    try:
        return float(text.replace('％', '%').split('%')[0])
    except (ValueError, IndexError):
        return 0.0
