import csv
import math
import random
from collections import defaultdict, namedtuple
from typing import Dict, List, Tuple

# =========================
# Config (tune as needed)
# =========================
RANDOM_SEED = 13
BUS_CAPACITY = 45                      # seats per bus
SHIFT_CHOICES = [-15, 0, 15]           # allowed per-departure minute shifts (route stays the same)
MAX_ADD_PER_DEP = 2                    # max added buses on a departure
UNMET_PENALTY = 28.0                   # higher to strongly prefer relieving overloads
RUN_COST = 3.0                         # operating cost per bus-departure
ADD_COST = 120.0                       # fixed cost per added bus
DROP_SAFETY_MARGIN_SEATS = 20          # slack that must remain after a drop on every affected link-time
POP_SIZE = 60
ELITE = 6
GENERATIONS = 400
MUTATION_RATE = 0.07

random.seed(RANDOM_SEED)

Route = namedtuple("Route", ["route_id", "stops", "travel_min"])

# =========================
# Time helpers
# =========================
def parse_time_to_min(tstr: str) -> int:
    h, m = map(int, tstr.strip().split(":"))
    return h * 60 + m

def min_to_timestr(m: int) -> str:
    m %= (24 * 60)
    return f"{m // 60:02d}:{m % 60:02d}"

# =========================
# CSV helpers
# =========================
def _pick(field_map: Dict[str, str], candidates: List[str]):
    for c in candidates:
        if c in field_map:
            return field_map[c]
    return None

def _gen_trip_id(route_id: str, dep_min: int, used: set) -> str:
    base = f"{route_id}-{min_to_timestr(dep_min).replace(':','')}"
    alpha = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    i = 0
    while True:
        tid = f"{base}-{alpha[i % 26]}"
        i += 1
        if tid not in used:
            used.add(tid)
            return tid

def load_schedule(path: str):
    """
    One row per physical bus (trip) with a unique trip_id:
      route_id,trip_id,stops_pipe,travel_min_pipe,dep_time,base_buses,passengers,dep_od_pipe
    dep_od_pipe is '|' groups like ORG:DST:PAX; each row is treated as 1 bus and base_buses is forced to 1 for clarity.
    """
    with open(path, newline="", encoding="utf-8-sig") as f:
        rdr = csv.DictReader(f, skipinitialspace=True, restval="")
        if not rdr.fieldnames:
            raise ValueError("schedule.csv: missing header row")

        fmap = {h.strip().lower(): h.strip() for h in rdr.fieldnames}
        rid_col   = _pick(fmap, ["route_id", "route", "line"])
        trip_col  = _pick(fmap, ["trip_id", "run_id", "bus_id"])
        stops_col = _pick(fmap, ["stops_pipe", "stops"])
        tmins_col = _pick(fmap, ["travel_min_pipe", "travel_min", "link_mins"])
        time_col  = _pick(fmap, ["dep_time", "time", "dep", "departure"])
        base_col  = _pick(fmap, ["base_buses", "buses", "base"])
        pax_col   = _pick(fmap, ["passengers", "pax", "total_pax"])
        od_col    = _pick(fmap, ["dep_od_pipe", "dep_od", "od_pipe", "od"])

        if not all([rid_col, stops_col, tmins_col, time_col, base_col]):
            raise ValueError("schedule.csv missing required columns")

        routes: Dict[str, Route] = {}
        rows_by_route: Dict[str, List[dict]] = defaultdict(list)
        for row in rdr:
            rid = row[rid_col].strip()
            if not rid or rid.startswith("#"):
                continue
            rows_by_route[rid].append(row)

        departures: Dict[str, List[Tuple[int, int]]] = defaultdict(list)
        per_dep_ods: Dict[Tuple[str, int], List[Tuple[int, int, int]]] = defaultdict(list)
        baseline_trip_ids: Dict[Tuple[str, int], List[str]] = {}
        used_trip_ids: set = set()

        for rid, rows in rows_by_route.items():
            # topology
            stops = [s.strip() for s in rows[0][stops_col].split("|")]
            tmins = [int(float(x)) for x in rows[0][tmins_col].split("|")]
            if len(tmins) != len(stops) - 1:
                raise ValueError(f"{rid}: travel_min_pipe must be |stops|-1")
            routes[rid] = Route(rid, stops, tmins)

            # group rows by time (multiple buses can share same minute)
            by_time: Dict[int, List[dict]] = defaultdict(list)
            for row in rows:
                dep_min = parse_time_to_min(row[time_col])
                by_time[dep_min].append(row)

            for dep_min in sorted(by_time.keys()):
                group = by_time[dep_min]
                trip_ids_for_dep = []
                # force each row to represent one bus
                for row in group:
                    base = int(float(row[base_col])) if row.get(base_col, "").strip() else 0
                    base = 1 if base <= 0 else 1
                    trip_id = row.get(trip_col, "").strip() if trip_col else ""
                    if not trip_id or trip_id in used_trip_ids:
                        trip_id = _gen_trip_id(rid, dep_min, used_trip_ids)
                    else:
                        used_trip_ids.add(trip_id)
                    trip_ids_for_dep.append(trip_id)

                idx = len(departures[rid])
                departures[rid].append((dep_min, len(trip_ids_for_dep)))
                baseline_trip_ids[(rid, idx)] = trip_ids_for_dep

                # aggregate OD from all rows at this time
                for row in group:
                    if od_col and row.get(od_col, "").strip():
                        for grp in row[od_col].split("|"):
                            grp = grp.strip()
                            if not grp:
                                continue
                            parts = [p.strip() for p in grp.split(":")]
                            if len(parts) != 3:
                                continue
                            o, d, p = parts
                            if o in stops and d in stops and stops.index(d) > stops.index(o):
                                per_dep_ods[(rid, idx)].append((stops.index(o), stops.index(d), int(float(p))))
                    elif pax_col and row.get(pax_col, "").strip():
                        pax = int(float(row[pax_col]))
                        if pax > 0:
                            per_dep_ods[(rid, idx)].append((0, len(stops) - 1, pax))

        return routes, departures, per_dep_ods, baseline_trip_ids

