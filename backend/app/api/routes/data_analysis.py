import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

from app.utils import helper_functions as hf
from app.utils import nichi_stock as nstk
from app.utils import executive_helpers as exr
from app.utils import inventory_alerts as ialerts
from app.utils import product_sale_onhand as pso
from app.utils import product_analytics as pa
from app.utils import location_analytics as la
from app.utils import purchase_analytics as pua
from app.utils import seasonality_margin as sm
from app.utils import stock_allocation as sal
from app.utils import period_comparison as pc
from app.utils import actions_engine as ae
from app.utils import item_detail as idet
from app.utils import recommendation_engine as reng
from app.utils import channel_analytics as cha
from app.utils import data_quality as dq
from app.utils.analytics_helpers import dataframe_split_json_response
from app.utils.cache import cached_call

router = APIRouter()


def _data_not_ready():
    return JSONResponse({"message": "data not ready"}, status_code=503)

@router.get("/data/status", summary="Check background load status")
def data_status():
    logger.debug("hf status: %s", hf.LOAD_STATUS)
    return JSONResponse(hf.LOAD_STATUS, status_code=200)  # <-- helpers
    # return {"message": "api/routes is wired correctly"}

@router.get("/df")
async def get_df():  # <-- renamed to avoid duplicate function name

    # use the GLOBAL_DF from helper_functions
    payload = {
        "filename": hf.GLOBAL_DF.get("filename"),
        "filedate": hf.GLOBAL_DF.get("filedate"),
        "sale":   hf.df_to_jsonable_head(hf.GLOBAL_DF.get("sale")),
        "onhand": hf.df_to_jsonable_head(hf.GLOBAL_DF.get("onhand")),
        "master": hf.df_to_jsonable_head(hf.GLOBAL_DF.get("master")),
        "grpo_detail": hf.df_to_jsonable_head(hf.GLOBAL_DF.get("grpo_detail")),
        "whs_code": hf.df_to_jsonable_head(hf.GLOBAL_DF.get("whs_code")),
    }
    return JSONResponse(content=jsonable_encoder(payload))

@router.get("/data/file_date", summary="Extract date from filename")
def extract_date_from_filename():
    """
    Extracts the date from the filename following the pattern: (YYYY-MM-DD) or (YYYYMMDD)
    
    Returns:
        JSON response with:
        - filename: original filename
        - extracted_date: date in YYYY-MM-DD format if found
        - date_found: boolean indicating if date was extracted
        - error: error message if any
    """
    try:
        filename = hf.LOAD_STATUS.get("filename")
        
        if not filename:
            return JSONResponse(
                content={
                    "filename": None,
                    "extracted_date": None,
                    "date_found": False,
                    "error": "No filename found in load status"
                },
                status_code=200
            )
        
        # Pattern to match (YYYYMMDD) or (YYYY-MM-DD) at the end of filename
        # Matches dates like (20251006) or (2025-10-06) before the file extension
        import re
        
        # Try pattern with hyphens: (YYYY-MM-DD)
        pattern_with_hyphens = r'\((\d{4}-\d{2}-\d{2})\)'
        match = re.search(pattern_with_hyphens, filename)
        
        if match:
            extracted_date = match.group(1)
            return JSONResponse(
                content={
                    "filename": filename,
                    "extracted_date": extracted_date,
                    "date_found": True,
                    "error": None
                },
                status_code=200
            )
        
        # Try pattern without hyphens: (YYYYMMDD)
        pattern_without_hyphens = r'\((\d{8})\)'
        match = re.search(pattern_without_hyphens, filename)
        
        if match:
            date_str = match.group(1)
            # Convert YYYYMMDD to YYYY-MM-DD
            extracted_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
            return JSONResponse(
                content={
                    "filename": filename,
                    "extracted_date": extracted_date,
                    "date_found": True,
                    "error": None
                },
                status_code=200
            )
        
        # No date pattern found
        return JSONResponse(
            content={
                "filename": filename,
                "extracted_date": None,
                "date_found": False,
                "error": "No date pattern found in filename"
            },
            status_code=200
        )
        
    except Exception as e:
        return JSONResponse(
            content={
                "filename": filename if 'filename' in locals() else None,
                "extracted_date": None,
                "date_found": False,
                "error": str(e)
            },
            status_code=500
        )


@router.get("/data/line_counts", summary="Row counts per loaded sheet (EX-11)")
def data_line_counts():
    if hf.LOAD_STATUS.get("state") != "ready":
        return JSONResponse({"message": "data not ready", "state": hf.LOAD_STATUS.get("state")}, status_code=503)
    payload = exr.global_df_line_counts(hf.GLOBAL_DF)
    payload["state"] = hf.LOAD_STATUS.get("state")
    payload["filename"] = hf.GLOBAL_DF.get("filename")
    fd = hf.GLOBAL_DF.get("filedate")
    if fd is not None and hasattr(fd, "isoformat"):
        payload["filedate"] = fd.isoformat()
    else:
        payload["filedate"] = str(fd) if fd is not None else None
    return JSONResponse(jsonable_encoder(payload))


@router.get("/executive_summary", summary="EX-01 organisation KPI totals")
def get_executive_summary():
    df_raw_sale = hf.GLOBAL_DF.get("sale")
    df_raw_onhand = hf.GLOBAL_DF.get("onhand")
    df_item_master = hf.GLOBAL_DF.get("master")
    if df_raw_sale is None or df_raw_onhand is None or df_item_master is None:
        return _data_not_ready()
    fd = hf.GLOBAL_DF.get("filedate")
    as_of = fd.isoformat() if fd is not None and hasattr(fd, "isoformat") else None
    payload = cached_call(
        "compute_executive_summary", exr.compute_executive_summary,
        df_raw_sale=df_raw_sale, df_raw_onhand=df_raw_onhand, df_item_master=df_item_master, as_of=as_of,
    )
    payload["filename"] = hf.GLOBAL_DF.get("filename")
    return JSONResponse(jsonable_encoder(payload))


@router.get("/sales_trend_executive", summary="EX-02 monthly/weekly trend with YoY and TTM")
def get_sales_trend_executive(
    granularity: str = Query(default="monthly"),
    year_list: Optional[list[int]] = Query(default=None),
):
    df_raw_sale = hf.GLOBAL_DF.get("sale")
    df_raw_onhand = hf.GLOBAL_DF.get("onhand")
    df_item_master = hf.GLOBAL_DF.get("master")
    if df_raw_sale is None or df_raw_onhand is None or df_item_master is None:
        return _data_not_ready()
    if granularity not in ("monthly", "weekly"):
        return JSONResponse({"message": "granularity must be monthly or weekly"}, status_code=400)
    years = [int(y) for y in year_list] if year_list else None
    try:
        payload = cached_call(
            "compute_sales_trend_executive", exr.compute_sales_trend_executive,
            df_raw_sale=df_raw_sale,
            df_raw_onhand=df_raw_onhand,
            df_item_master=df_item_master,
            granularity=granularity,
            year_list=years,
        )
    except ValueError as e:
        return JSONResponse({"message": str(e)}, status_code=400)
    fd = hf.GLOBAL_DF.get("filedate")
    payload["as_of"] = fd.isoformat() if fd is not None and hasattr(fd, "isoformat") else None
    payload["filename"] = hf.GLOBAL_DF.get("filename")
    return JSONResponse(jsonable_encoder(payload))


@router.get("/concentration_summary", summary="EX-05 top-N revenue concentration")
def get_concentration_summary(
    dimension: str = Query(default="brand"),
    year: Optional[int] = Query(default=None),
    top_n: int = Query(default=10, ge=1, le=100),
):
    if year is None:
        year = datetime.now().year
    df_raw_sale = hf.GLOBAL_DF.get("sale")
    df_raw_onhand = hf.GLOBAL_DF.get("onhand")
    df_item_master = hf.GLOBAL_DF.get("master")
    if df_raw_sale is None or df_raw_onhand is None or df_item_master is None:
        return _data_not_ready()
    try:
        payload = cached_call(
            "compute_concentration_summary", exr.compute_concentration_summary,
            df_raw_sale=df_raw_sale,
            df_raw_onhand=df_raw_onhand,
            df_item_master=df_item_master,
            dimension=dimension,
            year=year,
            top_n=top_n,
        )
    except ValueError as e:
        return JSONResponse({"message": str(e)}, status_code=400)
    return JSONResponse(jsonable_encoder(payload))


@router.get("/margin_by_brand", summary="EX-03 brand profitability summary")
def get_margin_by_brand(
    year_list: Optional[list[int]] = Query(default=None),
):
    df_raw_sale = hf.GLOBAL_DF.get("sale")
    df_raw_onhand = hf.GLOBAL_DF.get("onhand")
    df_item_master = hf.GLOBAL_DF.get("master")
    df_grpo_detail = hf.GLOBAL_DF.get("grpo_detail")
    if df_raw_sale is None or df_raw_onhand is None or df_item_master is None:
        return _data_not_ready()
    years = [int(y) for y in year_list] if year_list else None
    payload = cached_call(
        "compute_margin_by_brand", exr.compute_margin_by_brand,
        df_raw_sale=df_raw_sale,
        df_raw_onhand=df_raw_onhand,
        df_item_master=df_item_master,
        df_grpo_detail=df_grpo_detail,
        year_list=years,
    )
    fd = hf.GLOBAL_DF.get("filedate")
    payload["as_of"] = fd.isoformat() if fd is not None and hasattr(fd, "isoformat") else None
    return JSONResponse(jsonable_encoder(payload))


@router.get("/brand_list_metrics", summary="Brand drill-down: all brands with combined metrics")
def get_brand_list_metrics(
    year_list: Optional[list[int]] = Query(default=None),
):
    df_raw_sale = hf.GLOBAL_DF.get("sale")
    df_raw_onhand = hf.GLOBAL_DF.get("onhand")
    df_item_master = hf.GLOBAL_DF.get("master")
    df_grpo_detail = hf.GLOBAL_DF.get("grpo_detail")
    if df_raw_sale is None or df_raw_onhand is None or df_item_master is None:
        return _data_not_ready()
    years = [int(y) for y in year_list] if year_list else None
    payload = cached_call(
        "compute_brand_list_metrics", exr.compute_brand_list_metrics,
        df_raw_sale=df_raw_sale,
        df_raw_onhand=df_raw_onhand,
        df_item_master=df_item_master,
        df_grpo_detail=df_grpo_detail,
        year_list=years,
    )
    return JSONResponse(jsonable_encoder(payload))


