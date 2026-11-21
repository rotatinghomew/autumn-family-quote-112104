"""客服查询视图：典型支出、目前可承诺的价格、已发保证、需重新联系的原因。"""
from __future__ import annotations

from .plan import resolve_option


def _honored_entry(honored):
    quote = honored.quote
    combo = honored.placement.combo
    return {
        "报价": quote.quote,
        "承诺": quote.promised,
        "状态": "已受理·改派" if honored.placement.changed else "已受理·履约",
        "现组合": list(combo.offers),
        "家庭应付": honored.family_pays,
        "运营承担": honored.placement.compensation,
        "有效期至第几轮": min(leg.offer.expires for leg in combo.legs),
        "说明": honored.notes,
    }


def _open_entry(view, quote, remaining):
    family = view.family(quote.family)
    usable = []
    for option in quote.options:
        combo, _ = resolve_option(view, family, option)
        if combo is not None and all(remaining.get(s, 0) >= 1 for s in combo.slots):
            usable.append(list(option))
    valid_until = max(min(view.offer(o).expires for o in option) for option in quote.options)
    return {
        "报价": quote.quote,
        "承诺": quote.promised,
        "状态": "待受理·可兑现" if usable else "待受理·无法兑现",
        "可兑现备选": usable,
        "有效期至第几轮": valid_until,
    }


def build_service_view(view, family, assessment, honored, open_quotes, remaining):
    guarantees = []
    if honored is not None:
        guarantees.append(_honored_entry(honored))
    for quote in open_quotes:
        guarantees.append(_open_entry(view, quote, remaining))
    return {
        "家庭": family.family,
        "状态": assessment.status,
        "典型支出": assessment.typical,
        "目前可承诺": assessment.committable,
        "已发保证": guarantees,
        "需要重新联系": {"需要": bool(assessment.recontact), "原因": assessment.recontact},
        "敏感约束": assessment.sensitivities,
        "转人工": assessment.manual,
        "说明": assessment.reasons,
    }