# =========================
# GA chromosome
# =========================
class Chromosome:
    def __init__(self, departures, shift_choices, max_add):
        self.shift = {rid: [random.choice(shift_choices) for _ in dep] for rid, dep in departures.items()}
        self.add   = {rid: [random.randint(0, max_add) for _ in dep] for rid, dep in departures.items()}
        self.drop  = {rid: [0 for _ in dep] for rid, dep in departures.items()}  # drop intent checked later

    def copy(self):
        c = Chromosome.__new__(Chromosome)
        c.shift = {rid: v[:] for rid, v in self.shift.items()}
        c.add   = {rid: v[:] for rid, v in self.add.items()}
        c.drop  = {rid: v[:] for rid, v in self.drop.items()}
        return c

# =========================
# Helpers to detect overloads
# =========================
def compute_base_cap_dem(routes, departures, per_dep_ods, capacity):
    cum = {}
    for rid, route in routes.items():
        co = [0]
        for t in route.travel_min:
            co.append(co[-1] + t)
        cum[rid] = co
    cap = defaultdict(int)
    dem = defaultdict(float)
    for rid, route in routes.items():
        for i, (dep_min, base) in enumerate(departures[rid]):
            at = dep_min
            if base > 0:
                for l in range(len(route.stops) - 1):
                    key = ((route.stops[l], route.stops[l + 1]), at + cum[rid][l])
                    cap[key] += capacity * base
            if (rid, i) in per_dep_ods:
                for oi, di, pax in per_dep_ods[(rid, i)]:
                    for l in range(oi, di):
                        key = ((route.stops[l], route.stops[l + 1]), at + cum[rid][l])
                        dem[key] += pax
    return cap, dem, cum