@router.get("/inventory_risk_summary", summary="EX-04 inventory risk and days cover")
def get_inventory_risk_summary(
    window_days: int = Query(default=90, ge=7, le=365),
    top_n: int = Query(default=20, ge=1, le=200),
):
    df_raw_sale = hf.GLOBAL_DF.get("sale")
    df_raw_onhand = hf.GLOBAL_DF.get("onhand")
    df_item_master = hf.GLOBAL_DF.get("master")
    if df_raw_sale is None or df_raw_onhand is None or df_item_master is None:
        return _data_not_ready()
    fd = hf.GLOBAL_DF.get("filedate")
    as_of = pd.Timestamp(fd) if fd is not None else None
    payload = cached_call(
        "compute_inventory_risk_summary", exr.compute_inventory_risk_summary,
        df_raw_sale=df_raw_sale,
        df_raw_onhand=df_raw_onhand,
        df_item_master=df_item_master,
        as_of=as_of,
        window_days=window_days,
        top_n=top_n,
    )
    return JSONResponse(jsonable_encoder(payload))


@router.get("/channel_performance_executive", summary="EX-07 executive channel growth and mix")
def get_channel_performance_executive(
    year_list: Optional[list[int]] = Query(default=None),
    period_type: str = Query(default="monthly"),
):
    df_raw_sale = hf.GLOBAL_DF.get("sale")
    df_raw_onhand = hf.GLOBAL_DF.get("onhand")
    df_item_master = hf.GLOBAL_DF.get("master")
    if df_raw_sale is None or df_raw_onhand is None or df_item_master is None:
        return _data_not_ready()
    years = [int(y) for y in year_list] if year_list else None
    if period_type not in ("monthly", "weekly"):
        return JSONResponse({"message": "period_type must be monthly or weekly"}, status_code=400)
    payload = cached_call(
        "compute_channel_performance_executive", exr.compute_channel_performance_executive,
        df_raw_sale=df_raw_sale,
        df_raw_onhand=df_raw_onhand,
        df_item_master=df_item_master,
        year_list=years,
        period_type=period_type,
    )
    return JSONResponse(jsonable_encoder(payload))


@router.get("/sales_data_monthly_by_channel")
async def get_sales_data_monthly_by_channel(time_frame: str = Query(default="monthly")):
    df_raw_sale = hf.GLOBAL_DF.get("sale")
    df_raw_onhand = hf.GLOBAL_DF.get("onhand")
    df_item_master = hf.GLOBAL_DF.get("master")

    if df_raw_sale is None or df_raw_onhand is None or df_item_master is None:
        return _data_not_ready()

    df_sale, df_onhand, _ = nstk.prepare_sales_and_onhand_data(
        df_raw_sale, df_raw_onhand, df_item_master
    )
    df_out = nstk.generate_sales_onhand_by_channel(df_sale, df_onhand, period_type=time_frame)
    return dataframe_split_json_response(df_out)

@router.get("/sales_data_monthly_by_brand")
async def get_sales_data_monthly_by_brand(time_frame: str = Query(default="monthly")):
    df_raw_sale = hf.GLOBAL_DF.get("sale")
    df_raw_onhand = hf.GLOBAL_DF.get("onhand")
    df_item_master = hf.GLOBAL_DF.get("master")

    if df_raw_sale is None or df_raw_onhand is None or df_item_master is None:
        return _data_not_ready()

    df_sale, df_onhand, _ = nstk.prepare_sales_and_onhand_data(
        df_raw_sale, df_raw_onhand, df_item_master
    )

    df_out = nstk.generate_sales_onhand_by_brand(
        df_sale,
        df_onhand,
        period_type=time_frame,
        df_raw_onhand=df_raw_onhand,
        df_grpo_detail=hf.GLOBAL_DF.get("grpo_detail"),
        df_tr_in=hf.GLOBAL_DF.get("tr_in"),
        df_tr_out=hf.GLOBAL_DF.get("tr_out"),
        file_date=hf.GLOBAL_DF.get("filedate"),
        df_item_master=df_item_master,
    )
    return dataframe_split_json_response(df_out)





@router.post("/brand_health_summary")
async def get_brand_health_summary(request: Request):
    """
    Returns a brand-level summary with:
    - Total Sold (Units & THB Master Price Value)
    - Current On Hand (Units & THB Master Price Value)
    - Total Purchased (Units & FOB Cost THB & Master Price THB)
    - Current Stock FOB Value (THB)
    - Current Stock Master Price Value (THB)
    """

    df_raw_sale = hf.GLOBAL_DF.get("sale")
    df_raw_onhand = hf.GLOBAL_DF.get("onhand")
    df_item_master = hf.GLOBAL_DF.get("master")
    df_grpo_detail = hf.GLOBAL_DF.get("grpo_detail")

    if df_raw_sale is None or df_raw_onhand is None or df_item_master is None:
        return _data_not_ready()

    # 🔎 Read JSON body
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"message": "Invalid JSON body"}, status_code=400)

    year_list = body.get("year_list")

    if year_list is None:
        date_obj = pd.Timestamp.now()
        year_int = date_obj.year
        year_list = [ year_int ]
        
    # Generate summary
    df_summary = nstk.generate_brand_health_summary(
        df_raw_sale,
        df_raw_onhand,
        df_item_master,
        df_grpo_detail,
        # current_date=date_obj,
        year_list=year_list
    )

    return dataframe_split_json_response(df_summary)


@router.get("/store_health_summary")
async def get_store_health_summary(
    file_date: str = Query(default=None),
    year_list: list[str] = Query(default=None)
):
    """
    Returns a brand-level summary with:
    - Total Sold (Units & THB Master Price Value)
    - Current On Hand (Units & THB Master Price Value)
    - Total Purchased (Units & FOB Cost THB & Master Price THB)
    - Current Stock FOB Value (THB)
    - Current Stock Master Price Value (THB)
    """
    
    df_raw_sale = hf.GLOBAL_DF.get("sale")
    df_raw_onhand = hf.GLOBAL_DF.get("onhand")
    df_item_master = hf.GLOBAL_DF.get("master")
    df_whs_code = hf.GLOBAL_DF.get("whs_code")

    if df_raw_sale is None or df_raw_onhand is None or df_item_master is None or df_whs_code is None:
        return _data_not_ready()

    if year_list:
        try:
            year_list = [int(y) for y in year_list]
        except ValueError:
            return JSONResponse(
                {"message": "Invalid year_list format. Must be list of years like 2023,2024."}, 
                status_code=400
            )
    else:
        year_list = None

    try:
        df_summary = nstk.generate_store_health_summary(
            df_raw_sale,
            df_raw_onhand,
            df_item_master,
            df_whs_code,
            period_type='monthly',
            current_date=file_date,
            year_list=year_list
        )
    except ValueError as e:
        return JSONResponse({"message": str(e)}, status_code=400)

    return dataframe_split_json_response(df_summary)

@router.get("/sale_brand_channel")
async def get_sales_data_monthly_by_brand_channel(
    time_frame: str = Query(default="monthly"),
    brand_name: str = Query(default=None),
    file_date: str = Query(default=None),
    year_list: list[str] = Query(default=None)
):


    df_raw_sale = hf.GLOBAL_DF.get("sale")
    df_raw_onhand = hf.GLOBAL_DF.get("onhand")
    df_item_master = hf.GLOBAL_DF.get("master")

    if df_raw_sale is None or df_raw_onhand is None or df_item_master is None:
        return _data_not_ready()

    if brand_name is None:
        return JSONResponse({"message": "Brand name is required."}, status_code=400)

    if year_list:
        try:
            year_list = [int(y) for y in year_list]
        except ValueError:
            return JSONResponse({"message": "Invalid year_list format. Must be list of years like 2023,2024."}, status_code=400)
    else:
        year_list = None

    df_sale, df_onhand, _ = nstk.prepare_sales_and_onhand_data(
        df_raw_sale, df_raw_onhand, df_item_master
    )

    df_out = nstk.generate_sales_onhand_by_brand_channel(
        df_sale,
        df_onhand,
        brand_name=brand_name,
        period_type=time_frame,
        current_date=file_date,
        year_list=year_list
    )
    return dataframe_split_json_response(df_out)

@router.get("/sale_channel_brand")
async def get_sales_data_monthly_by_channel_brand(
    time_frame: str = Query(default="monthly"),
    channel_name: str = Query(default=None),      # <= SWAPPED
    file_date: str = Query(default=None),
    year_list: list[str] = Query(default=None)
):


    df_raw_sale = hf.GLOBAL_DF.get("sale")
    df_raw_onhand = hf.GLOBAL_DF.get("onhand")
    df_item_master = hf.GLOBAL_DF.get("master")

    if df_raw_sale is None or df_raw_onhand is None or df_item_master is None:
        return _data_not_ready()

    if channel_name is None:
        return JSONResponse({"message": "Channel name is required."}, status_code=400)

    if year_list:
        try:
            year_list = [int(y) for y in year_list]
        except ValueError:
            return JSONResponse({"message": "Invalid year_list format"}, status_code=400)
    else:
        year_list = None

    df_sale, df_onhand, _ = nstk.prepare_sales_and_onhand_data(
        df_raw_sale, df_raw_onhand, df_item_master
    )

    df_out = nstk.generate_sales_onhand_by_channel_brand(
        df_sale,
        df_onhand,
        channel_name=channel_name,
        period_type=time_frame,
        current_date=file_date,
        year_list=year_list
    )
    return dataframe_split_json_response(df_out)

@router.get("/get_brand_list")
async def get_brand_list():

    df_raw_sale = hf.GLOBAL_DF.get("sale")
    df_raw_onhand = hf.GLOBAL_DF.get("onhand")
    df_item_master = hf.GLOBAL_DF.get("master")

    if df_raw_sale is None or df_raw_onhand is None:
        return _data_not_ready()

    df_item_master = hf.GLOBAL_DF.get("master")
    brand_list = nstk.get_brands(df_raw_sale, df_item_master)

    return JSONResponse(content=brand_list, media_type="application/json")

@router.get("/get_channel_list")
async def get_channel_list():

    df_raw_sale = hf.GLOBAL_DF.get("sale")
    df_raw_onhand = hf.GLOBAL_DF.get("onhand")
    df_item_master = hf.GLOBAL_DF.get("master")

    if df_raw_sale is None or df_raw_onhand is None:
        return _data_not_ready()

    channel_list = nstk.get_channels(df_raw_sale)
    return JSONResponse(content=channel_list, media_type="application/json")

