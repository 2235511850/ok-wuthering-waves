# Tacet Suppression (无音区) name list, ordered by F2 book grouping.
# structure = [len(group) for group in TACET_GROUPS]  -> [2, 5, 5, 7]
# names (flat) = [name for group in TACET_GROUPS for name in group]  -> 19 items

TACET_GROUPS = [
    # Group 1 — 瑝珑·梦州 (2)
    ['方擎西峰无音区(秧秧/景燃)', '玄幽东岳无音区(秧秧/清宵)'],
    # Group 2 — 索拉里斯之极·拉海洛 (5)
    ['落日堤屿无音区(绯雪/校长)', '冰原运输港无音区(小爱/西格莉卡)', '加拉尔冠阶无音区(小爱/达妮娅)', '隐喙深腹无音区(医生/琳奈)', '陷足流川无音区(医生/莫宁)'],
    # Group 3 — 黎那汐塔 (5)
    ['哀恸谷无音区(卡提/露帕)', '贝奥海域无音区(夏空/水母)', '黎乔利群岛无音区(赞妮/船长)', '槲生半岛无音区(柯莱塔/赞妮)', '悲叹墓岛无音区(水母/高天)'],
    # Group 4 — 瑝珑·今州 (7)
    ['中曲台地无音区(雷/火)', '荒石高地无音区I(暗/轻云)', '虎口山脉无音区(攻击/奶)', '怨鸟泽无音区(风/冰)',
     '归墟港市无音区(冰/雷)', '荒石高地无音区II(光/攻击)', '无光之森无音区(火/奶)'],
]

TACET_NAMES = [name for group in TACET_GROUPS for name in group]
