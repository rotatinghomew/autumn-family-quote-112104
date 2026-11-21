"""书面保价签发：只在授权与可兑现条件同时成立时出具。

签发前核对：每个备选都是完整且当前可兑现的整程组合；已受理保价预留后
库存仍够（同一家庭的多个备选只按一份需求核对，不会同时扣掉多个名额）；
承诺价低于成本所需的补差不超出本轮剩余补差预算。保价有效期取各备选
报价有效期可支撑的最后一轮。任何一项不满足就拒签并说明，不出具
更便宜却不完整或不可兑现的保价。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .allocate import honor_accepted
from .plan import resolve_option


@dataclass
class IssueDecision:
    ok: bool
    reasons: list = field(default_factory=list)
    quote_row: dict | None = None
    valid_until: int | None = None
    compensation_reserved: int = 0


def issue_guarantee(view, family_id, option_offer_ids, promised, quote_id=None):
    try:
        family = view.family(family_id)
    except KeyError:
        return IssueDecision(False, [f"家庭{family_id}不存在"])
    if any(q.accepted for q in view.quotes_of(family_id)):
        return IssueDecision(False, ["该家庭已有受理保证，不能重复签发"])
    if not option_offer_ids:
        return IssueDecision(False, ["至少需要一个完整备选"])

    combos, reasons = [], []
    for option in option_offer_ids:
        combo, problems = resolve_option(view, family, option)
        if combo is None:
            reasons.append("备选（" + "、".join(option) + "）不可兑现：" + "；".join(p.detail for p in problems))
        else:
            combos.append(combo)
    if reasons:
        return IssueDecision(False, reasons + ["不出具更便宜却不完整或不可兑现的保价"])

    _, remaining, relief, _ = honor_accepted(view)
    for combo in combos:
        short = [s for s in combo.slots if remaining.get(s, 0) < 1]
        if short:
            reasons.append(f"备选（{'、'.join(combo.offers)}）所需场次{'、'.join(short)}在受理保证预留后已无确认库存")
    if reasons:
        return IssueDecision(False, reasons)

    costs = [combo.total for combo in combos]
    subsidy = max(0, max(costs) - promised)
    headroom = view.compensation_limit - relief
    if subsidy > headroom:
        return IssueDecision(False, [f"承诺价{promised}元低于最高成本{max(costs)}元，需补差{subsidy}元，超出本轮剩余补差预算{headroom}元"])

    valid_until = max(min(leg.offer.expires for leg in combo.legs) for combo in combos)
    if valid_until < view.seq:
        return IssueDecision(False, ["所有备选的报价有效期已过，不能出具有期限的保价"])

    row = {
        "quote": quote_id or f"q{view.seq}-{family_id}",
        "family": family_id,
        "options": [list(combo.offers) for combo in combos],
        "locked": None,
        "promised": promised,
        "accepted": False,
        "seq": view.seq,
    }
    return IssueDecision(True, ["符合授权与库存条件，可签发"], row, valid_until, subsidy)