@router.get("/sale_brand_profit_loss")
async def generate_brand_product_profit_loss(
    brand_name: str = Query(default=None),
    year_list: Optional[list[int]] = Query(default=None),
):

    df_raw_sale = hf.GLOBAL_DF.get("sale")
    df_raw_onhand = hf.GLOBAL_DF.get("onhand")
    df_item_master = hf.GLOBAL_DF.get("master")
    df_grpo_detail = hf.GLOBAL_DF.get("grpo_detail")

    if df_raw_sale is None or df_raw_onhand is None or df_item_master is None or df_grpo_detail is None:
        return _data_not_ready()

    if brand_name is None:
        return JSONResponse({"message": "Brand name is required."}, status_code=400)

    df_sale, df_onhand, _ = nstk.prepare_sales_and_onhand_data(
        df_raw_sale, df_raw_onhand, df_item_master
    )

    years = [int(y) for y in year_list] if year_list else None
    df_out = nstk.generate_brand_product_profit_loss(
        df_sale,
        df_onhand,
        df_grpo_detail,
        brand_name=brand_name,
        year_list=years,
    )
    return dataframe_split_json_response(df_out)

@router.get("/sale_brand_item_locations")
async def analyze_brand_item_locations(
    brand_name: str = Query(default=None),
    output: str = Query(default='Item'), # 'item' or 'location'
):


    df_raw_sale = hf.GLOBAL_DF.get("sale")
    df_raw_onhand = hf.GLOBAL_DF.get("onhand")
    df_item_master = hf.GLOBAL_DF.get("master")
    df_grpo_detail = hf.GLOBAL_DF.get("grpo_detail")
    df_whs_code = hf.GLOBAL_DF.get("whs_code")
    
    if (
        df_raw_sale is None
        or df_raw_onhand is None
        or df_item_master is None
        or df_grpo_detail is None
        or df_whs_code is None
    ):
        return _data_not_ready()

    if brand_name is None:
        return JSONResponse({"message": "Brand name is required."}, status_code=400)

    df_brand_item_locations = nstk.analyze_brand_item_locations(
        brand_name,
        df_item_master,
        df_raw_onhand,
        df_raw_sale,
        df_grpo_detail,
        df_whs_code
    )

    df_items, df_locations = df_brand_item_locations
    df = df_items if output.lower() == "item" else df_locations
    return dataframe_split_json_response(df.replace([np.inf, -np.inf], np.nan))

@router.get("/sale_brand_item_channels")
async def analyse_brand_item_channels(
    brand_name: str = Query(default=None),
    output: str = Query(default='Item'),
):


    df_raw_sale = hf.GLOBAL_DF.get("sale")
    df_raw_onhand = hf.GLOBAL_DF.get("onhand")
    df_item_master = hf.GLOBAL_DF.get("master")
    df_grpo_detail = hf.GLOBAL_DF.get("grpo_detail")
    df_whs_code = hf.GLOBAL_DF.get("whs_code")

    if (
        df_raw_sale is None
        or df_raw_onhand is None
        or df_item_master is None
        or df_grpo_detail is None
        or df_whs_code is None
    ):
        return _data_not_ready()

    if brand_name is None:
        return JSONResponse({"message": "Brand name is required."}, status_code=400)

    df_brand_item_channels = nstk.analyse_brand_item_channels(
        brand_name,
        df_item_master,
        df_raw_onhand,
        df_raw_sale,
        df_grpo_detail,
        df_whs_code
    )

    df_items, df_locations = df_brand_item_channels
    df = df_items if output.lower() == "item" else df_locations
    return dataframe_split_json_response(df.replace([np.inf, -np.inf], np.nan))

@router.get("/sale_onhand_locations_summary")
async def analyse_sale_onhand_locations():


    filename = hf.GLOBAL_DF.get("filename")
    df_raw_sale = hf.GLOBAL_DF.get("sale")
    df_raw_onhand = hf.GLOBAL_DF.get("onhand")
    df_item_master = hf.GLOBAL_DF.get("master")
    df_grpo_detail = hf.GLOBAL_DF.get("grpo_detail")
    df_whs_code = hf.GLOBAL_DF.get("whs_code")

    if (
        df_raw_sale is None
        or df_raw_onhand is None
        or df_item_master is None
        or df_whs_code is None
    ):
        return _data_not_ready()

    try:
        df_out = nstk.summarize_sales_onhand_by_location(
            filename,
            df_raw_sale,
            df_raw_onhand,
            df_whs_code,
            df_item_master,
        )
    except ValueError as e:
        return JSONResponse({"message": str(e)}, status_code=400)

    return dataframe_split_json_response(df_out.replace([np.inf, -np.inf], np.nan))


@router.get("/product_sale_vs_onhand", summary="Product Sale Vs. OnHand by brand (B.2)")
async def get_product_sale_vs_onhand(
    brand_name: str = Query(default=None),
    time_frame: str = Query(default="monthly"),
    year_list: Optional[list[int]] = Query(default=None),
):
    """Item × Month table with Sold_QTY, Sold_THB, reconstructed OnHand_QTY, Sale_Ratio."""
    df_raw_sale = hf.GLOBAL_DF.get("sale")
    df_raw_onhand = hf.GLOBAL_DF.get("onhand")
    df_item_master = hf.GLOBAL_DF.get("master")
    df_grpo_detail = hf.GLOBAL_DF.get("grpo_detail")
    df_tr_in = hf.GLOBAL_DF.get("tr_in")
    df_tr_out = hf.GLOBAL_DF.get("tr_out")

    if df_raw_sale is None or df_raw_onhand is None or df_item_master is None:
        return _data_not_ready()

    if brand_name is None:
        return JSONResponse({"message": "brand_name is required."}, status_code=400)

    fd = hf.GLOBAL_DF.get("filedate")
    if fd is None:
        import datetime
        fd = datetime.date.today()

    years = [int(y) for y in year_list] if year_list else None

    df_out = pso.generate_product_sale_vs_onhand(
        df_raw_sale=df_raw_sale,
        df_raw_onhand=df_raw_onhand,
        df_item_master=df_item_master,
        df_grpo_detail=df_grpo_detail,
        df_tr_in=df_tr_in,
        df_tr_out=df_tr_out,
        brand_name=brand_name,
        file_date=fd,
        period_type=time_frame,
        year_list=years,
    )

    return dataframe_split_json_response(df_out.replace([np.inf, -np.inf], np.nan))


@router.get("/product_sale_vs_onhand_locations", summary="Product Sale Vs. OnHand by Locations (B.3)")
async def get_product_sale_vs_onhand_locations(
    brand_name: str = Query(default=None),
    time_frame: str = Query(default="monthly"),
    year_list: Optional[list[int]] = Query(default=None),
):
    """Item × Month table with per-location breakdown of Sold, OnHand, and Sale_Ratio."""
    df_raw_sale = hf.GLOBAL_DF.get("sale")
    df_raw_onhand = hf.GLOBAL_DF.get("onhand")
    df_item_master = hf.GLOBAL_DF.get("master")
    df_grpo_detail = hf.GLOBAL_DF.get("grpo_detail")
    df_tr_in = hf.GLOBAL_DF.get("tr_in")
    df_tr_out = hf.GLOBAL_DF.get("tr_out")
    df_whs_code = hf.GLOBAL_DF.get("whs_code")

    if df_raw_sale is None or df_raw_onhand is None or df_item_master is None or df_whs_code is None:
        return _data_not_ready()

    if brand_name is None:
        return JSONResponse({"message": "brand_name is required."}, status_code=400)

    fd = hf.GLOBAL_DF.get("filedate")
    if fd is None:
        import datetime
        fd = datetime.date.today()

    years = [int(y) for y in year_list] if year_list else None

    df_out = pso.generate_product_sale_vs_onhand_locations(
        df_raw_sale=df_raw_sale,
        df_raw_onhand=df_raw_onhand,
        df_item_master=df_item_master,
        df_grpo_detail=df_grpo_detail,
        df_tr_in=df_tr_in,
        df_tr_out=df_tr_out,
        df_whs_code=df_whs_code,
        brand_name=brand_name,
        file_date=fd,
        period_type=time_frame,
        year_list=years,
    )

    return dataframe_split_json_response(df_out.replace([np.inf, -np.inf], np.nan))


# ---------------------------------------------------------------------------
# Inventory Action Alerts (OBJ-2: F-030, F-031, F-032)
# ---------------------------------------------------------------------------

@router.get("/stockout_risk", summary="Stockout risk alerts with projected dates")
def get_stockout_risk(
    window_days: int = Query(default=90, ge=7, le=365),
    threshold_days: int = Query(default=30, ge=1, le=180),
    top_n: int = Query(default=50, ge=1, le=500),
    brand: Optional[str] = Query(default=None),
):
    df_raw_sale = hf.GLOBAL_DF.get("sale")
    df_raw_onhand = hf.GLOBAL_DF.get("onhand")
    df_item_master = hf.GLOBAL_DF.get("master")
    if df_raw_sale is None or df_raw_onhand is None or df_item_master is None:
        return _data_not_ready()
    fd = hf.GLOBAL_DF.get("filedate")
    as_of = pd.Timestamp(fd) if fd is not None else None
    payload = cached_call(
        "compute_stockout_risk", ialerts.compute_stockout_risk,
        df_raw_sale=df_raw_sale,
        df_raw_onhand=df_raw_onhand,
        df_item_master=df_item_master,
        as_of=as_of,
        window_days=window_days,
        stockout_threshold_days=threshold_days,
        top_n=top_n,
        brand=brand,
    )
    return JSONResponse(jsonable_encoder(payload))


@router.get("/dead_stock", summary="Dead and slow-moving stock identification")
def get_dead_stock(
    window_days: int = Query(default=180, ge=30, le=730),
    top_n: int = Query(default=100, ge=1, le=500),
    brand: Optional[str] = Query(default=None),
):
    df_raw_sale = hf.GLOBAL_DF.get("sale")
    df_raw_onhand = hf.GLOBAL_DF.get("onhand")
    df_item_master = hf.GLOBAL_DF.get("master")
    df_grpo_detail = hf.GLOBAL_DF.get("grpo_detail")
    if df_raw_sale is None or df_raw_onhand is None or df_item_master is None:
        return _data_not_ready()
    fd = hf.GLOBAL_DF.get("filedate")
    as_of = pd.Timestamp(fd) if fd is not None else None
    payload = cached_call(
        "compute_dead_stock", ialerts.compute_dead_stock,
        df_raw_sale=df_raw_sale,
        df_raw_onhand=df_raw_onhand,
        df_item_master=df_item_master,
        df_grpo_detail=df_grpo_detail,
        as_of=as_of,
        window_days=window_days,
        top_n=top_n,
        brand=brand,
    )
    return JSONResponse(jsonable_encoder(payload))


