"""Generate location consolidation mapping JSON.

Consolidates multiple WhsCodes for the same physical retail location
into a single display name. E.g., CT-ลาดพร้าว GP25, GP33, GP25 Art Toy
all become "CT-ลาดพร้าว".

The mapping is saved to app/data/location_consolidation.json
"""
import pandas as pd
import os
import sys
import json
import re
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")

cache_dir = ".excel_cache"
files = [f for f in os.listdir(cache_dir) if f.endswith(".xlsx")]
path = os.path.join(cache_dir, files[0])

df_whs = pd.read_excel(path, sheet_name="Whs Code")
df_sale = pd.read_excel(path, sheet_name="Sale")
df_oh = pd.read_excel(path, sheet_name="OnHand")

# Get active codes
sale_codes = set(df_sale["WhsCode"].astype(str).unique())
oh_codes = set(df_oh["WhsCode"].astype(str).unique())
active_codes = sale_codes | oh_codes

whs_lookup = dict(zip(df_whs["WhsCode"].astype(str), df_whs["WhsName"].astype(str)))


def clean_branch_name(name):
    """Strip GP rate, tier, Art Toy, promo suffixes to get the physical location."""
    branch = name
    # Remove GP commission rates: GP25, GP30%, GP33, GP12%, GP18%, GP20%, GP25%, GP32%, GP35%, GP36%
    branch = re.sub(r"\s*\(?\s*GP\d+%?\s*\)?", "", branch)
    # Remove tier indicators: T1, T2, T2_
    branch = re.sub(r"\s+T[12]_?\s*", " ", branch)
    # Remove (Art Toy)
    branch = re.sub(r"\s*\(Art Toy\)", "", branch)
    # Remove ราคาปกติ / ราคาโปร
    branch = re.sub(r"\s*\(ราคาปกติ\)", "", branch)
    branch = re.sub(r"\s*\(ราคาโปร\)", "", branch)
    branch = re.sub(r"\s*ราคาโปร", "", branch)
    # Remove discount info: ส่วนลด 31-50%
    branch = re.sub(r"\s*ส่วนลด\s*\d+-\d+%", "", branch)
    # Remove +2% M Online
    branch = re.sub(r"\s*\+\d+%\s*M\s*Online", "", branch)
    # Remove store numbers like (1932)
    branch = re.sub(r"\s*\(\d+\)\s*", " ", branch)
    # Remove contract dates: _เริ่ม ... / เริ่ม ...
    branch = re.sub(r"_เริ่ม\s*\d+.*$", "", branch)
    branch = re.sub(r"\s*เริ่ม\s*\d+.*$", "", branch)
    # Remove event dates: _dd/mm - dd/mm/yy
    branch = re.sub(r"_\d+\s*/\s*\d+.*$", "", branch)
    # Remove T2_ prefix on outlet codes
    branch = re.sub(r"\s*T2_?\s*\(?[A-Z]*\)?\s*", " ", branch)
    # Remove Pro_ suffixes and everything after them
    branch = re.sub(r"\s*Pro_.*$", "", branch)
    branch = re.sub(r"\s*Pro\s+.*$", "", branch)
    # Remove โอนตามยอดขาย and similar trailing text
    branch = re.sub(r"\s*โอนตามยอดขาย.*$", "", branch)
    # Remove ออก IVN ... or ออก IV ...
    branch = re.sub(r"\s*ออก\s+IV[N]?\s+.*$", "", branch)
    # Remove สัญญา / สัณญา (contract info)
    branch = re.sub(r"\s*สั[ญณ]ญา.*$", "", branch)
    # Remove ต่อถึง (extended to)
    branch = re.sub(r"\s*ต่อถึง.*$", "", branch)
    # Clean up whitespace
    branch = re.sub(r"\s+", " ", branch).strip()
    # Remove trailing underscores, hyphens, spaces
    branch = branch.rstrip("_- ").strip()
    return branch


mapping = {}

