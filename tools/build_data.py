#!/usr/bin/env python3
"""
build_data.py — ubah Strava bulk export (activities.csv + activities/)
menjadi data.json untuk Runfolio. Tidak butuh API, tidak butuh subscription.

Struktur input yang diharapkan:
    tools/strava_export/
    ├── activities.csv
    └── activities/
        ├── 1234567890.fit.gz
        ├── 1234567891.gpx
        └── ...

Cara pakai:
    python tools/build_data.py --input tools/strava_export
"""

import argparse
import csv
import gzip
import json
import math
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path

try:
    import gpxpy
except ImportError:
    gpxpy = None

try:
    from fitparse import FitFile
except ImportError:
    FitFile = None

TCX_NS = {"ns": "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"}
MAX_GAP_S = 90


# ---------- geometri & format ----------
def haversine(lat1, lon1, lat2, lon2):
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def fmt_duration(seconds):
    seconds = int(round(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def fmt_human_time(seconds):
    seconds = int(round(seconds))
    h, rem = divmod(seconds, 3600)
    m = rem // 60
    if h:
        return f"{h}h {m}m"
    return f"{m}m"


def fmt_pace(sec_per_km):
    if sec_per_km <= 0:
        return "—"
    m = int(sec_per_km // 60)
    s = int(round(sec_per_km % 60))
    if s == 60:
        m += 1
        s = 0
    return f"{m}:{s:02d}"


def fmt_month_short(iso_month):
    try:
        d = datetime.strptime(iso_month, "%Y-%m")
    except ValueError:
        return iso_month
    return d.strftime("%b %Y").replace("May", "Mei").replace("Aug", "Agu")


def fmt_month_abbr(iso_month):
    try:
        d = datetime.strptime(iso_month, "%Y-%m")
    except ValueError:
        return iso_month
    return d.strftime("%b").replace("May", "Mei").replace("Aug", "Agu")


def fmt_week_label(iso_week_start):
    try:
        d = datetime.strptime(iso_week_start, "%Y-%m-%d")
    except ValueError:
        return iso_week_start
    return d.strftime("%b %d, %Y").replace("May", "Mei").replace("Aug", "Agu")


def infer_category(km):
    if km < 6:
        return "5K"
    if km < 12:
        return "10K"
    if km < 19:
        return "17K"
    return "HM 21.1K"


def parse_strava_date(s):
    """Tanggal dari CSV Strava: 'Jun 15, 2025, 6:30:00 AM'"""
    if not s:
        return None
    s = s.strip()
    for fmt in (
        "%b %d, %Y, %I:%M:%S %p",
        "%b %d, %Y %I:%M:%S %p",
        "%b %d, %Y, %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
        "%m/%d/%Y %H:%M:%S",
    ):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def safe_float(value, default=0.0):
    try:
        v = float(str(value).replace(",", "").strip())
        return v if math.isfinite(v) else default
    except (ValueError, AttributeError):
        return default


def safe_int(value, default=0):
    try:
        return int(float(str(value).replace(",", "").strip()))
    except (ValueError, AttributeError):
        return default


def get_col(row, *names):
    for n in names:
        if n in row and row[n] not in (None, ""):
            return row[n]
    return ""


# ---------- file readers ----------
def read_fit(path):
    if FitFile is None:
        raise RuntimeError("fitparse belum terpasang: pip install fitparse")

    if str(path).endswith(".gz"):
        with gzip.open(path, "rb") as f:
            data = f.read()
        fit = FitFile(BytesIO(data))
    else:
        fit = FitFile(str(path))

    samples = []
    for record in fit.get_messages("record"):
        rec = {d.name: d.value for d in record}
        lat = rec.get("position_lat")
        lng = rec.get("position_long")
        if lat is None or lng is None:
            continue
        # FIT menyimpan posisi dalam semicircles
        lat = float(lat) * (180.0 / 2**31)
        lng = float(lng) * (180.0 / 2**31)
        t = rec.get("timestamp")
        ele = rec.get("enhanced_altitude")
        if ele is None:
            ele = rec.get("altitude")
        samples.append((lat, lng, t, float(ele) if ele is not None else None))
    return samples


def read_gpx(path):
    if gpxpy is None:
        raise RuntimeError("gpxpy belum terpasang: pip install gpxpy")
    if str(path).endswith(".gz"):
        with gzip.open(path, "rb") as f:
            content = f.read().decode("utf-8", errors="ignore")
        gpx = gpxpy.parse(content)
    else:
        with open(path, "r", encoding="utf-8") as f:
            gpx = gpxpy.parse(f)

    samples = []
    for track in gpx.tracks:
        for seg in track.segments:
            for pt in seg.points:
                t = pt.time
                if t and t.tzinfo is not None:
                    t = t.astimezone(timezone.utc).replace(tzinfo=None)
                ele = pt.elevation
                samples.append((pt.latitude, pt.longitude, t, ele))
    return samples


def read_tcx(path):
    tree = ET.parse(path)
    root = tree.getroot()
    activity = root.find(".//ns:Activity", TCX_NS)
    if activity is None:
        return []

    samples = []
    for tp in activity.findall(".//ns:Trackpoint", TCX_NS):
        lat_el = tp.find("ns:Position/ns:LatitudeDegrees", TCX_NS)
        lon_el = tp.find("ns:Position/ns:LongitudeDegrees", TCX_NS)
        if lat_el is None or lon_el is None:
            continue

        t = None
        t_el = tp.find("ns:Time", TCX_NS)
        if t_el is not None and t_el.text:
            try:
                t = datetime.fromisoformat(t_el.text.replace("Z", "+00:00"))
                if t.tzinfo is not None:
                    t = t.astimezone(timezone.utc).replace(tzinfo=None)
            except ValueError:
                t = None

        ele = None
        ele_el = tp.find("ns:AltitudeMeters", TCX_NS)
        if ele_el is not None and ele_el.text:
            try:
                ele = float(ele_el.text)
            except ValueError:
                ele = None

        samples.append((float(lat_el.text), float(lon_el.text), t, ele))
    return samples


def load_samples(path):
    """Dispatch berdasarkan ekstensi."""
    name = str(path).lower()
    try:
        if name.endswith(".fit.gz") or name.endswith(".fit"):
            return read_fit(path)
        if name.endswith(".gpx.gz") or name.endswith(".gpx"):
            return read_gpx(path)
        if name.endswith(".tcx"):
            return read_tcx(path)
    except Exception as e:
        print(f"    ! gagal parse {path.name}: {e}")
    return []


# ---------- hitung turunan ----------
def normalize_times(samples):
    """Ubah ke list (lat, lng, t_rel_sec, ele) — t_rel dari sample pertama yang punya waktu."""
    ref = None
    for s in samples:
        if s[2] is not None:
            ref = s[2]
            break
    if ref is None:
        return [(s[0], s[1], None, s[3]) for s in samples]
    return [
        (s[0], s[1], (s[2] - ref).total_seconds() if s[2] is not None else None, s[3])
        for s in samples
    ]


def compute_cumulative(samples):
    cum = [0.0]
    for i in range(1, len(samples)):
        t0, t1 = samples[i - 1][2], samples[i][2]
        if t0 is not None and t1 is not None and (t1 - t0) > MAX_GAP_S:
            cum.append(cum[-1])
        else:
            cum.append(cum[-1] + haversine(*samples[i - 1][:2], *samples[i][:2]))
    return cum


def downsample_route(samples, target=200):
    if len(samples) <= target:
        return [[round(s[0], 6), round(s[1], 6)] for s in samples]
    step = len(samples) / target
    idx = [int(i * step) for i in range(target)] + [len(samples) - 1]
    return [[round(samples[i][0], 6), round(samples[i][1], 6)] for i in idx]


def compute_splits(samples, cum, moving_s, n_chunks):
    """Bagi jarak total menjadi n_chunks, hitung waktu per chunk."""
    total = cum[-1]
    if total <= 0 or n_chunks < 1 or moving_s <= 0:
        return []

    # waktu di setiap index, diskalakan agar total = moving_s
    sample_times = [s[2] if s[2] is not None else 0.0 for s in samples]
    raw_total = sample_times[-1] - sample_times[0] if sample_times else 0
    if raw_total <= 0:
        return []

    scale = moving_s / raw_total

    splits = []
    for c in range(n_chunks):
        d0 = total * c / n_chunks
        d1 = total * (c + 1) / n_chunks
        i0 = next((i for i, d in enumerate(cum) if d >= d0), len(cum) - 1)
        i1 = next((i for i, d in enumerate(cum) if d >= d1), len(cum) - 1)
        dt = (sample_times[i1] - sample_times[i0]) * scale
        dd = cum[i1] - cum[i0]
        if dt > 0 and dd > 0:
            splits.append(int(round(dt / (dd / 1000.0))))
        else:
            splits.append(0)
    return splits


def extract_elevation_profile(samples, cum, target=120):
    if len(samples) < 2:
        return None

    raw = [s[3] for s in samples]
    valid = [e for e in raw if e is not None]
    if not valid or len(valid) < len(raw) * 0.3:
        return None

    for i in range(1, len(raw)):
        if raw[i] is None:
            raw[i] = raw[i - 1]
    for i in range(len(raw) - 2, -1, -1):
        if raw[i] is None:
            raw[i] = raw[i + 1]

    total = cum[-1]
    if total <= 0:
        return None

    profile = []
    for i in range(target):
        d = total * i / (target - 1)
        idx = next((j for j, dd in enumerate(cum) if dd >= d), len(cum) - 1)
        profile.append(round(raw[idx], 1))

    gain = sum(max(0, profile[i] - profile[i - 1]) for i in range(1, len(profile)))

    return {
        "min": round(min(profile), 1),
        "max": round(max(profile), 1),
        "gain": round(gain),
        "profile": profile,
    }


# ---------- resolusi file di folder activities/ ----------
def resolve_activity_file(csv_row, base_dir):
    filename = get_col(csv_row, "Filename", "FileName")
    if filename:
        p = base_dir / filename
        if p.exists():
            return p
        p = base_dir / "activities" / Path(filename).name
        if p.exists():
            return p

    activity_id = str(get_col(csv_row, "Activity ID", "ActivityId")).strip()
    if activity_id:
        for ext in (".fit.gz", ".fit", ".gpx.gz", ".gpx", ".tcx"):
            p = base_dir / "activities" / f"{activity_id}{ext}"
            if p.exists():
                return p
    return None


# ---------- bangun satu run ----------
RUN_TYPES = {"Run", "Trail Run", "TrailRun", "Virtual Run", "VirtualRun", "Running"}

# field yang akan dianggap race (untuk ekstrak route + splits)
def should_extract_route(run, all_races_ids, longest_id):
    return run["is_race"] or run["id"] == longest_id


def build_run_from_row(row, base_dir, config, want_route, want_elevation):
    activity_type = get_col(row, "Activity Type", "ActivityType").strip()
    if activity_type not in RUN_TYPES:
        return None

    activity_id = str(get_col(row, "Activity ID", "ActivityId")).strip()
    if not activity_id:
        return None

    override = config.get("activities", {}).get(activity_id, {})

    # ---- metadata dari CSV ----
    date = parse_strava_date(get_col(row, "Activity Date", "ActivityDate"))
    distance_m = safe_float(get_col(row, "Distance", "Distance.1"))
    if distance_m <= 0:
        return None

    moving_s = safe_int(get_col(row, "Moving Time", "MovingTime"))
    elapsed_s = safe_int(get_col(row, "Elapsed Time", "ElapsedTime"))
    if moving_s <= 0:
        moving_s = elapsed_s if elapsed_s > 0 else 0
    if moving_s <= 0:
        return None

    dist_km = distance_m / 1000.0
    pace_s = moving_s / dist_km if dist_km > 0 else 0

    name = override.get("name") or get_col(row, "Activity Name", "ActivityName").strip() or "Untitled Run"
    description = override.get("description") or get_col(row, "Activity Description", "ActivityDescription").strip()
    is_race = bool(override.get("is_race", False))
    category = override.get("category") or infer_category(dist_km)

    run = {
        "id": activity_id,
        "name": name,
        "iso_date": date.isoformat() if date else "",
        "date": date.strftime("%b %Y").replace("May", "Mei").replace("Aug", "Agu") if date else "",
        "distance_km": round(dist_km, 2),
        "time_seconds": int(moving_s),
        "time": fmt_duration(moving_s),
        "pace": fmt_pace(pace_s),
        "category": category,
        "is_race": is_race,
        "badge": override.get("badge", "Race" if is_race else "Training"),
        "location": override.get("location", ""),
        "description": description,
    }

    # elevation gain dari CSV — fallback kalau file tidak ada
    csv_elev_gain = safe_float(get_col(row, "Elevation Gain", "ElevationGain"))
    csv_elev_loss = safe_float(get_col(row, "Elevation Loss", "ElevationLoss"))
    csv_elev_low = safe_float(get_col(row, "Elevation Low", "ElevationLow"))
    csv_elev_high = safe_float(get_col(row, "Elevation High", "ElevationHigh"))

    # ---- route + splits + elevation dari file, kalau perlu ----
    if want_route or want_elevation:
        path = resolve_activity_file(row, base_dir)
        if path:
            samples = load_samples(path)
            if len(samples) >= 2:
                samples = normalize_times(samples)
                cum = compute_cumulative(samples)

                if want_route:
                    run["route"] = downsample_route(samples, target=200)
                    n_chunks = max(1, int(round(dist_km)))
                    run["splits"] = compute_splits(samples, cum, moving_s, n_chunks)

                if want_elevation:
                    elev = extract_elevation_profile(samples, cum, target=120)
                    if elev:
                        run["elevation"] = elev

    # fallback elevation dari CSV (kalau belum ada dari file)
    if want_elevation and "elevation" not in run and csv_elev_gain > 0:
        run["elevation"] = {
            "min": round(csv_elev_low, 1),
            "max": round(csv_elev_high, 1),
            "gain": round(csv_elev_gain),
            "profile": None,
            "source": "csv",
        }

    return run


# ---------- agregat ----------
def fill_monthly_gaps(monthly):
    if not monthly:
        return []
    existing = {m["month"]: m for m in monthly}
    first = datetime.strptime(monthly[0]["month"], "%Y-%m")
    last = datetime.strptime(monthly[-1]["month"], "%Y-%m")
    result = []
    cursor = first
    while cursor <= last:
        key = cursor.strftime("%Y-%m")
        result.append(existing.get(key, {"month": key, "km": 0, "runs": 0}))
        cursor = (cursor.replace(day=1) + timedelta(days=32)).replace(day=1)
    return result


def compute_aggregates(runs):
    total_km = sum(r["distance_km"] for r in runs)
    total_time = sum(r["time_seconds"] for r in runs)

    monthly_map = {}
    weekly_map = {}
    for r in runs:
        iso = r.get("iso_date", "")
        if not iso:
            continue
        try:
            d = datetime.fromisoformat(iso)
        except ValueError:
            continue

        mkey = d.strftime("%Y-%m")
        monthly_map.setdefault(mkey, {"km": 0.0, "runs": 0})
        monthly_map[mkey]["km"] += r["distance_km"]
        monthly_map[mkey]["runs"] += 1

        week_start = (d - timedelta(days=d.weekday())).date().isoformat()
        weekly_map.setdefault(week_start, {"km": 0.0, "runs": 0})
        weekly_map[week_start]["km"] += r["distance_km"]
        weekly_map[week_start]["runs"] += 1

    monthly = [
        {"month": k, "label": fmt_month_short(k), "abbr": fmt_month_abbr(k),
         "km": round(v["km"], 1), "runs": v["runs"]}
        for k, v in sorted(monthly_map.items())
    ]
    monthly = fill_monthly_gaps(monthly)

    best_week = None
    if weekly_map:
        wk_start, wk = max(weekly_map.items(), key=lambda kv: kv[1]["km"])
        best_week = {
            "week": wk_start,
            "label": fmt_week_label(wk_start),
            "km": round(wk["km"], 1),
            "runs": wk["runs"],
        }

    most_active_month = None
    if monthly:
        best = max(monthly, key=lambda m: m["km"])
        if best["km"] > 0:
            most_active_month = {
                "month": best["month"],
                "label": best["label"],
                "km": best["km"],
                "runs": best["runs"],
            }

    avg_runs_per_week = (
        round(sum(w["runs"] for w in weekly_map.values()) / len(weekly_map), 1)
        if weekly_map else 0
    )

    return {
        "total_km": round(total_km, 1),
        "total_time_seconds": total_time,
        "total_time": fmt_human_time(total_time),
        "avg_pace": fmt_pace(total_time / total_km) if total_km > 0 else "—",
        "monthly": monthly,
        "best_week": best_week,
        "most_active_month": most_active_month,
        "avg_runs_per_week": avg_runs_per_week,
    }


def compute_heatmap(runs, months=12):
    if not runs:
        return None

    dates = []
    for r in runs:
        try:
            dates.append(datetime.fromisoformat(r["iso_date"]).date())
        except (ValueError, TypeError):
            continue
    if not dates:
        return None

    end = max(dates)
    end = end + timedelta(days=(6 - end.weekday()) % 7)
    start_target = end - timedelta(days=months * 30)
    start = start_target - timedelta(days=start_target.weekday())

    daily = {}
    for r in runs:
        try:
            d = datetime.fromisoformat(r["iso_date"]).date()
        except (ValueError, TypeError):
            continue
        if d < start or d > end:
            continue
        key = d.isoformat()
        daily.setdefault(key, {"km": 0.0, "runs": 0})
        daily[key]["km"] += r["distance_km"]
        daily[key]["runs"] += 1

    days = []
    cursor = start
    while cursor <= end:
        key = cursor.isoformat()
        entry = daily.get(key, {"km": 0.0, "runs": 0})
        days.append({"date": key, "km": round(entry["km"], 1), "runs": entry["runs"]})
        cursor += timedelta(days=1)

    total_km = sum(d["km"] for d in days)
    total_runs = sum(d["runs"] for d in days)

    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "total_km": round(total_km, 1),
        "total_runs": total_runs,
        "days": days,
    }


# ---------- finalisasi ----------
def finalize(runs):
    races = [r for r in runs if r.get("is_race")]

    best_by_cat = {}
    for r in races:
        cat = r["category"]
        if cat not in best_by_cat or r["time_seconds"] < best_by_cat[cat]["time_seconds"]:
            best_by_cat[cat] = r
    for r in races:
        r["pb"] = best_by_cat.get(r["category"]) is r

    sorted_runs = sorted(runs, key=lambda r: r.get("iso_date") or "", reverse=True)
    recent = [
        {
            "id": r["id"],
            "name": r["name"],
            "iso_date": r["iso_date"],
            "date": r["date"],
            "distance_km": r["distance_km"],
            "time": r["time"],
            "pace": r["pace"],
            "category": r["category"],
            "is_race": r["is_race"],
            "badge": r["badge"],
        }
        for r in sorted_runs[:10]
    ]

    aggregates = compute_aggregates(runs)
    heatmap = compute_heatmap(runs, months=12)

    best_5k = best_by_cat.get("5K")
    best_10k = best_by_cat.get("10K")
    best_hm = best_by_cat.get("HM 21.1K")
    longest = max(runs, key=lambda r: r["distance_km"]) if runs else None

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_runs": len(runs),
            "total_races": len(races),
            "total_km": aggregates["total_km"],
            "total_time": aggregates["total_time"],
            "avg_pace": aggregates["avg_pace"],
            "best_5k": {"time": best_5k["time"], "name": best_5k["name"]} if best_5k else None,
            "best_10k": {"time": best_10k["time"], "name": best_10k["name"]} if best_10k else None,
            "best_hm": {
                "time": best_hm["time"],
                "name": best_hm["name"],
                "date": best_hm["date"],
                "distance_km": best_hm["distance_km"],
                "splits": best_hm.get("splits", []),
                "route": best_hm.get("route", []),
                "elevation": best_hm.get("elevation"),
            } if best_hm else None,
            "longest_run": {
                "name": longest["name"],
                "distance_km": longest["distance_km"],
                "time": longest["time"],
                "iso_date": longest["iso_date"],
                "date": longest["date"],
                "route": longest.get("route", []),
                "elevation": longest.get("elevation"),
            } if longest else None,
            "most_active_month": aggregates["most_active_month"],
            "best_week": aggregates["best_week"],
            "avg_runs_per_week": aggregates["avg_runs_per_week"],
        },
        "monthly": aggregates["monthly"],
        "heatmap": heatmap,
        "recent_runs": recent,
        "races": sorted(races, key=lambda r: r.get("iso_date") or ""),
        "runs": sorted(runs, key=lambda r: r.get("iso_date") or ""),
    }


