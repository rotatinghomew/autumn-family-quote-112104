"""家庭维度的兑现评估：状态分类、支出分布、敏感约束与重新联系原因。

分类口径：
- 已有保证：存在已受理保价，按锁定或改派后的组合履约；
- 可承诺：存在可兑现组合且最低价不超预算；
- 确定超预算：存在可兑现组合但最低价仍超预算；
- 证据不足：时段可行的组合只被仅询价报价或未承认库存挡住，无法给出确定价格；
- 暂不成交：组合被过期报价、人数上限、确认库存用尽或时段冲突挡住。

敏感约束保留使结果对库存或时段变化敏感的关键条件：单一阻碍解除后
结论就会改变的组合逐条列出。
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from .plan import (
    BLOCK_AMBIGUOUS,
    BLOCK_INQUIRY,
    Blocker,
    reference_total,
    resolve_option,
)

STATUS_COMMITTABLE = "可承诺"
STATUS_INSUFFICIENT_EVIDENCE = "证据不足"
STATUS_STALLED = "暂不成交"
STATUS_OVER_BUDGET = "确定超预算"
STATUS_GUARANTEED = "已有保证"

EVIDENCE_KINDS = {BLOCK_INQUIRY, BLOCK_AMBIGUOUS}


@dataclass
class Assessment:
    family: str
    status: str
    typical: dict | None
    committable: dict | None
    reasons: list = field(default_factory=list)
    sensitivities: list = field(default_factory=list)
    manual: bool = False
    recontact: list = field(default_factory=list)


def _stock_check(view, plan, remaining):
    """把报价层面可订的组合再过一遍确认库存。"""
    deliverable, stock_blocked = [], []
    for combo in plan.combos:
        short = [s for s in combo.slots if remaining.get(s, 0) < 1]
        if not short:
            deliverable.append(combo)
            continue
        details, evidence_only = [], True
        for slot_id in short:
            state = view.inventory.get(slot_id)
            slot = view.slot(slot_id)
            if state is not None and state.ambiguous > 0:
                details.append(Blocker(BLOCK_AMBIGUOUS, f"{slot.station}场次{slot_id}仅剩未承认库存{state.ambiguous}个"))
            else:
                evidence_only = False
                extra = f"（第{state.seq}轮由{state.previous_confirmed}撤至{state.confirmed}）" if state is not None and state.withdrawn else ""
                details.append(Blocker("库存不足", f"{slot.station}场次{slot_id}确认库存已用尽{extra}"))
        stock_blocked.append((combo, tuple(details), evidence_only))
    return deliverable, stock_blocked


def assess_family(view, family, plan, remaining, competition_info, honored, open_quotes):
    reasons, sensitivities, recontact = [], [], []
    manual = False

    if honored is not None:
        placement = honored.placement
        combo = placement.combo
        typical = {"最低": honored.family_pays, "典型": honored.family_pays, "最高": honored.family_pays, "稳定": True}
        committable = {
            "价格": honored.quote.promised,
            "组合": combo.describe(),
            "报价": list(combo.offers),
            "保价有效期至第几轮": min(leg.offer.expires for leg in combo.legs),
            "竞争下稳定": True,
        }
        reasons.extend(honored.notes)
        if placement.changed:
            recontact.append(f"保证{honored.quote.quote}已改派场次，需通知家庭确认新场次")
        if placement.compensation > 0:
            reasons.append(f"改派差价{placement.compensation}元由运营承担（本轮补差预算）")
        return Assessment(family.family, STATUS_GUARANTEED, typical, committable, reasons, sensitivities, manual, recontact)

    deliverable, stock_blocked = _stock_check(view, plan, remaining)
    typical = committable = None

    if deliverable:
        cheapest = deliverable[0]
        info = competition_info.get(family.family)
        if info is not None and not info["可安置"]:
            status = STATUS_STALLED
            reasons.append("同批需求超出库存，联合安置下该家庭的组合无法同时兑现")
        elif cheapest.total <= family.budget:
            status = STATUS_COMMITTABLE
            valid_until = min(leg.offer.expires for leg in cheapest.legs)
            committable = {
                "价格": cheapest.total,
                "组合": cheapest.describe(),
                "报价": list(cheapest.offers),
                "保价有效期至第几轮": valid_until,
                "竞争下稳定": info["稳定"] if info else True,
            }
        else:
            status = STATUS_OVER_BUDGET
            reasons.append(f"最低可兑现整程{cheapest.total}元超出预算{family.budget}元")
        if info is not None and info["可安置"] and info["支出"]:
            values = info["支出"]
            typical = {"最低": values[0], "典型": int(statistics.median(values)), "最高": values[-1], "稳定": info["稳定"]}
            if not info["稳定"]:
                reasons.append("同批需求竞争下该价格组合可能被用尽，不作为确定的预计支出")
        elif status != STATUS_STALLED:
            typical = {"最低": cheapest.total, "典型": cheapest.total, "最高": deliverable[-1].total, "稳定": True}
    else:
        evidence_combo = None
        for ordered, blockers in plan.blocked:
            if blockers and all(b.kind in EVIDENCE_KINDS for b in blockers):
                evidence_combo = (ordered, blockers)
                break
        if evidence_combo is None:
            for combo, blockers, evidence_only in stock_blocked:
                if evidence_only:
                    evidence_combo = (combo, blockers)
                    break
        if evidence_combo is not None:
            status = STATUS_INSUFFICIENT_EVIDENCE
            reasons.extend(b.detail for b in evidence_combo[1])
            reasons.append("上述余位或报价尚未确认，不能当作确定可购")
        else:
            status = STATUS_STALLED
            for ordered, blockers in plan.blocked[:3]:
                reasons.extend(b.detail for b in blockers)
            for combo, blockers, _ in stock_blocked[:3]:
                reasons.extend(b.detail for b in blockers)
                if combo.total > family.budget:
                    reasons.append(f"即便恢复库存，组合（{'、'.join(combo.slots)}）{combo.total}元仍超预算{family.budget}元")
            if not plan.blocked and not stock_blocked:
                for ordered, timing in plan.timing_failed[:3]:
                    slots = "、".join(s.slot for s in ordered)
                    reasons.append(f"场次组合（{slots}）需改时{timing.needed_flex}分钟，家庭仅接受{family.flexible_time}分钟")

    # 敏感约束：单一阻碍解除后结论就会改变的组合
    for combo, blockers, _ in stock_blocked:
        if len(blockers) == 1:
            sensitivities.append(f"{blockers[0].detail}：若解除，整程{combo.total}元可承诺")
        else:
            kinds = "、".join(b.kind for b in blockers)
            sensitivities.append(f"组合（{'、'.join(combo.slots)}）同时受{kinds}限制")
    for ordered, blockers in plan.blocked:
        slots = "、".join(s.slot for s in ordered)
        if len(blockers) == 1:
            ref = reference_total(view, family, ordered)
            suffix = f"，整程参考{ref}元（报价状态待确认）" if ref is not None else ""
            sensitivities.append(f"{blockers[0].detail}：若解除{suffix}")
        else:
            kinds = "、".join(sorted({b.kind for b in blockers}))
            sensitivities.append(f"组合（{slots}）同时受{kinds}限制")
    for ordered, timing in plan.timing_failed:
        gap = timing.needed_flex - family.flexible_time
        if 0 < gap <= 60:
            slots = "、".join(s.slot for s in ordered)
            sensitivities.append(f"组合（{slots}）需家庭再放宽改时{gap}分钟才可行")
    sensitivities = sensitivities[:5]

    for quote in open_quotes:
        usable = False
        for option in quote.options:
            combo, _ = resolve_option(view, family, option)
            if combo is not None and all(remaining.get(s, 0) >= 1 for s in combo.slots):
                usable = True
                break
        if not usable:
            recontact.append(f"已发保价{quote.quote}（承诺{quote.promised}元）当前没有可兑现的备选，需重新联系家庭")
            manual = True
    return Assessment(family.family, status, typical, committable, reasons, sensitivities, manual, recontact)