def build_shift_first_seed(routes, departures, per_dep_ods, shift_choices, capacity):
    seed = Chromosome(departures, shift_choices, MAX_ADD_PER_DEP)
    base_cap, base_dem, cum = compute_base_cap_dem(routes, departures, per_dep_ods, capacity)

    # Generic: steer into every overloaded link-time
    overloaded = set(k for k in base_dem if base_dem[k] > base_cap.get(k, 0))
    for ((u, v), t_over) in overloaded:
        for rid, route in routes.items():
            if (u, v) not in list(zip(route.stops[:-1], route.stops[1:])):
                continue
            link_idx = list(zip(route.stops[:-1], route.stops[1:])).index((u, v))
            for i, (dep_min, base) in enumerate(departures[rid]):
                if base <= 0:
                    continue
                # downstream carriers are frozen at their timing
                has_downstream = (rid, i) in per_dep_ods and any(di - oi > 1 for oi, di, _ in per_dep_ods[(rid, i)])
                if has_downstream:
                    continue
                needed = t_over - (dep_min + cum[rid][link_idx])
                if needed in shift_choices:
                    seed.shift[rid][i] = needed

    # Specific nudge: R1 14:00 -> 14:15 on CHD->RJP if allowed
    if "R1" in routes:
        route = routes["R1"]
        links = list(zip(route.stops[:-1], route.stops[1:]))
        if ("CHD", "RJP") in links:
            link_idx = links.index(("CHD", "RJP"))
            for i, (dep_min, base) in enumerate(departures["R1"]):
                if base <= 0:
                    continue
                if min_to_timestr(dep_min) == "14:00":
                    target_dep_time = parse_time_to_min("14:15")
                    needed = target_dep_time - (dep_min + 0)  # link_idx offset is 0 for CHD->RJP on R1
                    if needed in shift_choices:
                        seed.shift["R1"][i] = needed

    # Prefer shifts/adds first
    for rid in departures:
        seed.add[rid]  = [0] * len(departures[rid])
        seed.drop[rid] = [0] * len(departures[rid])
    return seed

# =========================
# Fitness with capacity-aware dropping and safety margin
# =========================
def evaluate(ch, routes, departures, per_dep_ods, capacity, run_cost, add_cost, unmet_penalty):
    # cumulative offsets
    cum = {}
    for rid, route in routes.items():
        co = [0]
        for t in route.travel_min:
            co.append(co[-1] + t)
        cum[rid] = co

    # Step 1: proposed moves
    proposed = {}
    for rid, dep in departures.items():
        lst = []
        for i, (dep_min, base) in enumerate(dep):
            has_downstream = (rid, i) in per_dep_ods and any(di - oi > 1 for oi, di, _ in per_dep_ods[(rid, i)])
            applied_shift = 0 if has_downstream else ch.shift[rid][i]
            lst.append({
                "dep_min": dep_min,
                "base": base,
                "req_drop": ch.drop[rid][i] if not has_downstream else 0,  # never drop when downstream riders exist
                "add": ch.add[rid][i],
                "shift": applied_shift,
            })
        proposed[rid] = lst

    # Step 2: tentative cap/dem with requested drops
    cap = defaultdict(int)
    dem = defaultdict(float)
    contrib = defaultdict(lambda: defaultdict(int))
    for rid, route in routes.items():
        for i, meta in enumerate(proposed[rid]):
            dep_min = meta["dep_min"]
            buses = max(0, meta["base"] - min(meta["req_drop"], meta["base"]) + meta["add"])
            at = dep_min + meta["shift"]
            if buses > 0:
                for l in range(len(route.stops) - 1):
                    key = ((route.stops[l], route.stops[l + 1]), at + cum[rid][l])
                    cap[key] += capacity * buses
                    contrib[(rid, i)][key] += capacity * buses
            if (rid, i) in per_dep_ods:
                for oi, di, pax in per_dep_ods[(rid, i)]:
                    for l in range(oi, di):
                        key = ((route.stops[l], route.stops[l + 1]), at + cum[rid][l])
                        dem[key] += pax

    # Step 3: enforce capacity-aware drops with safety margin
    for rid, route in routes.items():
        for i, meta in enumerate(proposed[rid]):
            req = min(meta["req_drop"], meta["base"])
            if req <= 0:
                continue
            # all covered link-times must keep enough slack after removal
            ok = True
            for key, seats in contrib[(rid, i)].items():
                if cap[key] - seats < dem.get(key, 0) + DROP_SAFETY_MARGIN_SEATS:
                    ok = False
                    break
            if not ok:
                meta["req_drop"] = 0

    # Step 4: rebuild capacity with only allowed drops
    cap.clear()
    for rid, route in routes.items():
        for i, meta in enumerate(proposed[rid]):
            dep_min = meta["dep_min"]
            buses = max(0, meta["base"] - min(meta["req_drop"], meta["base"]) + meta["add"])
            at = dep_min + meta["shift"]
            if buses > 0:
                for l in range(len(route.stops) - 1):
                    key = ((route.stops[l], route.stops[l + 1]), at + cum[rid][l])
                    cap[key] += capacity * buses

    # Step 5: unmet and costs
    unmet = 0
    for key, d in dem.items():
        if d > cap.get(key, 0):
            unmet += d - cap.get(key, 0)

    run_cost_val = 0
    add_cost_val = 0
    for rid, dep in departures.items():
        for i, meta in enumerate(proposed[rid]):
            buses = max(0, meta["base"] - min(meta["req_drop"], meta["base"]) + meta["add"])
            run_cost_val += buses * run_cost
            add_cost_val += meta["add"] * add_cost

    fitness = unmet_penalty * math.ceil(unmet) + run_cost_val + add_cost_val
    return fitness, {"unmet": int(math.ceil(unmet)), "run_cost": run_cost_val, "add_cost": add_cost_val}, proposed

