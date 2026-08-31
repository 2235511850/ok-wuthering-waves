# weight_presets.py
# ============================================================
# 评分权重预设管理
# 存储结构: JSON 文件, 运行时可增删改
# 预设方案分两类: 通用类型 / 角色类型
# ============================================================
import json
import os
import threading
from ok import Logger

logger = Logger.get_logger(__name__)

# 所有可评分的副词条属性（小攻击/小生命/小防御固定值在评分时折算为对应百分比）
WEIGHT_STATS = [
    '暴击', '暴击伤害',
    '攻击百分比', '生命百分比', '防御百分比',
    '共鸣效率',
    '共鸣技能伤害加成', '共鸣解放伤害加成',
    '普攻伤害加成', '重击伤害加成',
]

# 预设文件路径
PRESETS_DIR = os.path.join('config')
PRESETS_FILE = os.path.join(PRESETS_DIR, 'weight_presets.json')

# 内置默认方案（首次运行自动生成）
BUILTIN_PRESETS = {
    # --- 通用类型 ---
    '共解C': {
        'type': '通用',
        'weights': {
            '暴击': 1.8, '暴击伤害': 0.9,
            '攻击百分比': 1.0, '生命百分比': 0.2, '防御百分比': 0.2,
            '共鸣效率': 0.3,
            '共鸣技能伤害加成': 0.8, '共鸣解放伤害加成': 0.8,
            '普攻伤害加成': 0.6, '重击伤害加成': 0.6,
        },
    },
    '辅助': {
        'type': '通用',
        'weights': {
            '暴击': 0.3, '暴击伤害': 0.2,
            '攻击百分比': 0.3, '生命百分比': 1.0, '防御百分比': 0.5,
            '共鸣效率': 1.2,
            '共鸣技能伤害加成': 0.3, '共鸣解放伤害加成': 0.3,
            '普攻伤害加成': 0.2, '重击伤害加成': 0.2,
        },
    },
    '肉盾': {
        'type': '通用',
        'weights': {
            '暴击': 0.2, '暴击伤害': 0.1,
            '攻击百分比': 0.2, '生命百分比': 1.5, '防御百分比': 1.5,
            '共鸣效率': 0.8,
            '共鸣技能伤害加成': 0.2, '共鸣解放伤害加成': 0.2,
            '普攻伤害加成': 0.1, '重击伤害加成': 0.1,
        },
    },
}

_lock = threading.RLock()


def _ensure_dir():
    os.makedirs(PRESETS_DIR, exist_ok=True)


def load_presets():
    """读取所有预设方案, 返回 dict: {方案名: {type, weights}}"""
    with _lock:
        if not os.path.exists(PRESETS_FILE):
            _ensure_dir()
            save_presets(BUILTIN_PRESETS)
            return BUILTIN_PRESETS.copy()
        try:
            with open(PRESETS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"读取权重预设文件失败: {e}, 返回内置默认")
            return BUILTIN_PRESETS.copy()


def save_presets(presets):
    """保存全部预设方案到文件"""
    with _lock:
        _ensure_dir()
        with open(PRESETS_FILE, 'w', encoding='utf-8') as f:
            json.dump(presets, f, ensure_ascii=False, indent=2)


def add_preset(name, preset_type, weights):
    """新增方案, 返回是否成功"""
    presets = load_presets()
    if name in presets:
        return False, f'方案[{name}]已存在'
    presets[name] = {'type': preset_type, 'weights': weights}
    save_presets(presets)
    return True, None


def update_preset(name, weights):
    """修改方案权重, 返回是否成功"""
    presets = load_presets()
    if name not in presets:
        return False, f'方案[{name}]不存在'
    presets[name]['weights'] = weights
    save_presets(presets)
    return True, None


def delete_preset(name):
    """删除方案, 返回是否成功"""
    presets = load_presets()
    if name not in presets:
        return False, f'方案[{name}]不存在'
    del presets[name]
    save_presets(presets)
    return True, None


def get_preset_names(preset_type=None):
    """获取方案名列表, 可按类型过滤"""
    presets = load_presets()
    if preset_type:
        return [name for name, info in presets.items() if info.get('type') == preset_type]
    return list(presets.keys())


def get_weights(name):
    """获取指定方案的权重, 返回 dict 或 None"""
    presets = load_presets()
    info = presets.get(name)
    if info is None:
        return None
    return info.get('weights')


def reset_to_builtin():
    """重置为内置默认方案"""
    save_presets(BUILTIN_PRESETS)


# 各副词条满值（与 EnhanceEchoV2Task.STAT_RANGES 对齐）
STAT_MAX = {
    '暴击': 10.5, '暴击伤害': 21.0,
    '攻击百分比': 11.6, '生命百分比': 11.6, '防御百分比': 14.7,
    '共鸣效率': 12.4,
    '共鸣技能伤害加成': 11.6, '共鸣解放伤害加成': 11.6,
    '普攻伤害加成': 11.6, '重击伤害加成': 11.6,
}


def compute_max_score(weights):
    """计算5条满值副词条的理论满分（归一化: 满值得分=权重本身）
    取权重最高的5个词条求和
    """
    scored = [(w, stat) for stat, w in weights.items() if w > 0]
    scored.sort(key=lambda x: x[0], reverse=True)
    top5 = scored[:5]
    return sum(w for w, _ in top5)

