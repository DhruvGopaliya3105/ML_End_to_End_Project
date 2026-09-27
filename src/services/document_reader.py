import os

import pytesseract

from PIL import Image

from pypdf import PdfReader


# ============================================================
# TESSERACT CONFIGURATION
# ============================================================

# Agar "tesseract" PATH mein available hai,
# to ye automatically kaam karega.
#
# Agar PATH issue aaye to neeche wali line uncomment karke
# apne installation path ke according set kar sakte ho.
#
# pytesseract.pytesseract.tesseract_cmd = (
#     r"C:\Program Files\Tesseract-OCR\tesseract.exe"
# )


# ============================================================
# READ TEXT FROM PDF
# ============================================================

def extract_text_from_pdf(file_path: str) -> str:

    text = ""

    try:

        reader = PdfReader(file_path)

        for page in reader.pages:

            page_text = page.extract_text()

            if page_text:

                text += page_text + "\n"

    except Exception as e:

        raise Exception(
            f"PDF text extraction failed: {str(e)}"
        )

    return text.strip()


# ============================================================
# OCR IMAGE
# ============================================================

def extract_text_from_image(file_path: str) -> str:

    try:

        image = Image.open(file_path)

        text = pytesseract.image_to_string(
            image
        )

        return text.strip()

    except Exception as e:

        raise Exception(
            f"Image OCR failed: {str(e)}"
        )


# ============================================================
# EXTRACT TEXT FROM PDF USING OCR
# ============================================================

def extract_text_from_pdf_ocr(file_path: str) -> str:

    try:

        from pdf2image import convert_from_path

        images = convert_from_path(
            file_path
        )

        text = ""

        for image in images:

            page_text = pytesseract.image_to_string(
                image
            )

            if page_text:

                text += page_text + "\n"

        return text.strip()

    except Exception as e:

        raise Exception(
            f"PDF OCR failed: {str(e)}"
        )


# ============================================================
# MAIN DOCUMENT READER
# ============================================================

def extract_text(file_path: str) -> str:

    if not os.path.isfile(file_path):

        raise FileNotFoundError(
            f"File not found: {file_path}"
        )

    extension = os.path.splitext(
        file_path
    )[1].lower()


    # ========================================================
    # PDF
    # ========================================================

    if extension == ".pdf":

        # First try normal PDF text extraction
        text = extract_text_from_pdf(
            file_path
        )

        # If PDF contains selectable text,
        # return it directly.
        if text.strip():

            return text

        # If no text found, it is probably
        # a scanned PDF.
        #
        # In that case use OCR.
        return extract_text_from_pdf_ocr(
            file_path
        )


    # ========================================================
    # IMAGE
    # ========================================================

    if extension in [
        ".jpg",
        ".jpeg",
        ".png"
    ]:

        return extract_text_from_image(
            file_path
        )


    # ========================================================
    # UNSUPPORTED FILE
    # ========================================================

    raise ValueError(
        "Unsupported file type. "
        "Only PDF, JPG, JPEG and PNG are supported."
    )