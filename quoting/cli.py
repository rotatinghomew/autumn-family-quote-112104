"""命令行：团期报价兑现报告、客服查询、保价签发、库存检视。"""
import argparse
import json
import sys
from pathlib import Path

from source_book import load

from .analyze import analyze, naive_calendar_sum, service_views
from .guarantee import issue_guarantee
from .model import build_view


def _print(payload):
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def cmd_inventory(args):
    view = build_view(load(args.path), args.seq)
    state = {
        slot: {
            "确认": s.confirmed,
            "未承认": s.ambiguous,
            "撤回": s.withdrawn_amount,
            "记录轮次": s.seq,
        }
        for slot, s in sorted(view.inventory.items())
    }
    _print({"轮次": view.seq, "库存": state, "补差预算": view.compensation_limit})
    return 0


def cmd_report(args):
    view = build_view(load(args.path), args.seq)
    honored, remaining, relief, manual, plans, _, assessments = analyze(view)
    honored_list = [
        {
            "报价": h.quote.quote,
            "家庭": h.quote.family,
            "承诺": h.quote.promised,
            "组合": list(h.placement.combo.offers),
            "改派": h.placement.changed,
            "家庭应付": h.family_pays,
            "运营承担": h.placement.compensation,
            "说明": h.notes,
        }
        for h in honored.values()
    ]
    families = {}
    for family in view.families:
        a = assessments[family.family]
        entry = {
            "状态": a.status,
            "典型支出": a.typical,
            "目前可承诺": a.committable,
            "敏感约束": a.sensitivities,
            "需要重新联系": a.recontact,
            "转人工": a.manual,
            "说明": a.reasons,
        }
        naive = naive_calendar_sum(view, family)
        if naive is not None:
            entry["诊断"] = {"日历低价合计": naive, "提示": "不核时段、库存与可订性，不可兑现，不能当作预计支出"}
        families[family.family] = entry
    _print(
        {
            "轮次": view.seq,
            "补差预算": {"限额": view.compensation_limit, "救济已用": relief, "剩余": view.compensation_limit - relief},
            "受理保证履约": honored_list,
            "剩余库存": remaining,
            "家庭评估": families,
            "人工处理": manual,
        }
    )
    return 0


def cmd_service(args):
    view = build_view(load(args.path), args.seq)
    views = service_views(view)
    if args.family:
        if args.family not in views:
            print(f"未知家庭：{args.family}", file=sys.stderr)
            return 1
        _print(views[args.family])
    else:
        _print(views)
    return 0


def cmd_issue(args):
    book = load(args.path)
    view = build_view(book, args.seq)
    options = [option.split(",") for option in args.option]
    decision = issue_guarantee(view, args.family, options, args.promised)
    payload = {
        "可签发": decision.ok,
        "原因": decision.reasons,
        "保价有效期至第几轮": decision.valid_until,
        "预留补差": decision.compensation_reserved,
    }
    if decision.ok and args.out:
        raw = json.loads(Path(args.path).read_text(encoding="utf-8"))
        row = decision.quote_row
        raw["tables"]["quotes"]["rows"].append(
            [row["quote"], row["family"], row["options"], row["locked"], row["promised"], row["accepted"], row["seq"]]
        )
        Path(args.out).write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
        payload["已写入"] = str(args.out)
        payload["新保价"] = row
    _print(payload)
    return 0 if decision.ok else 1


def main(argv=None):
    parser = argparse.ArgumentParser(prog="quoting", description="多站研学报价兑现引擎")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, help_text, func in [
        ("inventory", "查看某轮次的库存与撤回", cmd_inventory),
        ("report", "整批家庭的兑现评估报告", cmd_report),
        ("service", "客服查询：典型支出、可承诺价格、已发保证、重新联系原因", cmd_service),
        ("issue", "为家庭签发有期限的书面保价", cmd_issue),
    ]:
        p = sub.add_parser(name, help=help_text)
        p.add_argument("path", type=Path, help="交换资料 JSON")
        p.add_argument("--seq", type=int, required=True, help="团期轮次")
        p.set_defaults(func=func)
        if name == "service":
            p.add_argument("--family", help="只查某一个家庭")
        if name == "issue":
            p.add_argument("--family", required=True)
            p.add_argument("--option", action="append", required=True, help="完整备选，逗号分隔的报价编号，可多次给出")
            p.add_argument("--promised", type=int, required=True, help="承诺价（含税元）")
            p.add_argument("--out", type=Path, help="把新保价写入新的资料文件")
    args = parser.parse_args(argv)
    return args.func(args)
