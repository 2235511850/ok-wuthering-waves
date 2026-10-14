# BookTargetMixin.py
# ============================================================
# 二开模块：F2 手册列表点击增强（从 BaseWWTask.click_on_book_target 分离）
#
# 相比上游版本的增强：
#   1. 无 structure 时按比例滚动兜底（上游只支持有 structure 的场景）
#   2. adaptive retry：滚动不足时闭环修正（max_y < 0.73 补滚一次）
#   3. fallback 校准滚动：可见行数不足时按 header 校准再滚
#   4. story 剧情确认弹窗处理：确认后直接进本，返回 'story' 让调用方跳过组队挑战
#   5. 全程调试日志
#
# 使用方式：V2 任务类多继承本 Mixin 即可覆盖上游实现，上游 BaseWWTask 保持原样。
# ============================================================


class BookTargetMixin:

    def click_on_book_target(self, serial_number: int, total_number: int, structure: list[int] = None):
        def get_cross_count(structure, sn):
            current_sum = 0
            cross_count = 0
            for s in structure:
                current_sum += s
                if sn > current_sum:
                    cross_count += 1
                else:
                    break
            return cross_count

        self.sleep(0.5)
        bar_bottom = 0.8806
        bar_x = 0.9730
        header_h = 0.028  # calibrated header height (~40px @1440), replaces separator=0.01
        cross_count = 0
        container_max_rows = 4
        target_index = -1

        bar_top = self._find_book_scroll_top()
        self.log_info(f'click_on_book_target: serial_number={serial_number}, total_number={total_number}, '
                      f'structure={structure}, bar_top={bar_top}, bar_bottom={bar_bottom}')

        if serial_number <= container_max_rows:
            target_index = serial_number - 1
            self.log_info(
                f'click_on_book_target: serial_number <= {container_max_rows}, target_index={target_index} (no scroll needed)')
        else:
            calib_cross = get_cross_count(structure, serial_number) if structure else 0
            calib_container_h = (bar_bottom - bar_top - (len(structure) - 1) * header_h) if structure else (
                        bar_bottom - bar_top)
            calib_item_h = calib_container_h / total_number if total_number else 0
            calib_y = min(bar_top + calib_item_h * serial_number + calib_cross * header_h, bar_bottom) if structure else \
                min(bar_top + (bar_bottom - bar_top) / total_number * serial_number, bar_bottom) if total_number else bar_bottom
            to_click_y = calib_y
            item_h = calib_item_h
            self.log_info(
                f'click_on_book_target: scrolling to calib_y={calib_y:.4f}, item_h={item_h:.4f}, cross_count={calib_cross}')
            self.click(bar_x, to_click_y, after_sleep=1)
        btns = self.find_feature('boss_proceed', box=self.box_of_screen(0.9113, 0.229, 0.9613, 0.861), threshold=0.8)
        self.log_info(f'click_on_book_target: found {len(btns) if btns else 0} boss_proceed buttons')
        if btns:
            for i, b in enumerate(btns):
                self.log_info(f'  boss_proceed[{i}]: x={b.x}, y={b.y}, w={b.width}, h={b.height}, conf={b.confidence}')
        # adaptive retry: closed-loop correction for residual underscroll (found 3/4 with low max_y)
        if not target_index > -1 and btns and len(btns) in (3, 4) and structure and serial_number > container_max_rows:
            max_y = max(b.y / self.height for b in btns)
            if max_y < 0.73:
                retry_y = min(to_click_y + item_h * 0.55, bar_bottom) if 'item_h' in locals() and item_h else min(
                    to_click_y + 0.018, bar_bottom)
                self.log_info(f'click_on_book_target: adaptive retry, max_y={max_y:.4f} < 0.73, retry_y={retry_y:.4f}')
                self.click(bar_x, retry_y, after_sleep=1)
                btns = self.find_feature('boss_proceed', box=self.box_of_screen(0.9113, 0.229, 0.9613, 0.861),
                                         threshold=0.8)
                self.log_info(
                    f'click_on_book_target: after retry found {len(btns) if btns else 0} boss_proceed buttons')
        if not btns:
            raise Exception("can't find boss_proceed")
        if target_index > -1:
            if target_index < len(btns):
                target = btns[target_index]
                self.log_info(f'click_on_book_target: using target_index={target_index}, target={target}')
            else:
                # Fallback: not enough visible rows, scroll with calibrated header
                calib_cross2 = get_cross_count(structure, serial_number) if structure else 0
                calib_h2 = (bar_bottom - bar_top - (len(structure) - 1) * header_h) if structure else (
                            bar_bottom - bar_top)
                calib_y2 = min(bar_top + (calib_h2 / total_number) * serial_number + calib_cross2 * header_h,
                               bar_bottom) if total_number else bar_bottom
                self.log_info(
                    f'click_on_book_target: fallback scroll, target_index={target_index} >= len(btns)={len(btns)}, calib_y2={calib_y2:.4f}')
                self.click(bar_x, calib_y2, after_sleep=1)
                btns = self.find_feature('boss_proceed', box=self.box_of_screen(0.9113, 0.229, 0.9613, 0.861),
                                         threshold=0.8)
                if not btns:
                    raise Exception("can't find boss_proceed after scroll")
                target = max(btns, key=lambda box: box.y)
                self.log_info(f'click_on_book_target: fallback selected bottom-most target={target}')
        else:
            target = max(btns, key=lambda box: box.y)
            self.log_info(f'click_on_book_target: serial > 4, selected bottom-most target={target}')
        self.draw_boxes(boxes=target, color="red")
        self.log_info(
            f'click_on_book_target: clicking target at ({target.x + target.width / 2:.0f}, {target.y + target.height / 2:.0f})')
        self.click(target, after_sleep=1)
        self.log_info(f'click_on_book_target: clicked boss_proceed, checking for story confirmation dialog...')
        # Handle story confirmation dialog that may appear for some bosses
        # ("提前到达目标位置可能影响剧情体验，是否确认前往？")
        # After confirming this dialog, the game loads directly into the boss realm
        # (skipping the team challenge interface), so we wait for world load and
        # return 'story' to let the caller skip click_team_challenge.
        if confirm := self.wait_feature(
                ['confirm_btn_hcenter_vcenter', 'confirm_btn_highlight_hcenter_vcenter'],
                raise_if_not_found=False,
                threshold=0.6,
                time_out=2):
            self.log_info(f'click_on_book_target: found story confirmation dialog, clicking confirm')
            self.click(confirm, after_sleep=1)
            self.log_info(f'click_on_book_target: confirmed dialog, waiting for realm load...')
            self.wait_in_team_and_world(time_out=120)
            self.log_info(f'click_on_book_target: realm loaded after story dialog')
            return 'story'  # directly entered boss realm, skip team challenge
        self.log_info(f'click_on_book_target: no story dialog, waiting for teleport/team_close feature...')
        feature = self.wait_feature(['fast_travel_custom', 'gray_teleport', 'remove_custom', 'team_close'],
                                    time_out=10,
                                    settle_time=0.5, raise_if_not_found=True)
        self.log_info(f'click_on_book_target: wait_feature returned {feature.name if feature else None}')
        return feature.name == 'team_close'