# ---------- main ----------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="tools/strava_export",
                        help="folder hasil extract archive Strava (berisi activities.csv)")
    parser.add_argument("--output", default="data.json")
    parser.add_argument("--config", default="tools/config.json")
    args = parser.parse_args()

    base_dir = Path(args.input)
    csv_path = base_dir / "activities.csv"

    if not base_dir.exists():
        print(f"Folder tidak ditemukan: {base_dir}", file=sys.stderr)
        sys.exit(1)
    if not csv_path.exists():
        print(f"activities.csv tidak ditemukan di {base_dir}", file=sys.stderr)
        print("Pastikan --input menunjuk ke folder hasil extract archive Strava.", file=sys.stderr)
        sys.exit(1)

    config = {}
    config_path = Path(args.config)
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)

    print(f"Membaca {csv_path} ...")
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    print(f"  {len(rows)} baris di CSV")

    # pass 1: filter run, ambil metadata dasar, cari race dan longest
    candidates = []
    for row in rows:
        activity_type = get_col(row, "Activity Type", "ActivityType").strip()
        if activity_type not in RUN_TYPES:
            continue
        activity_id = str(get_col(row, "Activity ID", "ActivityId")).strip()
        if not activity_id:
            continue

        override = config.get("activities", {}).get(activity_id, {})
        is_race = bool(override.get("is_race", False))

        distance_m = safe_float(get_col(row, "Distance", "Distance.1"))
        if distance_m <= 0:
            continue

        candidates.append({
            "row": row,
            "id": activity_id,
            "is_race": is_race,
            "distance_m": distance_m,
        })

    longest_id = None
    if candidates:
        longest = max(candidates, key=lambda c: c["distance_m"])
        longest_id = longest["id"]

    race_ids = {c["id"] for c in candidates if c["is_race"]}

    print(f"  {len(candidates)} run · {len(race_ids)} race · longest: {longest_id}")

    # pass 2: build runs
    runs = []
    for i, c in enumerate(candidates, 1):
        want_route = c["id"] in race_ids or c["id"] == longest_id
        want_elevation = c["id"] in race_ids or c["id"] == longest_id

        run = build_run_from_row(
            c["row"], base_dir, config,
            want_route=want_route,
            want_elevation=want_elevation,
        )
        if run:
            runs.append(run)
            if want_route or want_elevation:
                extras = []
                if run.get("route"):
                    extras.append(f"route:{len(run['route'])}pts")
                if run.get("splits"):
                    extras.append(f"splits:{len(run['splits'])}")
                if run.get("elevation"):
                    extras.append("elev")
                if extras:
                    print(f"  [{i}/{len(candidates)}] {run['name']}: {', '.join(extras)}")

    if not runs:
        print("Tidak ada run yang valid.", file=sys.stderr)
        sys.exit(1)

    data = finalize(runs)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))

    s = data["summary"]
    print(f"\n✓ {s['total_runs']} runs → {args.output}")
    print(f"  {s['total_km']} km · {s['total_time']} · avg {s['avg_pace']}/km")
    print(f"  {s['total_races']} races")
    if s["best_5k"]:
        print(f"  5K PB: {s['best_5k']['time']}")
    if s["best_hm"]:
        print(f"  HM PB: {s['best_hm']['time']}")
    if data.get("heatmap"):
        print(f"  heatmap: {data['heatmap']['total_runs']} runs, {data['heatmap']['total_km']} km")


if __name__ == "__main__":
    main()