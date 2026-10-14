# Boss Challenge (强敌讨伐) and Weekly Challenge (战歌重奏) name lists,
# ordered by F2 book grouping.
# structure = [len(group) for group in BOSS_CHALLENGE_GROUPS]  -> [1, 1, 4, 7, 1, 9]
# names (flat) = [name for group in BOSS_CHALLENGE_GROUPS for name in group]  -> 23 items

BOSS_CHALLENGE_GROUPS = [
    # Group 1 — 限时提前开放 (1)
    ['天傀劫煞'],
    # Group 2 — 瑝珑·梦州 (1)
    ['万囹牢·朽躯'],
    # Group 3 — 索拉里斯之极·拉海洛 (4)
    ['梦魇亚当·重锤', '无铭探索者', '海维夏', '炉芯机骸'],
    # Group 4 — 黎那汐塔 (7)
    ['海之女', '伪作的神王', '芬莱克', '荣耀狮像', '叹息古龙', '罗蕾莱', '异构武装'],
    # Group 5 — 黑海岸 (1)
    ['无归的谬误'],
    # Group 6 — 瑝珑·今州 (9)
    ['无冠者', '朔雷之鳞', '云闪之鳞', '燎照之骑', '飞廉之猩', '哀声鸷', '无常凶鹭', '辉萤军势', '聚械机偶'],
]

WEEKLY_CHALLENGE_GROUPS = [
    # Group 1 — 瑝珑·梦州 (1)
    ['失坠困咎之庭·战歌重奏'],
    # Group 2 — 索拉里斯之极·拉海洛 (2)
    ['虚妄诞生之种·战歌重奏', '星海迷途之扉·战歌重奏'],
    # Group 3 — 黎那汐塔 (3)
    ['烬夜天启之章·战歌重奏', '命途断章之轮·战歌重奏', '彼世猩红之幕·战歌重奏'],
    # Group 4 — 瑝珑·今州 (4)
    ['时序命定之争·战歌重奏', '无冠巨像之心·战歌重奏', '无序边境之火·战歌重奏', '昔日咏叹之钟·战歌重奏'],
]

BOSS_CHALLENGE_NAMES = [name for group in BOSS_CHALLENGE_GROUPS for name in group]
WEEKLY_CHALLENGE_NAMES = [name for group in WEEKLY_CHALLENGE_GROUPS for name in group]

BOSS_CHALLENGE_STRUCTURE = [len(group) for group in BOSS_CHALLENGE_GROUPS]
WEEKLY_CHALLENGE_STRUCTURE = [len(group) for group in WEEKLY_CHALLENGE_GROUPS]

# Nightmare Challenge (梦魇祓除) — 特异梦魇 boss list.
# F2 book "梦魇祓除" tab contains 2 groups:
#   Group 1: 5 nightmare nests (梦魇聚落, handled by NightmareNestTask)
#   Group 2: 10 nightmare 4C bosses (特异梦魇, user-selectable for FarmEchoTask)
NIGHTMARE_NEST_NAMES = [
    '穗波市梦魇聚落', '三王峰梦魇聚落', '潮痕岩滩梦魇聚落',
    '受蚀地梦魇聚落', '千殁沉岛梦魇聚落',
]

NIGHTMARE_CHALLENGE_NAMES = [
    '梦魇·赫卡忒', '梦魇·凯尔匹', '梦魇·辉萤军势', '梦魇·哀声鸷', '梦魇·燎照之骑',
    '梦魇·无冠者', '梦魇·朔雷之鳞', '梦魇·云闪之鳞', '梦魇·无常凶鹭', '梦魇·飞廉之猩',
]

NIGHTMARE_CHALLENGE_GROUPS = [NIGHTMARE_NEST_NAMES, NIGHTMARE_CHALLENGE_NAMES]
NIGHTMARE_CHALLENGE_STRUCTURE = [len(group) for group in NIGHTMARE_CHALLENGE_GROUPS]  # [5, 10]
NIGHTMARE_CHALLENGE_TOTAL = sum(NIGHTMARE_CHALLENGE_STRUCTURE)  # 15
NIGHTMARE_NEST_COUNT = len(NIGHTMARE_NEST_NAMES)  # 5
