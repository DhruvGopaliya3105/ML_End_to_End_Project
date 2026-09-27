import os
import uuid

from fastapi import (
    APIRouter,
    Depends,
    Request,
    UploadFile,
    File,
    Form
)

from fastapi.responses import (
    RedirectResponse,
    FileResponse
)

from fastapi.templating import Jinja2Templates

from sqlalchemy.orm import Session

from src.database.connection import get_db

from src.services.document_service import (
    create_document,
    get_patient_documents,
    get_document
)

from src.services.document_reader import extract_text
from src.services.medical_ai_service import analyze_medical_report


# ============================================================
# ROUTER
# ============================================================

router = APIRouter()


# ============================================================
# TEMPLATES
# ============================================================

templates = Jinja2Templates(
    directory="templates"
)


# ============================================================
# UPLOAD DIRECTORY
# ============================================================

UPLOAD_DIR = "uploads/medical_reports"


# ============================================================
# ALLOWED FILE TYPES
# ============================================================

ALLOWED_EXTENSIONS = {
    ".pdf",
    ".jpg",
    ".jpeg",
    ".png"
}


# ============================================================
# MEDICAL REPORTS PAGE
# ============================================================

@router.get("/medical-reports")
def medical_reports_page(
    request: Request,
    db: Session = Depends(get_db)
):

    user_id = request.session.get("user_id")

    if user_id is None:

        return RedirectResponse(
            url="/login",
            status_code=303
        )

    documents = get_patient_documents(
        db=db,
        patient_id=user_id
    )

    return templates.TemplateResponse(
        request,
        "medical_reports.html",
        {
            "user": request.session,
            "documents": documents,
            "error": None
        }
    )


# ============================================================
# UPLOAD MEDICAL REPORT
# ============================================================

@router.post("/medical-reports/upload")
async def upload_medical_report(
    request: Request,
    document_type: str = Form("Medical Report"),
    medical_record_id: int | None = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):

    user_id = request.session.get("user_id")

    if user_id is None:

        return RedirectResponse(
            url="/login",
            status_code=303
        )

    # --------------------------------------------------------
    # ORIGINAL FILE NAME
    # --------------------------------------------------------

    original_name = file.filename or ""

    # --------------------------------------------------------
    # FILE EXTENSION
    # --------------------------------------------------------

    extension = os.path.splitext(
        original_name
    )[1].lower()

    # --------------------------------------------------------
    # VALIDATE FILE TYPE
    # --------------------------------------------------------

    if extension not in ALLOWED_EXTENSIONS:

        documents = get_patient_documents(
            db=db,
            patient_id=user_id
        )

        return templates.TemplateResponse(
            request,
            "medical_reports.html",
            {
                "user": request.session,
                "documents": documents,
                "error": (
                    "Only PDF, JPG, JPEG and PNG "
                    "files are allowed."
                )
            }
        )

    # --------------------------------------------------------
    # CREATE UPLOAD DIRECTORY
    # --------------------------------------------------------

    os.makedirs(
        UPLOAD_DIR,
        exist_ok=True
    )

    # --------------------------------------------------------
    # CREATE UNIQUE FILE NAME
    # --------------------------------------------------------

    unique_name = (
        f"{uuid.uuid4().hex}{extension}"
    )

    file_path = os.path.join(
        UPLOAD_DIR,
        unique_name
    )

    # --------------------------------------------------------
    # READ FILE
    # --------------------------------------------------------

    file_content = await file.read()

    # --------------------------------------------------------
    # SAVE FILE
    # --------------------------------------------------------

    with open(
        file_path,
        "wb"
    ) as output_file:

        output_file.write(
            file_content
        )

    # --------------------------------------------------------
    # SAVE DATABASE RECORD
    # --------------------------------------------------------

    create_document(
        db=db,
        patient_id=user_id,
        document_name=original_name,
        document_type=document_type,
        file_path=file_path,
        file_size=len(file_content),
        medical_record_id=medical_record_id
    )

    # --------------------------------------------------------
    # REDIRECT
    # --------------------------------------------------------

    return RedirectResponse(
        url="/medical-reports",
        status_code=303
    )


# ============================================================
# VIEW MEDICAL REPORT
# ============================================================

