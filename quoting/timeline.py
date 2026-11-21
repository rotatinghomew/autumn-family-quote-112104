"""时段与接驳核对：家庭时间窗、可接受改时分钟与站间通行。

家庭的 flexible_time 是总共可动用的改时分钟，同时覆盖：
行程早于窗口开始、晚于窗口结束、以及站间通行不足的分钟数。
三项缺口合计不超过 flexible_time 才视为时段可行。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Timing:
    window_shortfall: int
    transfer_shortfall: int

    @property
    def needed_flex(self):
        return self.window_shortfall + self.transfer_shortfall

    def feasible_for(self, family):
        return self.needed_flex <= family.flexible_time


def check_timing(family, ordered_slots):
    """ordered_slots 必须互不重叠且按开始时刻排序。"""
    first, last = ordered_slots[0], ordered_slots[-1]
    window = max(0, family.start - first.start) + max(0, last.end - family.end)
    transfer = 0
    for current, nxt in zip(ordered_slots, ordered_slots[1:]):
        gap = nxt.start - current.end
        transfer += max(0, current.travel_to_next_min - gap)
    return Timing(window, transfer)
