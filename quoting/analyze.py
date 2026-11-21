"""批量分析：把安置、竞争与评估串成一份团期结果。"""
from __future__ import annotations

from .allocate import competition, honor_accepted
from .assess import assess_family
from .plan import enumerate_plan
from .service import build_service_view


def analyze(view):
    """返回 (honored, remaining, relief, manual, plans, competition_info, assessments)。"""
    honored, remaining, relief, manual = honor_accepted(view)
    honored_by_family = {h.quote.family: h for h in honored.values()}
    plans, competition_plans = {}, {}
    for family in view.families:
        if family.family in honored_by_family:
            continue
        plan = enumerate_plan(view, family)
        plans[family.family] = plan
        competition_plans[family.family] = plan
    competition_info = competition(view, competition_plans, remaining)
    assessments = {}
    for family in view.families:
        if family.family in honored_by_family:
            assessments[family.family] = assess_family(view, family, None, remaining, {}, honored_by_family[family.family], [])
        else:
            open_quotes = [q for q in view.quotes_of(family.family) if not q.accepted]
            assessments[family.family] = assess_family(
                view, family, plans[family.family], remaining, competition_info, None, open_quotes
            )
    return honored, remaining, relief, manual, plans, competition_info, assessments


def service_views(view):
    """逐家庭的客服查询视图。"""
    honored, remaining, _, _, _, _, assessments = analyze(view)
    honored_by_family = {h.quote.family: h for h in honored.values()}
    views = {}
    for family in view.families:
        open_quotes = [q for q in view.quotes_of(family.family) if not q.accepted]
        views[family.family] = build_service_view(
            view, family, assessments[family.family], honored_by_family.get(family.family), open_quotes, remaining
        )
    return views


def naive_calendar_sum(view, family):
    """日历页低价合计：只看每站人数适用的最低有效报价，不核时段、库存与可订性。

    仅作对照诊断，不可兑现，不能当作预计支出。
    """
    total = 0
    stations = {slot.station for slot in view.slots}
    for station in stations:
        offers = [
            o
            for o in view.offers
            if view.slot(o.slot).station == station and o.fits_party(family) and o.valid_at(view.seq)
        ]
        if not offers:
            return None
        total += min(o.price for o in offers)
    return total