# =========================
# GA loop with shift-first seed
# =========================
def tournament(pop, fits, k=3):
    idx = random.sample(range(len(pop)), k)
    return pop[min(idx, key=lambda i: fits[i])].copy()

def run_ga(routes, departures, per_dep_ods):
    seed = build_shift_first_seed(routes, departures, per_dep_ods, SHIFT_CHOICES, BUS_CAPACITY)
    pop = [seed] + [Chromosome(departures, SHIFT_CHOICES, MAX_ADD_PER_DEP) for _ in range(POP_SIZE - 1)]
    best = None
    best_fit = float("inf")
    best_info = {}
    best_proposed = None
    for g in range(GENERATIONS):
        fits, infos, props = [], [], []
        for ch in pop:
            f, info, proposed = evaluate(ch, routes, departures, per_dep_ods, BUS_CAPACITY, RUN_COST, ADD_COST, UNMET_PENALTY)
            fits.append(f); infos.append(info); props.append(proposed)
            if f < best_fit:
                best = ch.copy(); best_fit = f; best_info = info; best_proposed = proposed
        elite_idx = sorted(range(len(pop)), key=lambda i: fits[i])[:ELITE]
        new_pop = [pop[i].copy() for i in elite_idx]
        while len(new_pop) < POP_SIZE:
            p1 = tournament(pop, fits)
            p2 = tournament(pop, fits)
            c1 = p1.copy(); c2 = p2.copy()
            for rid in departures:
                n = len(departures[rid])
                cut = random.randint(1, n - 1) if n > 1 else 0
                if cut:
                    c1.shift[rid][:cut], c2.shift[rid][:cut] = p2.shift[rid][:cut], p1.shift[rid][:cut]
                    c1.add[rid][:cut],   c2.add[rid][:cut]   = p2.add[rid][:cut],   p1.add[rid][:cut]
                    c1.drop[rid][:cut],  c2.drop[rid][:cut]  = p2.drop[rid][:cut],  p1.drop[rid][:cut]
                for i in range(n):
                    if random.random() < MUTATION_RATE: c1.shift[rid][i] = random.choice(SHIFT_CHOICES)
                    if random.random() < MUTATION_RATE: c1.add[rid][i]   = max(0, min(MAX_ADD_PER_DEP, c1.add[rid][i] + random.choice([-1, 1])))
                    if random.random() < MUTATION_RATE: c1.drop[rid][i]  = max(0, min(departures[rid][i][1], c1.drop[rid][i] + random.choice([-1, 1])))
                    if random.random() < MUTATION_RATE: c2.shift[rid][i] = random.choice(SHIFT_CHOICES)
                    if random.random() < MUTATION_RATE: c2.add[rid][i]   = max(0, min(MAX_ADD_PER_DEP, c2.add[rid][i] + random.choice([-1, 1])))
                    if random.random() < MUTATION_RATE: c2.drop[rid][i]  = max(0, min(departures[rid][i][1], c2.drop[rid][i] + random.choice([-1, 1])))
            new_pop.append(c1)
            if len(new_pop) < POP_SIZE: new_pop.append(c2)
        pop = new_pop
        if (g + 1) % 50 == 0:
            print(f"Gen {g+1}: fitness={best_fit:.2f}, unmet={best_info['unmet']}, cost={best_info['run_cost']+best_info['add_cost']:.1f}")
    return best, best_fit, best_info, best_proposed

