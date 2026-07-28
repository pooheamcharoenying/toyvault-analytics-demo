"""Seed a FICTIONAL planogram ("Master Con") into Mongo from the demo data's velocity.

The real Master Con PAR sheet is private, so we fabricate plausible shelf minimums:
for the top store locations, each of its fastest-moving SKUs gets a min_qty of roughly
one month of its recent velocity. This makes the planogram grid + refill views look
populated in the demo without any real planogram data.

Run from backend/:
    python seed_planogram.py "<path to ToyVault Demo Data (YYYYMMDD).xlsx>" [--dry-run]

--dry-run computes and prints what it WOULD seed without touching Mongo (no creds needed).
A real run requires Mongo configured (MONGODB_URI in backend/.env).
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

TOP_LOCATIONS = 25      # number of store locations to give a planogram
TOP_SKUS = 40           # SKUs per location (the shelf face)
VEL_MONTHS = 1.0        # min_qty ~ this many months of recent velocity
MIN_QTY_CAP = 24        # never shelf more than this per SKU
WAREHOUSE_HINTS = ("warehouse", "stock area", "dem", "demo", "credit")


def _is_store(name: str) -> bool:
    n = (name or "").lower()
    return not any(h in n for h in WAREHOUSE_HINTS)


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry-run" in sys.argv
    if not args or not os.path.exists(args[0]):
        print("Usage: python seed_planogram.py <demo_data.xlsx> [--dry-run]")
        return 1
    xlsx = args[0]

    from app.utils import digital_ocean_functions as dof
    from app.utils import helper_functions as hf
    from app.utils import location_analytics as la
    from app.utils import nichi_stock as nstk
    from app.utils.location_consolidation import add_consolidated_column
    import pandas as pd

    if not dry:
        from app.utils import mongo_store as ms
        if not ms.is_enabled():
            print("ERROR: Mongo not configured (set MONGODB_URI in backend/.env), or use --dry-run.")
            return 1

    print(f"Parsing {xlsx} ...")
    dfs = dof._parse_excel_bytes(open(xlsx, "rb").read())
    fname = os.path.basename(xlsx)
    hf.GLOBAL_DF = {"filename": fname, "filedate": hf.extract_date_from_filename(fname), **dfs}

    df_whs = dfs["whs_code"][["WhsCode", "WhsName"]].copy()
    df_whs["WhsCode"] = df_whs["WhsCode"].astype(str).str.strip()
    lookup = dict(zip(df_whs["WhsCode"], df_whs["WhsName"].astype(str)))

    # --- rank consolidated STORE locations by revenue ---
    df_sale, _, _ = nstk.prepare_sales_and_onhand_data(dfs["sale"], dfs["onhand"], dfs["master"])
    sale = la._channel_dedup_sale(df_sale)
    sale["WhsCode"] = sale["WhsCode"].astype(str).str.strip()
    sale = add_consolidated_column(sale, lookup)
    rev = sale.groupby("ConsolidatedLocation")["LineTotal"].sum().sort_values(ascending=False)
    stores = [loc for loc in rev.index if _is_store(str(loc))][:TOP_LOCATIONS]
    print(f"Selected {len(stores)} store locations (of {len(rev)} consolidated) for planograms.")

    # helpers from the planogram route (reuse the exact velocity + whs resolution)
    from app.api.routes.planogram import _velocity_and_recent_months, _resolve_location_whs

    seeded = 0
    total_cells = 0
    for order, location in enumerate(stores, start=1):
        extra = _velocity_and_recent_months(location, window_days=90, months_range="3m")
        by_item = extra["by_item"]
        # top SKUs by monthly velocity at this location
        ranked = sorted(by_item.items(), key=lambda kv: -kv[1].get("velocity", 0.0))
        items = {}
        for code, ex in ranked[:TOP_SKUS]:
            vel = float(ex.get("velocity", 0.0))
            if vel <= 0:
                continue
            items[str(code)] = int(min(MIN_QTY_CAP, max(1, round(vel * VEL_MONTHS))))
        if not items:
            continue

        whs = _resolve_location_whs(location)
        total_cells += len(items)
        if dry:
            sample = list(items.items())[:3]
            print(f"  [{order:2d}] {location:28s} SKUs={len(items):3d}  primary={whs.get('default_primary')}  e.g. {sample}")
        else:
            from app.utils import planogram_par as pp
            pp.replace_location(
                location, items,
                whs_codes=whs["whs_codes"] or None,
                primary_whs_code=whs["default_primary"],
                primary_source="heterogeneous" if whs.get("heterogeneous") else "base_prefix",
                source="demo-seed",
                meta={"order": order, "channel": None, "grade": None},
            )
            seeded += 1

    if dry:
        print(f"\nDRY RUN: would seed {len(stores)} locations, {total_cells} SKU-minimums total. No Mongo writes.")
    else:
        print(f"\nSeeded {seeded} location planograms ({total_cells} SKU-minimums) into '{ms.get_db_name()}'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