for code in sorted(active_codes):
    name = whs_lookup.get(code, code)
    consolidated = None

    # === CENTRAL branches (CT-) ===
    if name.startswith("CT-") or code.startswith("CCT"):
        branch = clean_branch_name(name)
        if "ออนไลน์" in branch or "Online" in branch:
            consolidated = "CT-Central Online"
        else:
            consolidated = branch

    # === ROBINSON branches (RO-) ===
    elif name.startswith("RO-") or name.startswith("RO -") or code.startswith("CRB"):
        branch = clean_branch_name(name)
        if "ออนไลน์" in branch or "Online" in branch:
            consolidated = "RO-Robinson Online"
        else:
            consolidated = branch

    # === THE MALL branches (M-) ===
    elif name.startswith("M-") or code.startswith("CTM"):
        branch = clean_branch_name(name)
        # Remove Pro_ prefix if it leaked through
        branch = re.sub(r"^Pro_", "", branch)
        consolidated = branch

    # === OUTLET MALL ===
    elif name.startswith("Outlet Mall") or code.startswith("COL"):
        branch = clean_branch_name(name)
        consolidated = branch

    # === KING POWER ===
    elif "KING POWER" in name.upper() or "คิง เพาเวอร์" in name or code.startswith("CKP"):
        consolidated = "King Power"

    # === B2S ===
    elif name.startswith("B2S") or code.startswith("CB2"):
        consolidated = "B2S"

    # === SIAM TAKASHIMAYA ===
    elif "ทาคาชิมาย่า" in name or "Takashimaya" in name.lower() or code.startswith("CSMT"):
        consolidated = "Siam Takashimaya"

    # === TOYS R US (TRU) ===
    elif name.startswith("TRU ") or name.startswith("TRU_") or code.startswith("CTU"):
        branch = clean_branch_name(name)
        consolidated = branch

    # === SHOPS (Nichiworld standalone) ===
    elif name.startswith("Shop") or name.startswith("Shop_"):
        branch = clean_branch_name(name)
        consolidated = branch

    # === D1 = Main Warehouse (also used for events/WH sale) ===
    elif code == "D1":
        consolidated = "Main Warehouse (D1)"

    # === D1-SL = Online (Shopee + Lazada) ===
    elif code == "D1-SL":
        consolidated = "Online (Shopee + Lazada)"

    # === D1-DEM = Demo ===
    elif code == "D1-DEM":
        consolidated = "Demo Stock"

    elif code == "D1-2":
        consolidated = "Secondary Warehouse (D1-2)"

    elif code == "D2":
        consolidated = "Warehouse D2"

    elif code == "D8":
        consolidated = "Team Stock (Shop & Events)"

    elif code == "D10":
        consolidated = "Warehouse D10"

    # === HOSPITALS (ร.พ.) ===
    elif "ร.พ." in name or "รพ." in name or "โรงพยาบา" in name or code.startswith("CBB"):
        branch = clean_branch_name(name)
        consolidated = branch

    # === 7-ELEVEN ===
    elif "เซเว่น" in name or code.startswith("CSV"):
        consolidated = "7-Eleven"

    # === ASIA BOOKS ===
    elif "เอเซียบุ๊คส" in name or code.startswith("CA7H"):
        consolidated = "Asia Books"

    # === SE-ED (ซีเอ็ด) ===
    elif "ซีเอ็ดยูเคชั่น" in name or code.startswith("CSEED"):
        consolidated = "SE-ED Education"

    # === CPN ===
    elif "เซ็นทรัลพัฒนา" in name or code.startswith("CCPS"):
        branch = clean_branch_name(name)
        consolidated = branch

    # === Default: keep as-is ===
    else:
        consolidated = name

    if consolidated:
        mapping[code] = consolidated

# Show results
groups = defaultdict(list)
for code, cons in mapping.items():
    groups[cons].append(code)

print(f"Total active codes: {len(active_codes)}")
print(f"Consolidated into: {len(groups)} unique locations")
print()

# Show groups with >1 code (consolidated locations)
multi = {k: v for k, v in groups.items() if len(v) > 1}
print(f"Groups with multiple codes (consolidated): {len(multi)}")
for cons, codes in sorted(multi.items(), key=lambda x: -len(x[1])):
    print(f"  {len(codes):3d} codes -> {cons}")
    for c in sorted(codes):
        print(f"               {c:15s} = {whs_lookup.get(c, '???')}")

# Save mapping
os.makedirs("app/data", exist_ok=True)
output_path = "app/data/location_consolidation.json"
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(mapping, f, ensure_ascii=False, indent=2)
print(f"\nSaved mapping to {output_path}")