# =========================
# Plan builders and writers
# =========================
def build_plan_rows(best_proposed, routes, departures, per_dep_ods, baseline_trip_ids):
    rows = []
    for rid, dep in departures.items():
        for i, (dep_min, base) in enumerate(dep):
            meta = best_proposed[rid][i]
            shift = meta["shift"]
            allowed_drop = min(meta["req_drop"], base)
            add = meta["add"]
            kept = max(0, base - allowed_drop)

            kept_ids    = baseline_trip_ids[(rid, i)][:kept]
            dropped_ids = baseline_trip_ids[(rid, i)][kept:base]

            used = set()
            for k in baseline_trip_ids.values():
                used.update(k)
            added_ids = []
            for _ in range(add):
                added_ids.append(_gen_trip_id(rid, dep_min + shift, used))

            rows.append({
                "route_id": rid,
                "trip_ids_kept": "|".join(kept_ids) if kept_ids else "",
                "trip_ids_dropped": "|".join(dropped_ids) if dropped_ids else "",
                "trip_ids_added": "|".join(added_ids) if added_ids else "",
                "original_time": min_to_timestr(dep_min),
                "adjusted_time": min_to_timestr(dep_min + shift),
                "baseline_buses": base,
                "net_bus_change": add - allowed_drop
            })
    return rows

def write_plan_csv(rows, out_path):
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "route_id","original_time","adjusted_time","baseline_buses","net_bus_change",
            "trip_ids_kept","trip_ids_dropped","trip_ids_added"
        ])
        for r in rows:
            w.writerow([
                r["route_id"], r["original_time"], r["adjusted_time"], r["baseline_buses"], r["net_bus_change"],
                r["trip_ids_kept"], r["trip_ids_dropped"], r["trip_ids_added"]
            ])

def write_plan_txt_pretty(rows, out_path, title="Optimization Plan (per bus)"):
    by_route = defaultdict(list)
    for r in rows:
        by_route[r["route_id"]].append(r)

    def pad(s, w): return (s or "").ljust(w)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"{title}\n")
        f.write("=" * len(title) + "\n\n")
        for rid in sorted(by_route):
            f.write(f"Route {rid}\n")
            f.write("-" * (6 + len(rid)) + "\n")
            f.write(f"{pad('Trip ID(s)', 36)}  {pad('From', 6)} -> {pad('To', 6)}  {pad('Action', 10)}  {pad('Net', 5)}  {pad('Baseline', 8)}\n")
            f.write("-" * 92 + "\n")
            for r in by_route[rid]:
                kept_ids    = [x for x in (r['trip_ids_kept'] or '').split('|') if x]
                dropped_ids = [x for x in (r['trip_ids_dropped'] or '').split('|') if x]
                added_ids   = [x for x in (r['trip_ids_added'] or '').split('|') if x]
                action = "Shift" if r["original_time"] != r["adjusted_time"] else "Keep"
                if kept_ids:
                    f.write(f"{pad(', '.join(kept_ids), 36)}  {pad(r['original_time'], 6)} -> {pad(r['adjusted_time'], 6)}  {pad(action, 10)}  {pad(str(r['net_bus_change']), 5)}  {pad(str(r['baseline_buses']), 8)}\n")
                if dropped_ids:
                    f.write(f"{pad(', '.join(dropped_ids), 36)}  {pad(r['original_time'], 6)} -> {pad(r['original_time'], 6)}  {pad('Drop', 10)}  {pad(str(r['net_bus_change']), 5)}  {pad(str(r['baseline_buses']), 8)}\n")
                if added_ids:
                    f.write(f"{pad(', '.join(added_ids), 36)}  {pad(r['adjusted_time'], 6)} -> {pad(r['adjusted_time'], 6)}  {pad('Add', 10)}   {pad(str(r['net_bus_change']), 5)}  {pad(str(r['baseline_buses']), 8)}\n")
            f.write("\n")

# =========================
# Main
# =========================
def main():
    import argparse
    ap = argparse.ArgumentParser(description="Shift-first GA optimizer with capacity-aware drops and per-bus trip_id outputs")
    ap.add_argument("--schedule", default="schedule.csv")
    ap.add_argument("--plan_csv", default="plan.csv")
    ap.add_argument("--plan_txt", default="plan.txt")
    args = ap.parse_args()

    routes, departures, per_dep_ods, baseline_trip_ids = load_schedule(args.schedule)
    best, fit, info, proposed = run_ga(routes, departures, per_dep_ods)
    print(f"Best fitness={fit:.2f}, unmet={info['unmet']}, run={info['run_cost']:.1f}, add={info['add_cost']:.1f}")
    rows = build_plan_rows(proposed, routes, departures, per_dep_ods, baseline_trip_ids)
    write_plan_csv(rows, args.plan_csv)
    write_plan_txt_pretty(rows, args.plan_txt)
    print(f"Wrote {args.plan_csv} and {args.plan_txt}")

if __name__ == "__main__":
    main()
