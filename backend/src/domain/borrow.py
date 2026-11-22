"""按期末在管清册为活动场次分配工具。

口径：
- 工具只从期末在管（in_custody）清册出，借出与退役工具不可排。
- 日期重叠的场次不共用同一件工具；同一事件内一件工具也只能用一次。
- 任一需求行缺一件，整场待排，已凑到的工具不预扣。
- 重点场先于普通场；同级内按开始日期、结束日期、登记顺序依次排期。
- 替用品按登记顺序递补主工具的缺口。
"""

_PRIORITY_ORDER = {"key": 0, "normal": 1}


def pool_summary(register):
    """按工具名称汇总在管件数，供排借表单参考。"""
    counts = {}
    for item in register:
        if item["status"] == "in_custody":
            counts[item["asset_name"]] = counts.get(item["asset_name"], 0) + 1
    return [{"asset_name": name, "in_custody": count} for name, count in sorted(counts.items())]


def _shortage(index, line, need, got, pool, blocked, taken, event):
    names = [line["tool"], *line["substitutes"]]
    if not any(pool.get(name) for name in names):
        suffix = "及替用品" if line["substitutes"] else ""
        return f"第{index}项「{line['tool']}」{suffix}不在期末在管清册"
    free = {name: sum(1 for asset in pool.get(name, [])
                      if asset not in taken and not blocked(asset, event["start"], event["end"]))
            for name in names}
    parts = "，".join(f"「{name}」可排{count}件" for name, count in free.items())
    held = sum(len(pool.get(name, [])) for name in names) - sum(free.values())
    note = f"，{held}件被本场其他需求或重叠日期场次占用" if held else ""
    return f"第{index}项「{line['tool']}」需{need}件，{parts}{note}，缺{need - got}件"


def allocate(events, register, occupied):
    """为场次分配工具。

    events: [{'key', 'start', 'end', 'priority', 'lines': [{'tool', 'quantity', 'substitutes'}]}]
    register: register_at 返回的资产清册；occupied: 其他已确认方案的占用 [{'asset_id', 'start', 'end'}]。
    返回 {event_key: {'status', 'assignments', 'reason'}}。
    """
    pool = {}
    names = {}
    for item in register:
        names[item["asset_id"]] = item["asset_name"]
        if item["status"] == "in_custody":
            pool.setdefault(item["asset_name"], []).append(item["asset_id"])
    for assets in pool.values():
        assets.sort()
    claims = [(claim["asset_id"], claim["start"], claim["end"]) for claim in occupied]

    def blocked(asset_id, start, end):
        return any(holder == asset_id and begin <= end and start <= finish
                   for holder, begin, finish in claims)

    results = {}
    ordered = sorted(events, key=lambda event: (_PRIORITY_ORDER.get(event["priority"], 1),
                                                event["start"], event["end"], event["key"]))
    for event in ordered:
        assignments = []
        taken = set()
        shortages = []
        for index, line in enumerate(event["lines"], 1):
            need = line["quantity"]
            picked = []
            for name in [line["tool"], *line["substitutes"]]:
                for asset_id in pool.get(name, []):
                    if len(picked) >= need:
                        break
                    if asset_id in taken or blocked(asset_id, event["start"], event["end"]):
                        continue
                    picked.append(asset_id)
                if len(picked) >= need:
                    break
            if len(picked) < need:
                shortages.append(_shortage(index, line, need, len(picked), pool, blocked, taken, event))
                continue
            taken.update(picked)
            for asset_id in picked:
                assignments.append({"asset_id": asset_id, "asset_name": names[asset_id], "line": index,
                                    "tool": line["tool"],
                                    "via": None if names[asset_id] == line["tool"] else names[asset_id]})
        if shortages:
            results[event["key"]] = {"status": "pending", "assignments": [],
                                     "reason": "；".join(shortages)}
        else:
            claims.extend((item["asset_id"], event["start"], event["end"]) for item in assignments)
            results[event["key"]] = {"status": "scheduled", "assignments": assignments, "reason": None}
    return results