@router.get("/reorder_analysis", summary="Reorder point analysis with suggested quantities")
def get_reorder_analysis(
    window_days: int = Query(default=90, ge=7, le=365),
    lead_time_days: int = Query(default=28, ge=1, le=180),
    target_cover_days: int = Query(default=56, ge=7, le=365),
    top_n: int = Query(default=100, ge=1, le=500),
    brand: Optional[str] = Query(default=None),
):
    df_raw_sale = hf.GLOBAL_DF.get("sale")
    df_raw_onhand = hf.GLOBAL_DF.get("onhand")
    df_item_master = hf.GLOBAL_DF.get("master")
    df_grpo_detail = hf.GLOBAL_DF.get("grpo_detail")
    if df_raw_sale is None or df_raw_onhand is None or df_item_master is None:
        return _data_not_ready()
    fd = hf.GLOBAL_DF.get("filedate")
    as_of = pd.Timestamp(fd) if fd is not None else None
    payload = cached_call(
        "compute_reorder_analysis", ialerts.compute_reorder_analysis,
        df_raw_sale=df_raw_sale,
        df_raw_onhand=df_raw_onhand,
        df_item_master=df_item_master,
        df_grpo_detail=df_grpo_detail,
        as_of=as_of,
        window_days=window_days,
        lead_time_days=lead_time_days,
        target_cover_days=target_cover_days,
        top_n=top_n,
        brand=brand,
    )
    return JSONResponse(jsonable_encoder(payload))


# ---------------------------------------------------------------------------
# Product Analytics (OBJ-3: F-034, F-035, F-036)
# ---------------------------------------------------------------------------

@router.get("/abc_classification", summary="ABC product/brand classification by revenue")
def get_abc_classification(
    year: Optional[int] = Query(default=None),
    dimension: str = Query(default="item"),
    a_threshold: float = Query(default=80.0, ge=50, le=99),
    b_threshold: float = Query(default=95.0, ge=60, le=99.9),
):
    df_raw_sale = hf.GLOBAL_DF.get("sale")
    df_raw_onhand = hf.GLOBAL_DF.get("onhand")
    df_item_master = hf.GLOBAL_DF.get("master")
    if df_raw_sale is None or df_raw_onhand is None or df_item_master is None:
        return _data_not_ready()
    payload = cached_call(
        "compute_abc_classification", pa.compute_abc_classification,
        df_raw_sale=df_raw_sale,
        df_raw_onhand=df_raw_onhand,
        df_item_master=df_item_master,
        year=year,
        dimension=dimension,
        a_threshold=a_threshold,
        b_threshold=b_threshold,
    )
    return JSONResponse(jsonable_encoder(payload))


@router.get("/product_channel_fit", summary="Product-channel fit matrix")
def get_product_channel_fit(
    year: Optional[int] = Query(default=None),
    year_list: Optional[list[int]] = Query(default=None),
    dimension: str = Query(default="brand"),
    top_n: int = Query(default=50, ge=1, le=500),
):
    df_raw_sale = hf.GLOBAL_DF.get("sale")
    df_raw_onhand = hf.GLOBAL_DF.get("onhand")
    df_item_master = hf.GLOBAL_DF.get("master")
    if df_raw_sale is None or df_raw_onhand is None or df_item_master is None:
        return _data_not_ready()
    payload = cached_call(
        "compute_product_channel_fit", pa.compute_product_channel_fit,
        df_raw_sale=df_raw_sale,
        df_raw_onhand=df_raw_onhand,
        df_item_master=df_item_master,
        year=year,
        year_list=year_list,
        dimension=dimension,
        top_n=top_n,
    )
    return JSONResponse(jsonable_encoder(payload))


# ---------------------------------------------------------------------------
# Enhanced Location Analytics (OBJ-4: F-038, F-039)
# ---------------------------------------------------------------------------

@router.get("/location_performance", summary="Location performance rankings with efficiency metrics")
def get_location_performance(
    year: Optional[int] = Query(default=None),
    year_list: Optional[list[int]] = Query(default=None),
    window_days: int = Query(default=90, ge=7, le=365),
    target_cover_days: int = Query(default=60, ge=7, le=365),
):
    df_raw_sale = hf.GLOBAL_DF.get("sale")
    df_raw_onhand = hf.GLOBAL_DF.get("onhand")
    df_item_master = hf.GLOBAL_DF.get("master")
    df_whs_code = hf.GLOBAL_DF.get("whs_code")
    if df_raw_sale is None or df_raw_onhand is None or df_item_master is None or df_whs_code is None:
        return _data_not_ready()
    payload = cached_call(
        "compute_location_performance", la.compute_location_performance,
        df_raw_sale=df_raw_sale,
        df_raw_onhand=df_raw_onhand,
        df_item_master=df_item_master,
        df_whs_code=df_whs_code,
        year=year,
        year_list=year_list,
        window_days=window_days,
        target_cover_days=target_cover_days,
    )
    return JSONResponse(jsonable_encoder(payload))


@router.get("/location_trends", summary="Monthly revenue trends per location")
def get_location_trends(
    location: Optional[str] = Query(default=None),
    top_n: int = Query(default=10, ge=1, le=50),
    year_list: Optional[list[int]] = Query(default=None),
):
    df_raw_sale = hf.GLOBAL_DF.get("sale")
    df_raw_onhand = hf.GLOBAL_DF.get("onhand")
    df_item_master = hf.GLOBAL_DF.get("master")
    df_whs_code = hf.GLOBAL_DF.get("whs_code")
    if df_raw_sale is None or df_raw_onhand is None or df_item_master is None or df_whs_code is None:
        return _data_not_ready()
    payload = cached_call(
        "compute_location_trends", la.compute_location_trends,
        df_raw_sale=df_raw_sale,
        df_raw_onhand=df_raw_onhand,
        df_item_master=df_item_master,
        df_whs_code=df_whs_code,
        location=location,
        top_n=top_n,
        year_list=year_list,
    )
    return JSONResponse(jsonable_encoder(payload))


@router.get("/location_product_mix", summary="Product/brand mix for a specific location")
def get_location_product_mix(
    location: str = Query(...),
    year: Optional[int] = Query(default=None),
    year_list: Optional[list[int]] = Query(default=None),
    top_n: int = Query(default=20, ge=1, le=100),
    window_days: int = Query(default=90, ge=7, le=365),
    brand: Optional[str] = Query(default=None),
):
    df_raw_sale = hf.GLOBAL_DF.get("sale")
    df_raw_onhand = hf.GLOBAL_DF.get("onhand")
    df_item_master = hf.GLOBAL_DF.get("master")
    df_whs_code = hf.GLOBAL_DF.get("whs_code")
    df_tr_in = hf.GLOBAL_DF.get("tr_in")
    df_grpo_detail = hf.GLOBAL_DF.get("grpo_detail")
    if df_raw_sale is None or df_raw_onhand is None or df_item_master is None or df_whs_code is None:
        return _data_not_ready()
    payload = cached_call(
        "compute_location_product_mix", la.compute_location_product_mix,
        df_raw_sale=df_raw_sale,
        df_raw_onhand=df_raw_onhand,
        df_item_master=df_item_master,
        df_whs_code=df_whs_code,
        df_tr_in=df_tr_in,
        df_grpo_detail=df_grpo_detail,
        location=location,
        year=year,
        year_list=year_list,
        top_n=top_n,
        window_days=window_days,
        brand=brand,
    )
    return JSONResponse(jsonable_encoder(payload))


# ---------------------------------------------------------------------------
# Purchase Cost Tracking & Vendor Analysis (OBJ-5: F-041, F-042)
# ---------------------------------------------------------------------------

@router.get("/purchase_cost_trends", summary="FOB cost trends over time by brand")
def get_purchase_cost_trends(
    brand: Optional[str] = Query(default=None),
    year: Optional[int] = Query(default=None),
    year_list: Optional[list[int]] = Query(default=None),
):
    df_raw_sale = hf.GLOBAL_DF.get("sale")
    df_raw_onhand = hf.GLOBAL_DF.get("onhand")
    df_item_master = hf.GLOBAL_DF.get("master")
    df_grpo_detail = hf.GLOBAL_DF.get("grpo_detail")
    if df_raw_sale is None or df_raw_onhand is None or df_item_master is None:
        return _data_not_ready()
    payload = cached_call(
        "compute_purchase_cost_trends", pua.compute_purchase_cost_trends,
        df_raw_sale=df_raw_sale,
        df_raw_onhand=df_raw_onhand,
        df_item_master=df_item_master,
        df_grpo_detail=df_grpo_detail,
        brand=brand,
        year=year,
        year_list=year_list,
    )
    return JSONResponse(jsonable_encoder(payload))


@router.get("/purchase_vs_sold", summary="Purchased vs sold comparison by brand")
def get_purchase_vs_sold(
    year: Optional[int] = Query(default=None),
    top_n: int = Query(default=30, ge=1, le=100),
    year_list: Optional[list[int]] = Query(default=None),
):
    df_raw_sale = hf.GLOBAL_DF.get("sale")
    df_raw_onhand = hf.GLOBAL_DF.get("onhand")
    df_item_master = hf.GLOBAL_DF.get("master")
    df_grpo_detail = hf.GLOBAL_DF.get("grpo_detail")
    if df_raw_sale is None or df_raw_onhand is None or df_item_master is None:
        return _data_not_ready()
    payload = cached_call(
        "compute_purchase_vs_sold", pua.compute_purchase_vs_sold,
        df_raw_sale=df_raw_sale,
        df_raw_onhand=df_raw_onhand,
        df_item_master=df_item_master,
        df_grpo_detail=df_grpo_detail,
        year=year,
        top_n=top_n,
        year_list=year_list,
    )
    return JSONResponse(jsonable_encoder(payload))


@router.get("/data_quality", summary="Item Master coverage and data-recovery tier breakdown")
def get_data_quality():
    df_raw_sale = hf.GLOBAL_DF.get("sale")
    df_raw_onhand = hf.GLOBAL_DF.get("onhand")
    df_item_master = hf.GLOBAL_DF.get("master")
    df_grpo_detail = hf.GLOBAL_DF.get("grpo_detail")
    if df_raw_sale is None or df_raw_onhand is None or df_item_master is None:
        return _data_not_ready()
    payload = cached_call(
        "compute_data_quality_summary", dq.compute_data_quality_summary,
        df_sale=df_raw_sale,
        df_onhand=df_raw_onhand,
        df_item_master=df_item_master,
        df_grpo_detail=df_grpo_detail,
    )
    return JSONResponse(jsonable_encoder(payload))


