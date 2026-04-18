from fastapi import APIRouter, File, UploadFile, HTTPException, status, BackgroundTasks
from fastapi.responses import JSONResponse
import os
import shutil

from app.utils import helper_functions as hf  # <-- use the helper module
from app.utils import digital_ocean_functions as dof  # <-- use the helper module
from app.core.config import get_settings

router = APIRouter()
settings = get_settings()


# Whitelist common Excel MIME types and extensions
ALLOWED_MIME = {
    "application/vnd.ms-excel",  # .xls
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  # .xlsx
    "application/octet-stream",  # some browsers fallback to this
}
ALLOWED_EXT = {".xls", ".xlsx"}

@router.post("/upload_digital_ocean", summary="Upload a file to DigitalOcean Spaces and start background load")
async def upload_digital_ocean(file: UploadFile = File(...), background_tasks: BackgroundTasks = None):
    # Validate like /upload
    ext = hf._ext_from_filename(file.filename)
    if ext not in ALLOWED_EXT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file extension '{ext}'. Only .xls and .xlsx are allowed.",
        )
    if file.content_type not in ALLOWED_MIME and ext not in ALLOWED_EXT:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported content type '{file.content_type}'.",
        )

    safe_name = os.path.basename(file.filename)
    content_type = file.content_type or "application/octet-stream"

    # If you defined DO_PREFIX in settings (optional)
    prefix = getattr(settings, "DO_PREFIX", "") or ""
    object_key = f"{prefix}{safe_name}"

    # Stream directly to Spaces
    await file.seek(0)
    public_url = dof.upload_fileobj_to_digitalocean(
        fileobj=file.file,
        filename=object_key,
        space_name=settings.DO_SPACE_NAME,
        region=settings.DO_REGION,
        access_key=settings.DO_ACCESS_KEY,
        secret_key=settings.DO_SECRET_KEY,
        # object_key=object_key,          # << use object key (prefix + filename)
        content_type=content_type,
    )
    
    

    # Kick off background extraction from Spaces into GLOBAL_DF
    if background_tasks is None:
        background_tasks = BackgroundTasks()
    hf.schedule_load_from_spaces_key(
        space_name=settings.DO_SPACE_NAME,
        region=settings.DO_REGION,
        access_key=settings.DO_ACCESS_KEY,
        secret_key=settings.DO_SECRET_KEY,
        key=object_key,
        background_tasks=background_tasks,
    )

    return JSONResponse(
        {
            "message": "Upload successful. Data extraction started.",
            "object_key": object_key,
            "url": public_url,
            "status_endpoint": "/data/status",
            "preview_endpoint": "/data/preview",
        },
        status_code=200,
        background=background_tasks,
    )
    


# ----------------------------
# Routes
# ----------------------------
@router.post("/upload_local", summary="Upload an Excel file (.xls or .xlsx)")
async def upload_excel(file: UploadFile = File(...), background_tasks: BackgroundTasks = None):
    # Basic validations
    ext = hf._ext_from_filename(file.filename)  # <-- from helpers
    if ext not in ALLOWED_EXT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file extension '{ext}'. Only .xls and .xlsx are allowed.",
        )
    if file.content_type not in ALLOWED_MIME and ext not in ALLOWED_EXT:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported content type '{file.content_type}'.",
        )

    # Save to disk quickly
    safe_name = os.path.basename(file.filename)
    save_path = os.path.join(hf.UPLOAD_DIR, safe_name)

    await file.seek(0)
    with open(save_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Kick off background extraction via helper
    if background_tasks is None:
        background_tasks = BackgroundTasks()
    background_tasks.add_task(hf._extract_file_to_global_df, save_path, ext)

    return JSONResponse(
        {
            "message": "File uploaded. Data extraction started.",
            "filename": safe_name,
            "content_type": file.content_type,
            "status_endpoint": "/data/status",
            "preview_endpoint": "/data/preview",
        },
        status_code=200,
        background=background_tasks,
    )