@router.get(
    "/medical-reports/{document_id}/view"
)
def view_medical_report(
    document_id: int,
    request: Request,
    db: Session = Depends(get_db)
):

    user_id = request.session.get("user_id")

    if user_id is None:

        return RedirectResponse(
            url="/login",
            status_code=303
        )

    # --------------------------------------------------------
    # GET DOCUMENT
    # --------------------------------------------------------

    document = get_document(
        db=db,
        document_id=document_id,
        patient_id=user_id
    )

    if document is None:

        return RedirectResponse(
            url="/medical-reports",
            status_code=303
        )

    # --------------------------------------------------------
    # FILE PATH
    # --------------------------------------------------------

    file_path = os.path.abspath(
        document.file_path
    )

    upload_directory = os.path.abspath(
        UPLOAD_DIR
    )

    # --------------------------------------------------------
    # SECURITY CHECK
    # --------------------------------------------------------

    try:

        if os.path.commonpath(
            [
                file_path,
                upload_directory
            ]
        ) != upload_directory:

            return RedirectResponse(
                url="/medical-reports",
                status_code=303
            )

    except ValueError:

        return RedirectResponse(
            url="/medical-reports",
            status_code=303
        )

    # --------------------------------------------------------
    # FILE EXISTS CHECK
    # --------------------------------------------------------

    if not os.path.isfile(file_path):

        return RedirectResponse(
            url="/medical-reports",
            status_code=303
        )

    # --------------------------------------------------------
    # OPEN FILE IN BROWSER
    # --------------------------------------------------------

    return FileResponse(
        path=file_path,
        filename=document.document_name,
        content_disposition_type="inline"
    )


# ============================================================
# DOWNLOAD MEDICAL REPORT
# ============================================================

@router.get(
    "/medical-reports/{document_id}/download"
)
def download_medical_report(
    document_id: int,
    request: Request,
    db: Session = Depends(get_db)
):

    user_id = request.session.get("user_id")

    if user_id is None:

        return RedirectResponse(
            url="/login",
            status_code=303
        )

    # --------------------------------------------------------
    # GET DOCUMENT
    # --------------------------------------------------------

    document = get_document(
        db=db,
        document_id=document_id,
        patient_id=user_id
    )

    if document is None:

        return RedirectResponse(
            url="/medical-reports",
            status_code=303
        )

    # --------------------------------------------------------
    # FILE PATH
    # --------------------------------------------------------

    file_path = os.path.abspath(
        document.file_path
    )

    upload_directory = os.path.abspath(
        UPLOAD_DIR
    )

    # --------------------------------------------------------
    # SECURITY CHECK
    # --------------------------------------------------------

    try:

        if os.path.commonpath(
            [
                file_path,
                upload_directory
            ]
        ) != upload_directory:

            return RedirectResponse(
                url="/medical-reports",
                status_code=303
            )

    except ValueError:

        return RedirectResponse(
            url="/medical-reports",
            status_code=303
        )

    # --------------------------------------------------------
    # FILE EXISTS CHECK
    # --------------------------------------------------------

    if not os.path.isfile(file_path):

        return RedirectResponse(
            url="/medical-reports",
            status_code=303
        )

    # --------------------------------------------------------
    # DOWNLOAD FILE
    # --------------------------------------------------------

    return FileResponse(
        path=file_path,
        filename=document.document_name,
        content_disposition_type="attachment"
    )


# ============================================================
# READ MEDICAL REPORT
# ============================================================

@router.get(
    "/medical-reports/{document_id}/read"
)
def read_medical_report(
    document_id: int,
    request: Request,
    db: Session = Depends(get_db)
):

    user_id = request.session.get("user_id")

    # --------------------------------------------------------
    # LOGIN CHECK
    # --------------------------------------------------------

    if user_id is None:

        return RedirectResponse(
            url="/login",
            status_code=303
        )

    # --------------------------------------------------------
    # GET DOCUMENT
    # --------------------------------------------------------

    document = get_document(
        db=db,
        document_id=document_id,
        patient_id=user_id
    )

    if document is None:

        return RedirectResponse(
            url="/medical-reports",
            status_code=303
        )

    # --------------------------------------------------------
    # FILE PATH
    # --------------------------------------------------------

    file_path = os.path.abspath(
        document.file_path
    )

    upload_directory = os.path.abspath(
        UPLOAD_DIR
    )

    # --------------------------------------------------------
    # SECURITY CHECK
    # --------------------------------------------------------

    try:

        if os.path.commonpath(
            [
                file_path,
                upload_directory
            ]
        ) != upload_directory:

            return RedirectResponse(
                url="/medical-reports",
                status_code=303
            )

    except ValueError:

        return RedirectResponse(
            url="/medical-reports",
            status_code=303
        )

    # --------------------------------------------------------
    # FILE EXISTS CHECK
    # --------------------------------------------------------

    if not os.path.isfile(file_path):

        return RedirectResponse(
            url="/medical-reports",
            status_code=303
        )

    # --------------------------------------------------------
    # EXTRACT TEXT
    # --------------------------------------------------------

    try:

        extracted_text = extract_text(
            file_path
        )

    except Exception as e:

        return templates.TemplateResponse(
            request,
            "medical_report_text.html",
            {
                "user": request.session,
                "document": document,
                "text": "",
                "error": str(e)
            }
        )

    # --------------------------------------------------------
    # DISPLAY EXTRACTED TEXT
    # --------------------------------------------------------

    return templates.TemplateResponse(
        request,
        "medical_report_text.html",
        {
            "user": request.session,
            "document": document,
            "text": extracted_text,
            "error": None
        }
    )
    
    
    
    # ============================================================