@router.get("/working_capital_trends", summary="Working capital and inventory efficiency trends")
def get_working_capital_trends(
    window_months: int = Query(default=12, ge=3, le=36),
):
    df_raw_sale = hf.GLOBAL_DF.get("sale")
    df_raw_onhand = hf.GLOBAL_DF.get("onhand")
    df_item_master = hf.GLOBAL_DF.get("master")
    df_grpo_detail = hf.GLOBAL_DF.get("grpo_detail")
    df_tr_in = hf.GLOBAL_DF.get("tr_in")
    df_tr_out = hf.GLOBAL_DF.get("tr_out")
    if df_raw_sale is None or df_raw_onhand is None or df_item_master is None:
        return _data_not_ready()
    payload = cached_call(
        "compute_working_capital_trends", pua.compute_working_capital_trends,
        df_raw_sale=df_raw_sale,
        df_raw_onhand=df_raw_onhand,
        df_item_master=df_item_master,
        df_grpo_detail=df_grpo_detail,
        df_tr_in=df_tr_in,
        df_tr_out=df_tr_out,
        file_date=hf.GLOBAL_DF.get("filedate"),
        window_months=window_months,
    )
    return JSONResponse(jsonable_encoder(payload))


@router.get("/seasonality_analysis", summary="Monthly sales patterns and seasonal trends")
def get_seasonality_analysis(
    dimension: str = Query(default="overall"),
    filter_value: Optional[str] = Query(default=None),
):
    df_raw_sale = hf.GLOBAL_DF.get("sale")
    df_raw_onhand = hf.GLOBAL_DF.get("onhand")
    df_item_master = hf.GLOBAL_DF.get("master")
    if df_raw_sale is None or df_raw_onhand is None or df_item_master is None:
        return _data_not_ready()
    payload = cached_call(
        "compute_seasonality_analysis", sm.compute_seasonality_analysis,
        df_raw_sale=df_raw_sale,
        df_raw_onhand=df_raw_onhand,
        df_item_master=df_item_master,
        dimension=dimension,
        filter_value=filter_value,
    )
    return JSONResponse(jsonable_encoder(payload))


@router.get("/margin_mix_analysis", summary="Blended margin trends and brand margin waterfall")
def get_margin_mix_analysis(
    year: Optional[int] = Query(default=None),
    top_n: int = Query(default=15, ge=1, le=50),
    year_list: Optional[list[int]] = Query(default=None),
):
    df_raw_sale = hf.GLOBAL_DF.get("sale")
    df_raw_onhand = hf.GLOBAL_DF.get("onhand")
    df_item_master = hf.GLOBAL_DF.get("master")
    df_grpo_detail = hf.GLOBAL_DF.get("grpo_detail")
    if df_raw_sale is None or df_raw_onhand is None or df_item_master is None:
        return _data_not_ready()
    payload = cached_call(
        "compute_margin_mix_analysis", sm.compute_margin_mix_analysis,
        df_raw_sale=df_raw_sale,
        df_raw_onhand=df_raw_onhand,
        df_item_master=df_item_master,
        df_grpo_detail=df_grpo_detail,
        year=year,
        top_n=top_n,
        year_list=year_list,
    )
    return JSONResponse(jsonable_encoder(payload))


# ---------------------------------------------------------------------------
# Stock Allocation Optimization & Transfer Analysis (OBJ-7)
# ---------------------------------------------------------------------------

@router.get("/stock_allocation", summary="Stock allocation: overstocked/understocked locations + transfer recs")
def get_stock_allocation(
    year: Optional[int] = Query(default=None),
    brand: Optional[str] = Query(default=None),
    window_days: int = Query(default=90, ge=7, le=365),
    top_n: int = Query(default=50, ge=1, le=200),
):
    df_raw_sale = hf.GLOBAL_DF.get("sale")
    df_raw_onhand = hf.GLOBAL_DF.get("onhand")
    df_item_master = hf.GLOBAL_DF.get("master")
    df_whs_code = hf.GLOBAL_DF.get("whs_code")
    if df_raw_sale is None or df_raw_onhand is None or df_item_master is None or df_whs_code is None:
        return _data_not_ready()
    payload = cached_call(
        "compute_stock_allocation", sal.compute_stock_allocation,
        df_raw_sale=df_raw_sale,
        df_raw_onhand=df_raw_onhand,
        df_item_master=df_item_master,
        df_whs_code=df_whs_code,
        year=year,
        brand=brand,
        window_days=window_days,
        top_n=top_n,
    )
    return JSONResponse(jsonable_encoder(payload))


@router.get("/transfer_history", summary="Transfer IN/OUT analysis: net flows, top items, monthly trend")
def get_transfer_history(
    year: Optional[int] = Query(default=None),
    top_n: int = Query(default=20, ge=1, le=100),
):
    df_tr_in = hf.GLOBAL_DF.get("tr_in")
    df_tr_out = hf.GLOBAL_DF.get("tr_out")
    df_whs_code = hf.GLOBAL_DF.get("whs_code")
    df_item_master = hf.GLOBAL_DF.get("master")
    if df_whs_code is None or df_item_master is None:
        return _data_not_ready()
    payload = cached_call(
        "compute_transfer_history", sal.compute_transfer_history,
        df_tr_in=df_tr_in if df_tr_in is not None else pd.DataFrame(),
        df_tr_out=df_tr_out if df_tr_out is not None else pd.DataFrame(),
        df_whs_code=df_whs_code,
        df_item_master=df_item_master,
        year=year,
        top_n=top_n,
    )
    return JSONResponse(jsonable_encoder(payload))


@router.get("/rebalancing_summary", summary="High-level rebalancing opportunity: surplus/deficit by location and brand")
def get_rebalancing_summary(
    year: Optional[int] = Query(default=None),
    window_days: int = Query(default=90, ge=7, le=365),
):
    df_raw_sale = hf.GLOBAL_DF.get("sale")
    df_raw_onhand = hf.GLOBAL_DF.get("onhand")
    df_item_master = hf.GLOBAL_DF.get("master")
    df_whs_code = hf.GLOBAL_DF.get("whs_code")
    if df_raw_sale is None or df_raw_onhand is None or df_item_master is None or df_whs_code is None:
        return _data_not_ready()
    payload = cached_call(
        "compute_rebalancing_summary", sal.compute_rebalancing_summary,
        df_raw_sale=df_raw_sale,
        df_raw_onhand=df_raw_onhand,
        df_item_master=df_item_master,
        df_whs_code=df_whs_code,
        year=year,
        window_days=window_days,
    )
    return JSONResponse(jsonable_encoder(payload))


@router.get(
    "/stock_bot/transfer_plan",
    summary="Stock Bot: profit-aware, shelf-cap-aware transfer recommendations grouped by destination",
)
def get_stock_bot_transfer_plan(
    year: Optional[int] = Query(default=None),
    brand: Optional[str] = Query(default=None),
):
    from app.stock_bot.api import generate_transfer_plan
    df_raw_sale = hf.GLOBAL_DF.get("sale")
    df_raw_onhand = hf.GLOBAL_DF.get("onhand")
    df_item_master = hf.GLOBAL_DF.get("master")
    df_whs_code = hf.GLOBAL_DF.get("whs_code")
    df_grpo_detail = hf.GLOBAL_DF.get("grpo_detail")
    if (
        df_raw_sale is None or df_raw_onhand is None
        or df_item_master is None or df_whs_code is None
        or df_grpo_detail is None
    ):
        return _data_not_ready()
    payload = cached_call(
        "stock_bot_transfer_plan", generate_transfer_plan,
        df_raw_sale=df_raw_sale,
        df_raw_onhand=df_raw_onhand,
        df_item_master=df_item_master,
        df_whs_code=df_whs_code,
        df_grpo_detail=df_grpo_detail,
        year=year,
        brand=brand,
    )
    return JSONResponse(jsonable_encoder(payload))


@router.get(
    "/stock_bot/location_summary",
    summary="Stock Bot: per-item summary at one location (shelf cap + net transfer)",
)
def get_stock_bot_location_summary(location: str = Query(...)):
    """Powers the 'Shelf Cap' + 'Recommended Transfer' columns on the
    location-detail page's product tables. Walks the cached transfer plan
    and aggregates per-item info for the requested physical location.
    """
    from app.stock_bot.api import (
        generate_transfer_plan,
        build_all_item_location_states,
    )
    from app.utils.stock_bot_location_summary import (
        compute_location_summary,
        enrich_with_caps_from_states,
        enrich_with_d1_stock,
        enrich_with_ai_planogram,
        enrich_with_current_planogram,
        compute_ai_transfers,
    )
    from app.utils.ai_planogram_service import ai_for_location
    from app.utils import planogram_par as pp

    df_raw_sale = hf.GLOBAL_DF.get("sale")
    df_raw_onhand = hf.GLOBAL_DF.get("onhand")
    df_item_master = hf.GLOBAL_DF.get("master")
    df_whs_code = hf.GLOBAL_DF.get("whs_code")
    df_grpo_detail = hf.GLOBAL_DF.get("grpo_detail")
    if (
        df_raw_sale is None or df_raw_onhand is None
        or df_item_master is None or df_whs_code is None
        or df_grpo_detail is None
    ):
        return _data_not_ready()

    # 1. Cached transfer plan — gives us net_transfer per item (only for
    #    items the bot actually moved).
    plan = cached_call(
        "stock_bot_transfer_plan", generate_transfer_plan,
        df_raw_sale=df_raw_sale,
        df_raw_onhand=df_raw_onhand,
        df_item_master=df_item_master,
        df_whs_code=df_whs_code,
        df_grpo_detail=df_grpo_detail,
        year=None,
        brand=None,
    )

    # 2. Cached pre-planner states — gives us shelf_cap for EVERY (item,
    #    location) the bot considered, including items the planner had
    #    no proposal for. Separate cache key from the plan so each is
    #    recomputed only when its dependencies change.
    bundle = cached_call(
        "stock_bot_all_item_location_states", build_all_item_location_states,
        df_raw_sale=df_raw_sale,
        df_raw_onhand=df_raw_onhand,
        df_item_master=df_item_master,
        df_whs_code=df_whs_code,
        df_grpo_detail=df_grpo_detail,
        year=None,
        brand=None,
    )
    states = bundle.get("states") or []
    policy = bundle.get("policy") or {}
    policy_overrides = policy.get("physical_location_overrides") or {}

    # 3. Normalise the URL-provided location name to the bot's convention.
    from app.stock_bot.output.physical_location import derive_physical_location
    bot_location = derive_physical_location(location, None, policy_overrides)

    # 4. Aggregate proposals → per-item net_transfer (search by bot's name)
    summary = compute_location_summary(plan, bot_location, policy=policy)
    # 5. Layer in shelf_cap for items WITHOUT a proposal
    summary = enrich_with_caps_from_states(
        summary, states, bot_location, policy_overrides=policy_overrides,
    )
    # 6. Overlay the AI Suggested Planogram (keyed by the original location
    #    name, matching the demand engine's consolidated-location keys). Adds
    #    every managed-shelf item and drives the AI Recommended Transfer below.
    try:
        ai_map = ai_for_location(location)
    except Exception:
        ai_map = {}
    summary = enrich_with_ai_planogram(summary, ai_map)
    # 7. Overlay the human-set planogram minimum (Current Planogram).
    try:
        summary = enrich_with_current_planogram(summary, pp.load(location))
    except Exception:
        pass
    # 8. Layer in d1_stock from raw on-hand (covers the AI-added items too).
    summary = enrich_with_d1_stock(summary, df_raw_onhand)
    # 9. AI Recommended Transfer = top up to the AI planogram from D1.
    summary = compute_ai_transfers(summary)
    # Restore the original (user-facing) location name in the response.
    summary["location"] = location
    summary["ai_available"] = bool(ai_map)
    return JSONResponse(jsonable_encoder(summary))


