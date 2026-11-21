"""整程组合枚举与报价适用性核对。

整程组合必须每站各选一个场次、互不重叠、时段与接驳可核对；
每个场次取当前可订（有效、可订、人数适用）的最低报价。
只询价或已过期的报价不进入可订组合，只作为阻碍与参考记录下来。
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass

from .timeline import check_timing

BLOCK_TIMING = "时段冲突"
BLOCK_PARTY = "人数超限"
BLOCK_EXPIRED = "报价已过期"
BLOCK_INQUIRY = "仅询价"
BLOCK_NO_OFFER = "无可用报价"
BLOCK_INVENTORY = "库存不足"
BLOCK_AMBIGUOUS = "库存未承认"
BLOCK_INCOMPLETE = "组合不完整"


@dataclass(frozen=True)
class Blocker:
    kind: str
    detail: str


@dataclass(frozen=True)
class Leg:
    slot: object
    offer: object


@dataclass(frozen=True)
class Combo:
    legs: tuple
    total: int
    needed_flex: int

    @property
    def offers(self):
        return tuple(leg.offer.offer for leg in self.legs)

    @property
    def slots(self):
        return tuple(leg.slot.slot for leg in self.legs)

    def describe(self):
        return "＋".join(f"{leg.slot.station}场次{leg.slot.slot}（报价{leg.offer.offer} {leg.offer.price}元）" for leg in self.legs)


@dataclass
class SlotOfferCheck:
    """单个场次对家庭报价的核对结果。"""

    slot: object
    bookable: list  # 有效、可订且人数适用
    inquiry: list  # 有效、人数适用但仅可询价
    expired: list  # 人数适用但已过期
    party_blocked: list  # 有效可订但人数上限不适用

    @property
    def cheapest(self):
        return min(self.bookable, key=lambda o: (o.price, o.offer), default=None)

    def primary_blocker(self):
        if self.cheapest is not None:
            return None
        if self.inquiry:
            ids = "、".join(o.offer for o in self.inquiry)
            return Blocker(BLOCK_INQUIRY, f"{self.slot.station}场次{self.slot.slot}的报价{ids}仅可询价，不能当作确定可购")
        if self.expired:
            ids = "、".join(f"{o.offer}（第{o.expires}轮后失效）" for o in self.expired)
            return Blocker(BLOCK_EXPIRED, f"{self.slot.station}场次{self.slot.slot}的报价{ids}已过期")
        if self.party_blocked:
            ids = "、".join(f"{o.offer}（限{o.adults}大{o.children}小）" for o in self.party_blocked)
            return Blocker(BLOCK_PARTY, f"{self.slot.station}场次{self.slot.slot}的报价{ids}人数上限不适用")
        return Blocker(BLOCK_NO_OFFER, f"{self.slot.station}场次{self.slot.slot}没有可用报价")


def check_slot_offers(view, family, slot):
    bookable, inquiry, expired, party_blocked = [], [], [], []
    for offer in view.offers:
        if offer.slot != slot.slot:
            continue
        if not offer.fits_party(family):
            if offer.valid_at(view.seq) and offer.bookable:
                party_blocked.append(offer)
            continue
        if not offer.valid_at(view.seq):
            expired.append(offer)
        elif not offer.bookable:
            inquiry.append(offer)
        else:
            bookable.append(offer)
    return SlotOfferCheck(slot, bookable, inquiry, expired, party_blocked)


def slot_combinations(view):
    """每站选一个场次且互不重叠的全部组合，按开始时刻排序。"""
    by_station = {}
    for slot in view.slots:
        by_station.setdefault(slot.station, []).append(slot)
    for picked in itertools.product(*by_station.values()):
        ordered = tuple(sorted(picked, key=lambda s: (s.start, s.end, s.slot)))
        if any(nxt.start < cur.end for cur, nxt in zip(ordered, ordered[1:])):
            continue
        yield ordered


@dataclass
class FamilyPlan:
    family: object
    combos: list  # 报价层面可订的整程组合（尚未核对库存），按价格升序
    blocked: list  # (场次组合, (Blocker, ...))：时段可行但报价层面受阻
    timing_failed: list  # (场次组合, Timing)：时段不可行


def enumerate_plan(view, family):
    combos, blocked, timing_failed = [], [], []
    for ordered in slot_combinations(view):
        timing = check_timing(family, ordered)
        if not timing.feasible_for(family):
            timing_failed.append((ordered, timing))
            continue
        legs, problems = [], []
        for slot in ordered:
            check = check_slot_offers(view, family, slot)
            offer = check.cheapest
            if offer is None:
                problems.append(check.primary_blocker())
            else:
                legs.append(Leg(slot, offer))
        if problems:
            blocked.append((ordered, tuple(problems)))
        else:
            combos.append(Combo(tuple(legs), sum(leg.offer.price for leg in legs), timing.needed_flex))
    combos.sort(key=lambda c: (c.total, c.offers))
    return FamilyPlan(family, combos, blocked, timing_failed)


def resolve_option(view, family, offer_ids):
    """把保价备选（报价编号列表）核成整程组合；核不过返回阻碍列表。"""
    offers, problems = [], []
    for offer_id in offer_ids:
        try:
            offer = view.offer(offer_id)
        except KeyError:
            problems.append(Blocker(BLOCK_NO_OFFER, f"报价{offer_id}不存在"))
            continue
        offers.append(offer)
        if not offer.valid_at(view.seq):
            problems.append(Blocker(BLOCK_EXPIRED, f"报价{offer.offer}第{offer.expires}轮后失效"))
        elif not offer.bookable:
            problems.append(Blocker(BLOCK_INQUIRY, f"报价{offer.offer}仅可询价，不能当作确定可购"))
        elif not offer.fits_party(family):
            problems.append(
                Blocker(BLOCK_PARTY, f"报价{offer.offer}限{offer.adults}大{offer.children}小，家庭为{family.adults}大{family.children}小")
            )
    slots = []
    for offer in offers:
        try:
            slots.append(view.slot(offer.slot))
        except KeyError:
            problems.append(Blocker(BLOCK_NO_OFFER, f"报价{offer.offer}指向不存在的场次{offer.slot}"))
    stations = {slot.station for slot in view.slots}
    covered = {slot.station for slot in slots}
    if covered != stations or len(slots) != len(stations):
        problems.append(Blocker(BLOCK_INCOMPLETE, "整程组合没有覆盖全部站点或同站重复"))
    timing = None
    if not problems:
        ordered = tuple(sorted(slots, key=lambda s: (s.start, s.end, s.slot)))
        if any(nxt.start < cur.end for cur, nxt in zip(ordered, ordered[1:])):
            problems.append(Blocker(BLOCK_TIMING, "场次时间重叠"))
        else:
            timing = check_timing(family, ordered)
            if not timing.feasible_for(family):
                problems.append(Blocker(BLOCK_TIMING, f"需改时{timing.needed_flex}分钟，家庭仅接受{family.flexible_time}分钟"))
    if problems:
        return None, tuple(problems)
    by_slot = {slot.slot: slot for slot in slots}
    legs = tuple(sorted((Leg(by_slot[offer.slot], offer) for offer in offers), key=lambda leg: leg.slot.start))
    return Combo(legs, sum(leg.offer.price for leg in legs), timing.needed_flex), ()


def reference_total(view, family, ordered_slots):
    """参考价：取每场次人数适用的最低报价（不问有效期与可订性），仅用于对照。"""
    total = 0
    for slot in ordered_slots:
        offers = [o for o in view.offers if o.slot == slot.slot and o.fits_party(family)]
        if not offers:
            return None
        total += min(o.price for o in offers)
    return total
