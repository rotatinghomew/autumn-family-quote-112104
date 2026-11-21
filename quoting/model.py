"""领域模型与指定轮次的资料视图。

轮次（seq）是资料里的时间轴：报价有效期、库存事件、补差预算都按轮次对齐。
报价在 ``seq <= expires`` 时有效；库存取每个场次不晚于该轮次的最新记录，
确认数较上一轮减少即为外部撤回。
"""
from __future__ import annotations

from dataclasses import dataclass

BOOKABLE = "可订"
INQUIRY_ONLY = "仅询价"


def parse_time(text):
    hours, minutes = str(text).split(":")
    return int(hours) * 60 + int(minutes)


def format_time(minutes):
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


@dataclass(frozen=True)
class Family:
    family: str
    adults: int
    children: int
    start: int
    end: int
    budget: int
    flexible_time: int  # 家庭接受的额外改时分钟


@dataclass(frozen=True)
class Slot:
    slot: str
    station: str
    start: int
    end: int
    travel_to_next_min: int


@dataclass(frozen=True)
class Offer:
    offer: str
    slot: str
    adults: int  # 组合允许的人数上限
    children: int
    base: int
    required_fee: int
    expires: int  # 有效期（含）至第几轮
    certainty: str

    @property
    def price(self):
        """整组合含税价：底价加必选服务费。"""
        return self.base + self.required_fee

    @property
    def bookable(self):
        return self.certainty == BOOKABLE

    def valid_at(self, seq):
        return seq <= self.expires

    def fits_party(self, family):
        return family.adults <= self.adults and family.children <= self.children


@dataclass(frozen=True)
class InventoryState:
    slot: str
    confirmed: int  # 可供购买的家庭组合数
    ambiguous: int  # 尚未承认的额外组合
    seq: int
    previous_confirmed: int | None

    @property
    def withdrawn(self):
        return self.previous_confirmed is not None and self.confirmed < self.previous_confirmed

    @property
    def withdrawn_amount(self):
        return self.previous_confirmed - self.confirmed if self.withdrawn else 0


@dataclass(frozen=True)
class Quote:
    quote: str
    family: str
    options: tuple  # 完整备选，每项是报价编号元组
    locked: tuple | None  # 实际确认的一项
    promised: int
    accepted: bool
    seq: int


class BookView:
    """某一团期轮次下的核对视图。"""

    def __init__(self, seq, families, slots, offers, inventory, compensation_limit, quotes):
        self.seq = seq
        self.families = families
        self.slots = slots
        self.offers = offers
        self.inventory = inventory
        self.compensation_limit = compensation_limit
        self.quotes = quotes
        self._family = {f.family: f for f in families}
        self._offer = {o.offer: o for o in offers}
        self._slot = {s.slot: s for s in slots}

    def family(self, family_id):
        return self._family[family_id]

    def offer(self, offer_id):
        return self._offer[offer_id]

    def slot(self, slot_id):
        return self._slot[slot_id]

    def accepted_quotes(self):
        return [q for q in self.quotes if q.accepted]

    def quotes_of(self, family_id):
        return [q for q in self.quotes if q.family == family_id]


def build_view(book, seq):
    families = tuple(
        Family(r["family"], r["adults"], r["children"], parse_time(r["start"]), parse_time(r["end"]), r["budget"], r["flexible_time"])
        for r in book["families"]
    )
    slots = tuple(
        Slot(r["slot"], r["station"], parse_time(r["start"]), parse_time(r["end"]), r["travel_to_next_min"])
        for r in book["products"]
    )
    offers = tuple(
        Offer(r["offer"], r["slot"], r["adults"], r["children"], r["base"], r["required_fee"], r["expires"], r["certainty"])
        for r in book["offers"]
    )
    inventory = {}
    for row in sorted(book["inventory"], key=lambda r: r["seq"]):
        if row["seq"] > seq:
            continue
        prev = inventory.get(row["slot"])
        inventory[row["slot"]] = InventoryState(
            row["slot"], row["confirmed"], row["ambiguous"], row["seq"], prev.confirmed if prev else None
        )
    limit = 0
    for row in sorted(book["authority"], key=lambda r: r["seq"]):
        if row["seq"] <= seq:
            limit = row["compensation_limit"]
    quotes = tuple(
        Quote(
            q["quote"],
            q["family"],
            tuple(tuple(option) for option in q["options"]),
            tuple(q["locked"]) if q["locked"] else None,
            q["promised"],
            q["accepted"],
            q["seq"],
        )
        for q in book["quotes"]
        if q["seq"] <= seq
    )
    return BookView(seq, families, slots, offers, inventory, limit, quotes)