# ---------------------------------------------------------------------------
# Period Comparison Reports (OBJ-10)
# ---------------------------------------------------------------------------

@router.get("/period_comparison", summary="Compare two periods side-by-side with KPIs and breakdowns")
def get_period_comparison(
    period_a_year: Optional[int] = Query(default=None),
    period_a_quarter: Optional[int] = Query(default=None, ge=1, le=4),
    period_a_month: Optional[int] = Query(default=None, ge=1, le=12),
    period_b_year: Optional[int] = Query(default=None),
    period_b_quarter: Optional[int] = Query(default=None, ge=1, le=4),
    period_b_month: Optional[int] = Query(default=None, ge=1, le=12),
):
    current_year = datetime.now().year
    if period_a_year is None:
        period_a_year = current_year
    if period_b_year is None:
        period_b_year = current_year - 1
    df_raw_sale = hf.GLOBAL_DF.get("sale")
    df_raw_onhand = hf.GLOBAL_DF.get("onhand")
    df_item_master = hf.GLOBAL_DF.get("master")
    df_grpo_detail = hf.GLOBAL_DF.get("grpo_detail")
    if df_raw_sale is None or df_raw_onhand is None or df_item_master is None:
        return _data_not_ready()
    payload = cached_call(
        "compute_period_comparison", pc.compute_period_comparison,
        df_raw_sale=df_raw_sale,
        df_raw_onhand=df_raw_onhand,
        df_item_master=df_item_master,
        df_grpo_detail=df_grpo_detail,
        period_a_year=period_a_year,
        period_a_quarter=period_a_quarter,
        period_a_month=period_a_month,
        period_b_year=period_b_year,
        period_b_quarter=period_b_quarter,
        period_b_month=period_b_month,
    )
    return JSONResponse(jsonable_encoder(payload))


