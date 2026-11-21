"""库存的联合安置：已受理保证优先，同批需求竞争在后。

联合安置把每个家庭安置到一个组合且场次用量不超库存；家庭按候选数升序
（最受限的优先）尝试，搜索是完备的——只要整体存在可行安置就不会因为
逐单改换让灵活家庭先占走唯一可用的场次。同一家庭的多个备选只算一份需求，
接受保价前的多个备选不会同时扣掉多个名额。
"""
from __future__ import annotations

from dataclasses import dataclass

from .plan import resolve_option


@dataclass(frozen=True)
class Placement:
    combo: object
    compensation: int  # 运营承担的补差
    changed: bool  # 是否偏离了原锁定


def enumerate_assignments(candidates, inventory, cap=2000):
    """返回安置家庭数最多的全部联合安置方案。

    candidates: {键: [Placement, ...]}；inventory: {场次: 可用数}。
    """
    keys = sorted(candidates, key=lambda k: (len(candidates[k]), str(k)))
    best = []

    def search(index, used, chosen):
        if index == len(keys):
            if not best or len(chosen) > len(best[0]):
                best.clear()
                best.append(dict(chosen))
            elif len(chosen) == len(best[0]) and len(best) < cap:
                best.append(dict(chosen))
            return
        if best and len(chosen) + len(keys) - index < len(best[0]):
            return
        key = keys[index]
        for placement in candidates[key]:
            slots = placement.combo.slots
            if all(used.get(s, 0) < inventory.get(s, 0) for s in slots):
                for s in slots:
                    used[s] = used.get(s, 0) + 1
                chosen[key] = placement
                search(index + 1, used, chosen)
                del chosen[key]
                for s in slots:
                    used[s] -= 1
        search(index + 1, used, chosen)

    search(0, {}, {})
    return best


@dataclass
class HonoredQuote:
    quote: object
    placement: Placement | None
    notes: list

    @property
    def family_pays(self):
        if self.placement is None:
            return None
        return min(self.quote.promised, self.placement.combo.total)


def honor_accepted(view):
    """已受理保价优先占用库存与补差预算。

    库存被撤回或报价过期时，在家庭明确接受范围（已受理报价的各备选）内
    联合改派；改派后实付超出承诺的部分由运营承担，计入本轮补差预算。
    返回 (honored, remaining, relief, manual)。
    """
    candidates = {}
    prepared = {}
    manual = []
    for quote in view.accepted_quotes():
        family = view.family(quote.family)
        placements, notes, seen = [], [], set()
        ordered_options = []
        if quote.locked:
            ordered_options.append(quote.locked)
        ordered_options.extend(option for option in quote.options if tuple(option) != tuple(quote.locked or ()))
        locked_offers = set(quote.locked or ())
        for option in ordered_options:
            combo, problems = resolve_option(view, family, option)
            if combo is None:
                if tuple(option) == tuple(quote.locked or ()):
                    notes.append("原锁定组合无法兑现：" + "；".join(p.detail for p in problems))
                continue
            if combo.offers in seen:
                continue
            seen.add(combo.offers)
            changed = set(combo.offers) != locked_offers
            compensation = max(0, combo.total - quote.promised)
            placements.append(Placement(combo, compensation, changed))
        if not placements:
            manual.append({"报价": quote.quote, "家庭": quote.family, "原因": "接受范围内没有仍可兑现的组合，需人工救济"})
            continue
        candidates[quote.quote] = placements
        prepared[quote.quote] = (quote, notes)
    inventory = {slot: state.confirmed for slot, state in view.inventory.items()}
    assignments = enumerate_assignments(candidates, inventory)
    complete = [a for a in assignments if len(a) == len(candidates)]
    pool = complete if complete else assignments
    chosen = min(pool, key=lambda a: (sum(p.compensation for p in a.values()), sum(p.changed for p in a.values()))) if pool else {}
    honored, used = {}, {}
    for quote_id, (quote, notes) in prepared.items():
        placement = chosen.get(quote_id)
        if placement is None:
            manual.append({"报价": quote_id, "家庭": quote.family, "原因": "联合安置后仍无库存，需人工救济"})
            continue
        for slot in placement.combo.slots:
            used[slot] = used.get(slot, 0) + 1
        note_list = list(notes)
        if placement.changed:
            note_list.append("已按家庭接受范围改派为 " + "、".join(placement.combo.offers))
        honored[quote_id] = HonoredQuote(quote, placement, note_list)
    relief = sum(h.placement.compensation for h in honored.values() if h.placement)
    remaining = {slot: state.confirmed - used.get(slot, 0) for slot, state in view.inventory.items()}
    if relief > view.compensation_limit:
        manual.append({"报价": None, "家庭": None, "原因": f"救济补差{relief}元超出本轮限额{view.compensation_limit}元，需人工审批"})
    return honored, remaining, relief, manual


def competition(view, plans, remaining):
    """同批可信需求（最低可兑现价不超预算）的联合安置与支出分布。

    返回 {家庭: {安置方案数, 可安置, 稳定, 支出}}；支出是该家庭在所有
    安置数最多的联合方案中被安置时的整程总价列表。
    """
    candidates = {}
    for family_id, plan in plans.items():
        family = view.family(family_id)
        combos = [c for c in plan.combos if all(remaining.get(s, 0) >= 1 for s in c.slots)]
        if not combos or combos[0].total > family.budget:
            continue  # 没有可兑现组合或确定超预算的需求不构成竞争
        candidates[family_id] = [Placement(combo, 0, False) for combo in combos]
    assignments = enumerate_assignments(candidates, remaining) if candidates else []
    distribution = {}
    for family_id in candidates:
        placed = sorted(a[family_id].combo.total for a in assignments if family_id in a)
        distribution[family_id] = {
            "安置方案数": len(assignments),
            "可安置": bool(placed),
            "稳定": len(placed) == len(assignments),
            "支出": placed,
        }
    return distribution