# ANALYZE MEDICAL REPORT
# ============================================================

@router.get(
    "/medical-reports/{document_id}/analyze"
)
def analyze_medical_report_route(
    document_id: int,
    request: Request,
    db: Session = Depends(get_db)
):

    # --------------------------------------------------------
    # GET LOGGED-IN USER
    # --------------------------------------------------------

    user_id = request.session.get("user_id")

    # --------------------------------------------------------
    # LOGIN CHECK
    # --------------------------------------------------------

    if user_id is None:

        return RedirectResponse(
            url="/login",
            status_code=303
        )

    # --------------------------------------------------------
    # GET DOCUMENT
    # --------------------------------------------------------

    document = get_document(
        db=db,
        document_id=document_id,
        patient_id=user_id
    )

    if document is None:

        return RedirectResponse(
            url="/medical-reports",
            status_code=303
        )

    # --------------------------------------------------------
    # FILE PATH
    # --------------------------------------------------------

    file_path = os.path.abspath(
        document.file_path
    )

    upload_directory = os.path.abspath(
        UPLOAD_DIR
    )

    # --------------------------------------------------------
    # SECURITY CHECK
    # --------------------------------------------------------

    try:

        if os.path.commonpath(
            [
                file_path,
                upload_directory
            ]
        ) != upload_directory:

            return RedirectResponse(
                url="/medical-reports",
                status_code=303
            )

    except ValueError:

        return RedirectResponse(
            url="/medical-reports",
            status_code=303
        )

    # --------------------------------------------------------
    # FILE EXISTS CHECK
    # --------------------------------------------------------

    if not os.path.isfile(file_path):

        return RedirectResponse(
            url="/medical-reports",
            status_code=303
        )

    # --------------------------------------------------------
    # EXTRACT TEXT
    # --------------------------------------------------------

    try:

        extracted_text = extract_text(
            file_path
        )

    except Exception as e:

        return templates.TemplateResponse(
            request,
            "medical_report_analysis.html",
            {
                "user": request.session,
                "document": document,
                "analysis": None,
                "error": (
                    f"Unable to read medical report: {str(e)}"
                )
            }
        )

    # --------------------------------------------------------
    # CHECK EXTRACTED TEXT
    # --------------------------------------------------------

    if not extracted_text or not extracted_text.strip():

        return templates.TemplateResponse(
            request,
            "medical_report_analysis.html",
            {
                "user": request.session,
                "document": document,
                "analysis": None,
                "error": (
                    "No readable text was found "
                    "in this medical report."
                )
            }
        )

    # --------------------------------------------------------
    # AI / MEDICAL TEXT ANALYSIS
    # --------------------------------------------------------

    try:

        analysis = analyze_medical_report(
            extracted_text
        )

    except Exception as e:

        return templates.TemplateResponse(
            request,
            "medical_report_analysis.html",
            {
                "user": request.session,
                "document": document,
                "analysis": None,
                "error": (
                    f"Medical report analysis failed: {str(e)}"
                )
            }
        )

    # --------------------------------------------------------
    # DISPLAY ANALYSIS
    # --------------------------------------------------------

    return templates.TemplateResponse(
        request,
        "medical_report_analysis.html",
        {
            "user": request.session,
            "document": document,
            "analysis": analysis,
            "error": None
        }
    )