@router.post("/period_comparison_multi", summary="Compare 2-4 periods side-by-side with KPIs and breakdowns")
async def post_period_comparison_multi(request: Request):
    """Accept a JSON body with ``{"periods": [{"year": 2025, "quarter": 1}, ...]}``."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)
    periods = body.get("periods")
    if not periods or not isinstance(periods, list) or len(periods) < 2:
        return JSONResponse({"error": "Provide 2-4 periods"}, status_code=400)
    if len(periods) > 4:
        return JSONResponse({"error": "Maximum 4 periods"}, status_code=400)

    df_raw_sale = hf.GLOBAL_DF.get("sale")
    df_raw_onhand = hf.GLOBAL_DF.get("onhand")
    df_item_master = hf.GLOBAL_DF.get("master")
    df_grpo_detail = hf.GLOBAL_DF.get("grpo_detail")
    if df_raw_sale is None or df_raw_onhand is None or df_item_master is None:
        return _data_not_ready()

    # Build a stable cache key from sorted period params
    cache_key_parts = []
    for p in periods:
        cache_key_parts.append(f"{p.get('year')}-{p.get('quarter')}-{p.get('month')}")
    cache_suffix = "|".join(cache_key_parts)

    payload = cached_call(
        f"compute_multi_period_comparison_{cache_suffix}",
        pc.compute_multi_period_comparison,
        df_raw_sale=df_raw_sale,
        df_raw_onhand=df_raw_onhand,
        df_item_master=df_item_master,
        df_grpo_detail=df_grpo_detail,
        periods=periods,
    )
    return JSONResponse(jsonable_encoder(payload))


# ---------------------------------------------------------------------------
# Actions Dashboard (OBJ-16)
# ---------------------------------------------------------------------------

@router.get("/priority_actions", summary="Top priority business actions — the ONE page a manager opens Monday morning")
def get_priority_actions(
    max_actions: int = Query(default=30, ge=1, le=100),
):
    df_raw_sale = hf.GLOBAL_DF.get("sale")
    df_raw_onhand = hf.GLOBAL_DF.get("onhand")
    df_item_master = hf.GLOBAL_DF.get("master")
    df_whs_code = hf.GLOBAL_DF.get("whs_code")
    df_grpo_detail = hf.GLOBAL_DF.get("grpo_detail")
    if df_raw_sale is None or df_raw_onhand is None or df_item_master is None or df_whs_code is None:
        return _data_not_ready()
    fd = hf.GLOBAL_DF.get("filedate")
    as_of = pd.Timestamp(fd) if fd is not None else None
    payload = cached_call(
        "compute_priority_actions", ae.compute_priority_actions,
        df_raw_sale=df_raw_sale,
        df_raw_onhand=df_raw_onhand,
        df_item_master=df_item_master,
        df_whs_code=df_whs_code,
        df_grpo_detail=df_grpo_detail,
        as_of=as_of,
        max_actions=max_actions,
    )
    return JSONResponse(jsonable_encoder(payload))


# ---------------------------------------------------------------------------
# Item Location Detail (OBJ-19)
# ---------------------------------------------------------------------------

@router.get("/item_location_detail", summary="Per-item stock distribution and lifetime sales across all locations")
def get_item_location_detail(
    item_code: str = Query(..., description="The ItemCode to look up"),
    year_list: Optional[list[int]] = Query(default=None),
):
    df_sale = hf.GLOBAL_DF.get("sale")
    df_onhand = hf.GLOBAL_DF.get("onhand")
    df_item_master = hf.GLOBAL_DF.get("master")
    df_whs_code = hf.GLOBAL_DF.get("whs_code")
    df_grpo_detail = hf.GLOBAL_DF.get("grpo_detail")
    if df_sale is None or df_onhand is None or df_item_master is None:
        return _data_not_ready()
    payload = cached_call(
        "compute_item_location_detail", idet.compute_item_location_detail,
        item_code=item_code,
        df_sale=df_sale,
        df_onhand=df_onhand,
        df_item_master=df_item_master,
        df_whs_code=df_whs_code,
        df_grpo_detail=df_grpo_detail,
        year_list=year_list,
    )
    return JSONResponse(jsonable_encoder(payload))


# ---------------------------------------------------------------------------
# Monthly Time Series Endpoints (OBJ-81)
# ---------------------------------------------------------------------------

@router.get("/brand_monthly_trend", summary="Monthly revenue/cost/margin trend by brand")
def get_brand_monthly_trend(
    brand_name: Optional[str] = Query(default=None, description="Single brand name (omit for top-N brands)"),
    top_n: int = Query(default=5, ge=1, le=20),
    year_list: Optional[list[int]] = Query(default=None),
):
    df_raw_sale = hf.GLOBAL_DF.get("sale")
    df_raw_onhand = hf.GLOBAL_DF.get("onhand")
    df_item_master = hf.GLOBAL_DF.get("master")
    df_grpo_detail = hf.GLOBAL_DF.get("grpo_detail")
    if df_raw_sale is None or df_raw_onhand is None or df_item_master is None:
        return _data_not_ready()
    payload = cached_call(
        "compute_brand_monthly_trend", exr.compute_brand_monthly_trend,
        df_raw_sale=df_raw_sale,
        df_raw_onhand=df_raw_onhand,
        df_item_master=df_item_master,
        df_grpo_detail=df_grpo_detail,
        brand_name=brand_name,
        top_n=top_n,
        year_list=year_list,
    )
    return JSONResponse(jsonable_encoder(payload))


@router.get("/item_monthly_trend", summary="Monthly sales trend for a single item")
def get_item_monthly_trend(
    item_code: str = Query(..., description="The ItemCode to look up"),
    year_list: Optional[list[int]] = Query(default=None),
):
    df_sale = hf.GLOBAL_DF.get("sale")
    df_item_master = hf.GLOBAL_DF.get("master")
    if df_sale is None or df_item_master is None:
        return _data_not_ready()
    df_onhand = hf.GLOBAL_DF.get("onhand")
    df_grpo_detail = hf.GLOBAL_DF.get("grpo_detail")
    df_tr_in = hf.GLOBAL_DF.get("tr_in")
    df_tr_out = hf.GLOBAL_DF.get("tr_out")
    payload = cached_call(
        "compute_item_monthly_trend", idet.compute_item_monthly_trend,
        item_code=item_code,
        df_sale=df_sale,
        df_item_master=df_item_master,
        df_onhand=df_onhand,
        df_grpo_detail=df_grpo_detail,
        df_tr_in=df_tr_in,
        df_tr_out=df_tr_out,
        year_list=year_list,
    )
    return JSONResponse(jsonable_encoder(payload))


@router.get("/item_at_location_trend", summary="Monthly trend for a single item at a single location")
def get_item_at_location_trend(
    item_code: str = Query(..., description="The ItemCode to look up"),
    whs_code: str = Query(..., description="The warehouse/location code"),
    year_list: Optional[list[int]] = Query(default=None),
):
    df_sale = hf.GLOBAL_DF.get("sale")
    df_item_master = hf.GLOBAL_DF.get("master")
    if df_sale is None or df_item_master is None:
        return _data_not_ready()
    df_onhand = hf.GLOBAL_DF.get("onhand")
    df_grpo_detail = hf.GLOBAL_DF.get("grpo_detail")
    df_tr_in = hf.GLOBAL_DF.get("tr_in")
    df_tr_out = hf.GLOBAL_DF.get("tr_out")
    df_whs_code = hf.GLOBAL_DF.get("whs_code")
    payload = cached_call(
        "compute_item_at_location_trend", idet.compute_item_at_location_trend,
        item_code=item_code,
        whs_code=whs_code,
        df_sale=df_sale,
        df_item_master=df_item_master,
        df_onhand=df_onhand,
        df_grpo_detail=df_grpo_detail,
        df_tr_in=df_tr_in,
        df_tr_out=df_tr_out,
        df_whs_code=df_whs_code,
        year_list=year_list,
    )
    return JSONResponse(jsonable_encoder(payload))


@router.get("/brand_at_location_trend", summary="Monthly revenue trend for a brand at a location")
def get_brand_at_location_trend(
    location: str = Query(...),
    brand: str = Query(...),
    year_list: Optional[list[int]] = Query(default=None),
):
    df_raw_sale = hf.GLOBAL_DF.get("sale")
    df_raw_onhand = hf.GLOBAL_DF.get("onhand")
    df_item_master = hf.GLOBAL_DF.get("master")
    df_whs_code = hf.GLOBAL_DF.get("whs_code")
    if df_raw_sale is None or df_raw_onhand is None or df_item_master is None or df_whs_code is None:
        return _data_not_ready()
    payload = cached_call(
        "compute_brand_at_location_trend", la.compute_brand_at_location_trend,
        df_raw_sale=df_raw_sale,
        df_raw_onhand=df_raw_onhand,
        df_item_master=df_item_master,
        df_whs_code=df_whs_code,
        location=location,
        brand=brand,
        year_list=year_list,
    )
    return JSONResponse(jsonable_encoder(payload))


@router.get("/brand_stock_vs_sales", summary="Brand on-hand vs sold qty broken down by location and by channel")
def get_brand_stock_vs_sales(
    brand: str = Query(..., description="Brand name (Item Master GroupName)"),
    year_list: Optional[list[int]] = Query(default=None),
):
    df_raw_sale = hf.GLOBAL_DF.get("sale")
    df_raw_onhand = hf.GLOBAL_DF.get("onhand")
    df_item_master = hf.GLOBAL_DF.get("master")
    df_whs_code = hf.GLOBAL_DF.get("whs_code")
    if df_raw_sale is None or df_raw_onhand is None or df_item_master is None or df_whs_code is None:
        return _data_not_ready()
    payload = cached_call(
        "compute_brand_stock_vs_sales", exr.compute_brand_stock_vs_sales,
        df_raw_sale=df_raw_sale,
        df_raw_onhand=df_raw_onhand,
        df_item_master=df_item_master,
        df_whs_code=df_whs_code,
        brand=brand,
        year_list=year_list,
    )
    return JSONResponse(jsonable_encoder(payload))


@router.get(
    "/product_market_fit",
    summary="Per-location product-market fit: lift analysis for brand, brand×line, and price band",
)
def get_product_market_fit(
    location: str = Query(...),
    year_list: Optional[list[int]] = Query(default=None),
    top_n: int = Query(default=5, ge=1, le=20),
):
    from app.utils.product_market_fit import compute_product_market_fit
    df_raw_sale = hf.GLOBAL_DF.get("sale")
    df_raw_onhand = hf.GLOBAL_DF.get("onhand")
    df_item_master = hf.GLOBAL_DF.get("master")
    df_whs_code = hf.GLOBAL_DF.get("whs_code")
    if (
        df_raw_sale is None or df_raw_onhand is None
        or df_item_master is None or df_whs_code is None
    ):
        return _data_not_ready()
    payload = cached_call(
        "compute_product_market_fit", compute_product_market_fit,
        df_raw_sale=df_raw_sale,
        df_raw_onhand=df_raw_onhand,
        df_item_master=df_item_master,
        df_whs_code=df_whs_code,
        location=location,
        year_list=year_list,
        top_n=top_n,
    )
    return JSONResponse(jsonable_encoder(payload))


@router.get("/location_brand_trends", summary="Per-brand monthly or weekly sales at a single location")
def get_location_brand_trends(
    location: str = Query(...),
    year_list: Optional[list[int]] = Query(default=None),
    top_n: int = Query(default=50, ge=1, le=500),
    granularity: str = Query(default="monthly", description="'monthly' (default) or 'weekly'"),
):
    df_raw_sale = hf.GLOBAL_DF.get("sale")
    df_raw_onhand = hf.GLOBAL_DF.get("onhand")
    df_item_master = hf.GLOBAL_DF.get("master")
    df_whs_code = hf.GLOBAL_DF.get("whs_code")
    if df_raw_sale is None or df_raw_onhand is None or df_item_master is None or df_whs_code is None:
        return _data_not_ready()
    payload = cached_call(
        "compute_location_brand_trends", la.compute_location_brand_trends,
        df_raw_sale=df_raw_sale,
        df_raw_onhand=df_raw_onhand,
        df_item_master=df_item_master,
        df_whs_code=df_whs_code,
        location=location,
        year_list=year_list,
        top_n=top_n,
        granularity=granularity,
    )
    return JSONResponse(jsonable_encoder(payload))


@router.get("/location_item_trends", summary="Per-item monthly or weekly sales at a single location")
def get_location_item_trends(
    location: str = Query(...),
    year_list: Optional[list[int]] = Query(default=None),
    top_n: int = Query(default=100, ge=1, le=1000),
    granularity: str = Query(default="monthly", description="'monthly' (default) or 'weekly'"),
):
    df_raw_sale = hf.GLOBAL_DF.get("sale")
    df_raw_onhand = hf.GLOBAL_DF.get("onhand")
    df_item_master = hf.GLOBAL_DF.get("master")
    df_whs_code = hf.GLOBAL_DF.get("whs_code")
    if df_raw_sale is None or df_raw_onhand is None or df_item_master is None or df_whs_code is None:
        return _data_not_ready()
    payload = cached_call(
        "compute_location_item_trends", la.compute_location_item_trends,
        df_raw_sale=df_raw_sale,
        df_raw_onhand=df_raw_onhand,
        df_item_master=df_item_master,
        df_whs_code=df_whs_code,
        location=location,
        year_list=year_list,
        top_n=top_n,
        granularity=granularity,
    )
    return JSONResponse(jsonable_encoder(payload))


@router.get("/brand_at_location_item_trends", summary="Per-item monthly or weekly sales for a brand at a location")
def get_brand_at_location_item_trends(
    location: str = Query(...),
    brand: str = Query(...),
    year_list: Optional[list[int]] = Query(default=None),
    top_n: int = Query(default=200, ge=1, le=1000),
    granularity: str = Query(default="monthly", description="'monthly' (default) or 'weekly'"),
):
    df_raw_sale = hf.GLOBAL_DF.get("sale")
    df_raw_onhand = hf.GLOBAL_DF.get("onhand")
    df_item_master = hf.GLOBAL_DF.get("master")
    df_whs_code = hf.GLOBAL_DF.get("whs_code")
    if df_raw_sale is None or df_raw_onhand is None or df_item_master is None or df_whs_code is None:
        return _data_not_ready()
    payload = cached_call(
        "compute_brand_at_location_item_trends", la.compute_brand_at_location_item_trends,
        df_raw_sale=df_raw_sale,
        df_raw_onhand=df_raw_onhand,
        df_item_master=df_item_master,
        df_whs_code=df_whs_code,
        location=location,
        brand=brand,
        year_list=year_list,
        top_n=top_n,
        granularity=granularity,
    )
    return JSONResponse(jsonable_encoder(payload))


# ---------------------------------------------------------------------------
# Home Summary (OBJ-23) — one call returns all card stats
# ---------------------------------------------------------------------------

@router.get("/home_summary", summary="Home page summary stats — one call for all dashboard cards")
def get_home_summary():
    """Return lightweight summary stats for every Home page card in a single API call."""
    import logging
    logger = logging.getLogger(__name__)

    df_raw_sale = hf.GLOBAL_DF.get("sale")
    df_raw_onhand = hf.GLOBAL_DF.get("onhand")
    df_item_master = hf.GLOBAL_DF.get("master")
    df_whs_code = hf.GLOBAL_DF.get("whs_code")
    df_grpo_detail = hf.GLOBAL_DF.get("grpo_detail")
    fd = hf.GLOBAL_DF.get("filedate")

    if df_raw_sale is None or df_raw_onhand is None or df_item_master is None:
        return _data_not_ready()

    as_of = fd.isoformat() if fd is not None and hasattr(fd, "isoformat") else None
    result = {"as_of": as_of, "filename": hf.GLOBAL_DF.get("filename")}

    # 1. Executive summary — revenue and on-hand totals
    try:
        exec_data = cached_call(
            "compute_executive_summary", exr.compute_executive_summary,
            df_raw_sale=df_raw_sale, df_raw_onhand=df_raw_onhand,
            df_item_master=df_item_master, as_of=as_of,
        )
        comp = exec_data.get("comparison")
        result["executive"] = {
            "latest_revenue_thb": comp["last_revenue_thb"] if comp else None,
            "latest_period": comp["last_period"] if comp else None,
            "mom_pct": comp.get("revenue_mom_pct") if comp else None,
        }
    except Exception:
        logger.warning("home_summary: executive_summary failed", exc_info=True)
        result["executive"] = None

    # 2. Priority actions
    try:
        as_of_ts = pd.Timestamp(fd) if fd is not None else None
        actions_data = cached_call(
            "compute_priority_actions", ae.compute_priority_actions,
            df_raw_sale=df_raw_sale, df_raw_onhand=df_raw_onhand,
            df_item_master=df_item_master,
            df_whs_code=df_whs_code if df_whs_code is not None else pd.DataFrame(),
            df_grpo_detail=df_grpo_detail if df_grpo_detail is not None else pd.DataFrame(),
            as_of=as_of_ts, max_actions=30,
        )
        result["actions"] = {
            "total": actions_data.get("total_actions", 0),
            "critical": actions_data.get("by_severity", {}).get("critical", 0),
            "warning": actions_data.get("by_severity", {}).get("warning", 0),
        }
    except Exception:
        logger.warning("home_summary: priority_actions failed", exc_info=True)
        result["actions"] = None

    # 3. Stockout risk
    try:
        stockout_data = cached_call(
            "compute_stockout_risk_30_100", ialerts.compute_stockout_risk,
            df_raw_sale=df_raw_sale, df_raw_onhand=df_raw_onhand,
            df_item_master=df_item_master, threshold_days=30, top_n=100,
        )
        result["stockout"] = {
            "total_at_risk": stockout_data.get("summary", {}).get("total_at_risk_items", 0),
        }
    except Exception:
        logger.warning("home_summary: stockout_risk failed", exc_info=True)
        result["stockout"] = None

    # 4. Dead stock
    try:
        dead_data = cached_call(
            "compute_dead_stock_180_100", ialerts.compute_dead_stock,
            df_raw_sale=df_raw_sale, df_raw_onhand=df_raw_onhand,
            df_item_master=df_item_master, window_days=180, top_n=100,
        )
        result["dead_stock"] = {
            "total_thb": dead_data.get("summary", {}).get("total_capital_at_risk", 0),
        }
    except Exception:
        logger.warning("home_summary: dead_stock failed", exc_info=True)
        result["dead_stock"] = None

    # 5. Stock allocation
    try:
        alloc_data = cached_call(
            "compute_stock_allocation_all", sal.compute_stock_allocation,
            df_raw_sale=df_raw_sale, df_raw_onhand=df_raw_onhand,
            df_item_master=df_item_master,
            df_whs_code=df_whs_code if df_whs_code is not None else pd.DataFrame(),
            window_days=90,
        )
        result["allocation"] = {
            "transfer_recs": alloc_data.get("summary", {}).get("transfer_recommendations", 0),
        }
    except Exception:
        logger.warning("home_summary: stock_allocation failed", exc_info=True)
        result["allocation"] = None

    # 6. Location count
    try:
        if df_whs_code is not None and not df_whs_code.empty:
            result["locations"] = {"count": int(len(df_whs_code))}
        else:
            result["locations"] = {"count": 0}
    except Exception:
        result["locations"] = None

    # 7. Product counts
    try:
        if df_item_master is not None:
            brand_col = "GroupName" if "GroupName" in df_item_master.columns else None
            result["products"] = {
                "brands": int(df_item_master[brand_col].nunique()) if brand_col else 0,
                "items": int(len(df_item_master)),
            }
        else:
            result["products"] = None
    except Exception:
        result["products"] = None

    # 8. ABC classification (Product Analytics card)
    try:
        abc_data = cached_call(
            "compute_abc_all", pa.compute_abc_classification,
            df_raw_sale=df_raw_sale, df_raw_onhand=df_raw_onhand,
            df_item_master=df_item_master,
        )
        a_items = [r for r in abc_data.get("items", []) if r.get("abc_class") == "A"]
        a_pct = abc_data.get("summary", {}).get("A", {}).get("revenue_pct", 0)
        result["abc"] = {
            "a_count": len(a_items),
            "a_revenue_pct": round(a_pct, 1),
        }
    except Exception:
        logger.warning("home_summary: abc_classification failed", exc_info=True)
        result["abc"] = None

    # 9. Store / location health (Store Scorecard card)
    try:
        loc_data = cached_call(
            "compute_location_performance_90", la.compute_location_performance,
            df_raw_sale=df_raw_sale, df_raw_onhand=df_raw_onhand,
            df_item_master=df_item_master,
            df_whs_code=df_whs_code if df_whs_code is not None else pd.DataFrame(),
            window_days=90,
        )
        locs = loc_data.get("locations", [])
        health_scores = [l.get("health_score", 0) for l in locs if l.get("health_score") is not None]
        avg_health = round(sum(health_scores) / len(health_scores), 0) if health_scores else 0
        result["stores"] = {
            "count": len(locs),
            "avg_health": avg_health,
        }
    except Exception:
        logger.warning("home_summary: location_performance (stores) failed", exc_info=True)
        result["stores"] = None

    # 10. Margin mix (Seasonality & Margin card)
    try:
        margin_data = cached_call(
            "compute_margin_mix_all", sm.compute_margin_mix_analysis,
            df_raw_sale=df_raw_sale, df_item_master=df_item_master,
            df_grpo_detail=df_grpo_detail if df_grpo_detail is not None else pd.DataFrame(),
        )
        result["margin"] = {
            "blended_margin_pct": round(margin_data.get("blended_margin_pct", 0), 1),
        }
    except Exception:
        logger.warning("home_summary: margin_mix failed", exc_info=True)
        result["margin"] = None

    # 11. Period comparison — YoY revenue change
    try:
        if df_raw_sale is not None and not df_raw_sale.empty:
            df_s, _, _ = nstk.prepare_sales_and_onhand_data(df_raw_sale.copy(), df_raw_onhand.copy(), df_item_master.copy())
            if "DocDate" in df_s.columns:
                df_s = df_s.copy()
                df_s["DocDate"] = pd.to_datetime(df_s["DocDate"], errors="coerce")
                df_s["_year"] = df_s["DocDate"].dt.year
                years = sorted(df_s["_year"].dropna().unique())
                if len(years) >= 2:
                    latest = years[-1]
                    prev = years[-2]
                    rev_latest = df_s.loc[df_s["_year"] == latest, "LineTotal"].sum()
                    rev_prev = df_s.loc[df_s["_year"] == prev, "LineTotal"].sum()
                    yoy_pct = ((rev_latest - rev_prev) / rev_prev * 100) if rev_prev > 0 else 0
                    result["period"] = {
                        "latest_year": int(latest),
                        "prev_year": int(prev),
                        "yoy_pct": round(yoy_pct, 1),
                    }
                else:
                    result["period"] = None
            else:
                result["period"] = None
        else:
            result["period"] = None
    except Exception:
        logger.warning("home_summary: period_comparison failed", exc_info=True)
        result["period"] = None

    return JSONResponse(jsonable_encoder(result))


# ---------------------------------------------------------------------------
# Recommendations (OBJ-86 Layer 1)
# ---------------------------------------------------------------------------

@router.get("/recommendations", summary="Rule-based recommendations for a page context")
def get_recommendations(
    context: str = Query(..., description="Page context: brand, location, or item"),
    name: str = Query(..., description="Brand name, location name, or item code"),
    year_list: Optional[list[int]] = Query(default=None),
):
    """Return rule-based recommendations for the given page context."""
    df_raw_sale = hf.GLOBAL_DF.get("sale")
    df_raw_onhand = hf.GLOBAL_DF.get("onhand")
    df_item_master = hf.GLOBAL_DF.get("master")
    df_whs_code = hf.GLOBAL_DF.get("whs_code")
    df_grpo_detail = hf.GLOBAL_DF.get("grpo_detail")

    if df_raw_sale is None or df_item_master is None:
        return _data_not_ready()

    recommendations = []

    if context == "brand":
        # Get product P/L data for this brand
        try:
            products = nstk.generate_brand_product_profit_loss(
                df_raw_sale, df_raw_onhand, df_item_master,
                brand_name=name,
                year_list=year_list,
                df_grpo_detail=df_grpo_detail,
            )
            if isinstance(products, dict):
                rows = products.get("rows", [])
            elif isinstance(products, pd.DataFrame):
                rows = products.to_dict("records")
            else:
                rows = []
            # Filter out TOTAL row
            rows = [r for r in rows if r.get("ItemCode") != "TOTAL"]
            recommendations = reng.recommend_for_brand(name, rows)
        except Exception:
            logger.warning("recommendations: brand computation failed", exc_info=True)

    elif context == "location":
        try:
            perf = la.compute_location_performance(
                df_raw_sale=df_raw_sale,
                df_raw_onhand=df_raw_onhand,
                df_item_master=df_item_master,
                df_whs_code=df_whs_code,
                year_list=year_list,
            )
            loc_data = next(
                (l for l in perf.get("locations", []) if l["location"] == name), None
            )
            if loc_data:
                recommendations = reng.recommend_for_location(
                    name, loc_data, perf.get("company_avg")
                )
        except Exception:
            logger.warning("recommendations: location computation failed", exc_info=True)

    elif context == "item":
        try:
            detail = idet.compute_item_location_detail(
                item_code=name,
                df_sale=df_raw_sale,
                df_onhand=df_raw_onhand,
                df_item_master=df_item_master,
                df_whs_code=df_whs_code,
                year_list=year_list,
            )
            if detail.get("found"):
                recommendations = reng.recommend_for_item(
                    detail["item_info"], detail["locations"]
                )
        except Exception:
            logger.warning("recommendations: item computation failed", exc_info=True)

    return JSONResponse(jsonable_encoder({
        "context": context,
        "name": name,
        "recommendations": recommendations,
        "count": len(recommendations),
    }))


# ---------------------------------------------------------------------------
# Channel Analytics (OBJ-89: Channel-to-Location Mapping)
# ---------------------------------------------------------------------------

@router.get("/channel_list", summary="All sales channels with location counts and revenue")
def get_channel_list(
    year_list: Optional[list[int]] = Query(default=None),
):
    df_raw_sale = hf.GLOBAL_DF.get("sale")
    df_raw_onhand = hf.GLOBAL_DF.get("onhand")
    df_item_master = hf.GLOBAL_DF.get("master")
    df_whs_code = hf.GLOBAL_DF.get("whs_code")
    if df_raw_sale is None or df_raw_onhand is None or df_item_master is None:
        return _data_not_ready()
    payload = cached_call(
        "compute_channel_list", cha.compute_channel_list,
        df_raw_sale=df_raw_sale,
        df_raw_onhand=df_raw_onhand,
        df_item_master=df_item_master,
        df_whs_code=df_whs_code,
        year_list=year_list,
    )
    return JSONResponse(jsonable_encoder(payload))


@router.get("/channel_detail", summary="Channel detail with all locations within a channel")
def get_channel_detail(
    channel: str = Query(..., description="Channel name (GroupName)"),
    year_list: Optional[list[int]] = Query(default=None),
):
    df_raw_sale = hf.GLOBAL_DF.get("sale")
    df_raw_onhand = hf.GLOBAL_DF.get("onhand")
    df_item_master = hf.GLOBAL_DF.get("master")
    df_whs_code = hf.GLOBAL_DF.get("whs_code")
    if df_raw_sale is None or df_raw_onhand is None or df_item_master is None:
        return _data_not_ready()
    payload = cached_call(
        "compute_channel_detail", cha.compute_channel_detail,
        channel_name=channel,
        df_raw_sale=df_raw_sale,
        df_raw_onhand=df_raw_onhand,
        df_item_master=df_item_master,
        df_whs_code=df_whs_code,
        year_list=year_list,
    )
    return JSONResponse(jsonable_encoder(payload))
