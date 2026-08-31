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
from src.weight_presets import get_preset_names, get_weights

def _get_preset_options():
    """获取预设方案名列表，用于下拉选项"""
    try:
        names = get_preset_names()
        return names if names else ['共解C']
    except Exception:
        return ['共解C']


def _get_preset_weights(name):
    """获取指定方案的权重字典"""
    try:
        w = get_weights(name)
        return w if w else {}
    except Exception:
        return {}

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
    # UI 坐标（基于 1920x1080 截图校准）
    # 格式: (x1, y1, x2, y2) 屏幕归一化坐标 0-1
    # ============================================================
    UI_COORDS = {
        '加号按钮':       (0.125, 0.711, 0.149, 0.776),   # 左侧材料槽第一个+（模板拾取 239,768,47x70）
        '金色密音筒':     (0.538, 0.075, 0.606, 0.187),   # 右侧列表第一行第一个金色材料（模板拾取 1033,81,130x121）
        '设置按钮':       (0.322, 0.627, 0.344, 0.668),   # 齿轮设置按钮（模板功能拾取 618,677,42x44）
        '确认按钮':       (0.731, 0.819, 0.866, 0.858),   # 设置弹窗确认按钮（模板拾取 1404,884,260x42）
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "⬆️ 批量强化声骸V2(二开)"
        self.description = "点击B进入背包, 在过滤器中选择需要强化的声骸, 并按照等级从0排序后开始."
        self.fail_reason = ""
        self.supported_languages = ["zh_CN", "zh_TW"]

        # 激进模式: 快捷放入设置只需执行一次（设置会持久化）
        self._quick_add_configured = False
        # 保守/标准模式: 阶段放入设置只需执行一次（设置会持久化）
        self._stage_add_configured = False

        # ============================================================
        # A3 GUI 配置项
        # ============================================================
        self.default_config.update({
            # --- 筛选模式 ---
            '筛选模式': '保守',

            # --- 硬性底线（独立开关） ---
            '必须暴击': True,
            '必须暴击伤害': True,

            # --- 评分系统（归一化评分：满分=权重最高的5条满值词条得分之和，共解C满分≈5.3） ---
            '启用评分': True,
            '15级评分阈值': 2.1,
            '20级评分阈值': 2.9,
            '25级评分阈值': 3.7,

            # --- 有效词条系统 ---
            '启用有效词条检查': True,
            '有效词条': ['暴击', '暴击伤害', '攻击百分比'],
            '15级有效词条数': 1,
            '20级有效词条数': 2,
            '25级有效词条数': 3,

            # --- 其他 ---
            '评分权重方案': '共解C',
            'Pause after Success': True,
        })

        # 筛选模式：下拉单选
        self.config_type['筛选模式'] = {
            'options': ['保守', '标准', '激进'],
        }
        # 评分权重方案：下拉单选（动态读取预设列表）
        self.config_type['评分权重方案'] = {
            'options': _get_preset_options(),
        }
        # 启用评分: 开关控制评分阈值显隐
        self.config_type['启用评分'] = {
            'sub_configs': {True: ['15级评分阈值', '20级评分阈值', '25级评分阈值', '评分权重方案']}
        }
        # 启用有效词条检查: 开关控制有效词条相关项显隐
        self.config_type['启用有效词条检查'] = {
            'sub_configs': {True: ['有效词条', '15级有效词条数', '20级有效词条数', '25级有效词条数']}
        }
        # 有效词条：多选
        self.config_type['有效词条'] = {
            'options': ALL_STAT_NAMES,
        }

        self.config_description = {
            '筛选模式': '保守=0→15→20→25三级止损（最省材料）; 标准=0→20→25两级止损; 激进=0→25快速放入一步到位（最费材料）',
            '必须暴击': '开启后声骅最终必须拥有暴击词条，剩余孔位不足以凑齐则提前弃置',
            '必须暴击伤害': '开启后声骅最终必须拥有暴击伤害词条，剩余孔位不足以凑齐则提前弃置',
            '启用评分': '开启后按评分阈值筛选，关闭则只看有效词条',
            '15级评分阈值': '15级（3条词条）时归一化评分下限（满分≈理论满分×词条比，共解C满分5.3），低于此值弃置',
            '20级评分阈值': '20级（4条词条）时归一化评分下限',
            '25级评分阈值': '25级（5条满级）时最终归一化评分下限',
            '启用有效词条检查': '开启后按有效词条数量筛选，关闭则只看评分',
            '有效词条': '选择哪些副词条算作有效词条，用于有效词条数判定',
            '15级有效词条数': '15级时至少需要几条有效词条，不足则弃置',
            '20级有效词条数': '20级时至少需要几条有效词条',
            '25级有效词条数': '25级时至少需要几条有效词条',
            'Pause after Success': '成功时发送通知并暂停任务',
            '评分权重方案': '选择评分权重预设方案（在左侧导航栏「评分权重预设」模块中管理方案）',
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

            # --- 等待强化界面加载完毕 ---
            self.log_info('等待强化界面加载...')
            if not self.wait_ocr(0.10, 0.55, 0.35, 0.70,
                                 match=['快捷放入', '阶段放入', re.compile('强化消耗材料')],
                                 settle_time=0.5, time_out=10):
                raise Exception('强化界面加载超时, 找不到快捷放入/阶段放入/强化消耗材料!')
            self.log_info('强化界面已加载')

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
        # 首次进入: 配置阶段放入方式（只执行一次）
        self.ensure_stage_add_configured()
        # 阶段1: 自定义放8个金色密音筒 → 升15
        self.add_custom_materials(8)
        r = self.evaluate_stage(self.config.get('15级评分阈值'), '15级')
        if r is not True:
            return  # False=已弃置, None=已上锁(不会在15级发生)

        # 阶段2: 阶段放入 → 升20
        self.stage_add_materials()
        r = self.evaluate_stage(self.config.get('20级评分阈值'), '20级')
        if r is not True:
            return

        # 阶段3: 阶段放入 → 升25
        self.stage_add_materials()
        self.evaluate_stage(self.config.get('25级评分阈值'), '25级')

    def _flow_standard(self):
        """标准模式: 0→20评 → 阶段放入升25评"""
        # 首次进入: 阶段放入方式只配置一次
        self.ensure_stage_add_configured()
        # 阶段1: 自定义放16个金色密音筒 → 升20
        self.add_custom_materials(16)
        r = self.evaluate_stage(self.config.get('20级评分阈值'), '20级')
        if r is not True:
            return

        # 阶段2: 阶段放入 → 升25
        self.stage_add_materials()
        self.evaluate_stage(self.config.get('25级评分阈值'), '25级')

    def _flow_aggressive(self):
        """激进模式: 快速放入 → 直升25 → 评"""
        self.quick_add_materials()
        self.evaluate_stage(self.config.get('25级评分阈值'), '25级')

    # ============================================================
    # 材料放入方法（坐标基于 1920x1080 截图校准）
    # ============================================================
    def _click_placeholder(self, name, after_sleep=0.3):
        """点击校准坐标对应的UI元素"""
        x1, y1, x2, y2 = self.UI_COORDS[name]
        box = self.box_of_screen(x1, y1, x2, y2)
        # 调试: 打印归一化坐标和像素坐标
        cx = (x1 + x2) / 2
        cy = (y1 + y2) / 2
        px = int(cx * 1920)
        py = int(cy * 1080)
        self.log_info(f'点击 [{name}] 归一化=({x1:.3f},{y1:.3f},{x2:.3f},{y2:.3f}) '
                      f'中心=({cx:.3f},{cy:.3f}) 像素=({px},{py}) '
                      f'box=({box.x},{box.y},{box.width},{box.height})')
        self.screenshot(f'click_{name}')
        self.click(box, after_sleep=after_sleep)

    def add_custom_materials(self, count):
        """自定义添加材料: 点加号 → 右侧材料列表选金色密音筒×count → ESC返回

        基于截图校准: 点+号后右侧材料列表显示，第一行第一个是金色经验材料
        注意: 点加号后必须等弹窗加载完成再开始点材料, 否则点击落空少次数
        """
        self.log_info(f'自定义添加金色密音筒 ×{count}')
        # 点加号打开材料选择
        self._click_placeholder('加号按钮', after_sleep=0.5)
        # 等材料列表弹窗加载完成（避免点太快落空）
        self.log_info('等待材料列表加载...')
        self.sleep(1.0)
        # 在右侧材料列表中选金色密音筒
        for i in range(count):
            self._click_placeholder('金色密音筒', after_sleep=0.3)
        # 按 ESC 返回强化界面
        self.send_key('esc', after_sleep=0.5)
        self.log_info('已返回强化界面')

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

    def ensure_stage_add_configured(self):
        """确保阶段放入设置已初始化（只执行一次，设置会持久化）

        首次调用: 点齿轮设置 → 弹窗 OCR选"阶段放入" → OCR点"确认"
        后续调用: 设置已持久化, 直接跳过
        """
        if not self._stage_add_configured:
            self.log_info('首次执行, 配置阶段放入设置...')
            self._configure_add_mode('阶段放入')
            self._stage_add_configured = True
        else:
            self.log_info('阶段放入已配置, 跳过设置步骤')

    def _configure_add_mode(self, add_mode):
        """打开设置弹窗, 选择放入方式并确认（一次性设置）"""
        self._click_placeholder('设置按钮', after_sleep=0.5)
        # OCR 选择放入方式: 弹窗内选项并排, 快捷放入在左, 阶段放入在右（模板拾取）
        add_mode_area = {
            '快捷放入': (0.123, 0.253, 0.493, 0.404),   # 模板拾取 237,273,710x164
            '阶段放入': (0.515, 0.256, 0.883, 0.402),   # 模板拾取 989,276,706x158
        }.get(add_mode, (0.123, 0.253, 0.883, 0.402))   # 兜底: 全宽搜索
        if not self.wait_click_ocr(*add_mode_area, match=[add_mode],
                                   settle_time=0.1, after_sleep=0.3):
            self.log_error(f'设置弹窗中找不到[{add_mode}]选项!')
            raise Exception(f'设置弹窗中找不到[{add_mode}]选项!')
        self.log_info(f'选择[{add_mode}]模式')
        # OCR 点击确认按钮（模板拾取 1404,884,260x42）
        if not self.wait_click_ocr(0.70, 0.80, 0.90, 0.88, match=['确认'],
                                   settle_time=0.1, after_sleep=0.5):
            self.log_info('OCR找不到确认按钮, 尝试硬坐标兜底')
            self._click_placeholder('确认按钮', after_sleep=0.5)
        self.log_info('确认设置')

    def quick_add_materials(self):
        """快速放入材料（激进模式: 0→25一步到位）

        首次调用: 配置快捷放入设置（只执行一次） → 点击"快捷放入"按钮
        后续调用: 设置已持久化, 直接点"快捷放入"按钮
        """
        self.log_info('快速放入材料(0→25)...')
        if not self._quick_add_configured:
            # 首次: 打开设置弹窗配置快捷放入
            self.log_info('首次执行, 配置快捷放入设置...')
            self._configure_add_mode('快捷放入')
            self._quick_add_configured = True
        else:
            self.log_info('快捷放入已配置, 跳过设置步骤')
        # 通用: 点击快捷放入按钮（首次配置后 / 后续直接点）
        self.find_and_click_quick_add()

    def find_and_click_quick_add(self):
        """查找并点击"快捷放入"按钮

        OCR 搜索左下区域，匹配"快捷放入"文字
        """
        if not self.wait_click_ocr(0.240, 0.632, 0.308, 0.665, match=['快捷放入'],
                                   settle_time=0.1, after_sleep=0.5):
            self.log_error('找不到快捷放入按钮!')
            raise Exception('找不到快捷放入按钮!')
        self.log_info('点击快捷放入')

    # ============================================================
    # 强化+调谐 + OCR 读取（从原版提取复用）
    # ============================================================
    def enhance_and_tune(self):
        """点击强化并调谐, 处理调谐弹窗"""
        if not self.wait_click_ocr(0.122, 0.891, 0.329, 0.941, match=['强化并调谐'],
                                   settle_time=0.1, after_sleep=1.5):
            if self.ocr(0.122, 0.891, 0.329, 0.941, match=['强化']):
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
        """计算归一化评分: score = Σ(weight × value / max_value)
        权重直接等于1条满值词条的得分，阈值含义清晰

        返回: (score, has_crit_rate, has_crit_dmg, total_count)
        """
        has_crit_rate = False
        has_crit_dmg = False
        score = 0.0
        detail = []  # 仅用于日志

        # 从预设方案读取权重
        preset_name = self.config.get('评分权重方案', '共解C')
        weights = _get_preset_weights(preset_name)
        if not weights:
            self.log_info(f'方案[{preset_name}]无权重数据, 使用空权重')

        for p_raw, v_str in paired_stats:
            pname, value = self._normalize_stat(p_raw, v_str)

            if pname == '暴击':
                has_crit_rate = True
            elif pname == '暴击伤害':
                has_crit_dmg = True

            # 小攻击/小生命 固定值词条: 折算为等效百分比后使用对应百分比权重
            if pname == '攻击':
                value = value * 0.5 / STAT_RANGES['攻击'][1] * STAT_RANGES['攻击百分比'][1]
                pname = '攻击百分比'
            elif pname == '生命':
                value = value * 0.33 / STAT_RANGES['生命'][1] * STAT_RANGES['生命百分比'][1]
                pname = '生命百分比'
            elif pname == '防御':
                value = value * 0.5 / STAT_RANGES['防御'][1] * STAT_RANGES['防御百分比'][1]
                pname = '防御百分比'

            weight = weights.get(pname, 0) or 0
            # 归一化: 满值词条得分 = weight, 半值词条得分 = weight × 0.5
            max_val = STAT_RANGES.get(pname, (0, 1))[1]
            if weight > 0 and max_val > 0:
                norm_value = value / max_val
                line_score = weight * norm_value
                score += line_score
                detail.append(f'{pname}={value:.1f}/{max_val}={norm_value:.2f}×{weight}={line_score:.2f}')
            elif weight > 0:
                detail.append(f'{pname}={value:.1f}[满值未知,跳过]')
            else:
                detail.append(f'{pname}={value:.1f}[权重0,跳过]')

        # # ===== 旧版细化评分（原始值 × 权重，已废弃） =====
        # for p_raw, v_str in paired_stats:
        #     pname, value = self._normalize_stat(p_raw, v_str)
        #     if pname == '暴击': has_crit_rate = True
        #     elif pname == '暴击伤害': has_crit_dmg = True
        #     if pname == '攻击':
        #         value = value * 0.5 / STAT_RANGES['攻击'][1] * STAT_RANGES['攻击百分比'][1]
        #         pname = '攻击百分比'
        #     elif pname == '生命':
        #         value = value * 0.33 / STAT_RANGES['生命'][1] * STAT_RANGES['生命百分比'][1]
        #         pname = '生命百分比'
        #     elif pname == '防御':
        #         value = value * 0.5 / STAT_RANGES['防御'][1] * STAT_RANGES['防御百分比'][1]
        #         pname = '防御百分比'
        #     weight = weights.get(pname, 0) or 0
        #     if weight > 0:
        #         line_score = weight * value
        #         score += line_score
        #         detail.append(f'{pname}={value:.1f}×{weight}={line_score:.1f}')
        #     else:
        #         detail.append(f'{pname}={value:.1f}[权重0,跳过]')
        # # ===== 旧版结束 =====

        self.log_info(f'方案[{preset_name}] 词条明细: {" | ".join(detail)}')
        return score, has_crit_rate, has_crit_dmg, len(paired_stats)

    def evaluate_stage(self, threshold, stage_label):
        """评分判定一个阶段: 强化+调谐 → OCR → 有效词条检查 → 评分 → 判定

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

        # 5. 有效词条检查
        valid_stats = self.config.get('有效词条', [])
        valid_count = 0
        valid_names = []
        for p_raw, v_str in paired:
            pname, _ = self._normalize_stat(p_raw, v_str)
            if pname in valid_stats:
                valid_count += 1
                valid_names.append(pname)

        valid_threshold = self.config.get(f'{stage_label}有效词条数', 0)
        enable_valid = self.config.get('启用有效词条检查')
        if enable_valid and valid_count < valid_threshold:
            self.fail_reason = f'{stage_label}_有效词条{valid_count}<{valid_threshold}'
            self.log_info(f'[{stage_label}] 有效词条 {valid_count}({",".join(valid_names)}) < {valid_threshold}, 弃置')
            self.trash_and_esc()
            return False

        # 6. 评分阈值判定
        enable_score = self.config.get('启用评分')
        if enable_score:
            self.log_info(f'[{stage_label}] 评分={score:.1f} 阈值={threshold} | '
                          f'有效词条={valid_count}/{valid_threshold} | {total_count}条')
            if score < threshold:
                self.fail_reason = f'{stage_label}_评分{score:.1f}<{threshold}'
                self.log_info(f'[{stage_label}] 评分 {score:.1f} < {threshold}, 弃置')
                self.trash_and_esc()
                return False
        else:
            self.log_info(f'[{stage_label}] 评分已关闭 | 有效词条={valid_count}/{valid_threshold} | {total_count}条')

        # 7. 通过! 满级则上锁
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
