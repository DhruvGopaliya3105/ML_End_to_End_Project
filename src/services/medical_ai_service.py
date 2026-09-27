# ============================================================
# MEDICAL AI SERVICE
# ============================================================

import re


# ============================================================
# CLEAN EXTRACTED TEXT
# ============================================================

def clean_medical_text(text: str) -> str:

    if not text:
        return ""

    # Remove extra spaces
    text = re.sub(
        r"[ \t]+",
        " ",
        text
    )

    # Remove excessive blank lines
    text = re.sub(
        r"\n{3,}",
        "\n\n",
        text
    )

    return text.strip()


# ============================================================
# EXTRACT IMPORTANT INFORMATION
# ============================================================

def extract_patient_information(text: str) -> dict:

    information = {
        "patient_name": None,
        "document_type": None,
        "report_status": None
    }

    # --------------------------------------------------------
    # PATIENT NAME
    # --------------------------------------------------------

    patient_match = re.search(
        r"Patient\s*:\s*(.+)",
        text,
        re.IGNORECASE
    )

    if patient_match:

        information["patient_name"] = (
            patient_match.group(1).strip()
        )

    # --------------------------------------------------------
    # DOCUMENT TYPE
    # --------------------------------------------------------

    document_match = re.search(
        r"Document\s*Type\s*:\s*(.+)",
        text,
        re.IGNORECASE
    )

    if document_match:

        information["document_type"] = (
            document_match.group(1).strip()
        )

    # --------------------------------------------------------
    # REPORT STATUS
    # --------------------------------------------------------

    status_match = re.search(
        r"Report\s*Status\s*:\s*(.+)",
        text,
        re.IGNORECASE
    )

    if status_match:

        information["report_status"] = (
            status_match.group(1).strip()
        )

    return information


# ============================================================
# FIND IMPORTANT KEYWORDS
# ============================================================

def find_medical_keywords(text: str) -> list:

    medical_keywords = [

        "hemoglobin",
        "glucose",
        "blood sugar",
        "cholesterol",
        "triglycerides",
        "blood pressure",
        "heart rate",
        "temperature",
        "wbc",
        "rbc",
        "platelets",
        "creatinine",
        "urea",
        "bilirubin",
        "thyroid",
        "tsh",
        "vitamin",
        "iron",
        "calcium",
        "sodium",
        "potassium",
        "diabetes",
        "infection",
        "fever",
        "prescription",
        "diagnosis",
        "medication"
    ]

    found_keywords = []

    text_lower = text.lower()

    for keyword in medical_keywords:

        if keyword in text_lower:

            found_keywords.append(
                keyword
            )

    return found_keywords


# ============================================================
# FIND POSSIBLE WARNING WORDS
# ============================================================

def find_warning_terms(text: str) -> list:

    warning_terms = [

        "abnormal",
        "critical",
        "high",
        "low",
        "elevated",
        "decreased",
        "increased",
        "positive",
        "negative",
        "urgent",
        "severe",
        "risk",
        "warning"
    ]

    found_terms = []

    text_lower = text.lower()

    for term in warning_terms:

        if term in text_lower:

            found_terms.append(
                term
            )

    return found_terms


# ============================================================
# CREATE SUMMARY
# ============================================================

def create_summary(
    text: str,
    information: dict,
    medical_keywords: list,
    warning_terms: list
) -> str:

    if not text:

        return (
            "No readable medical information "
            "was found in the report."
        )

    summary_parts = []

    # --------------------------------------------------------
    # DOCUMENT TYPE
    # --------------------------------------------------------

    if information["document_type"]:

        summary_parts.append(
            f"This document is identified as "
            f"{information['document_type']}."
        )

    else:

        summary_parts.append(
            "The uploaded document was successfully read."
        )

    # --------------------------------------------------------
    # PATIENT
    # --------------------------------------------------------

    if information["patient_name"]:

        summary_parts.append(
            f"Patient name identified as "
            f"{information['patient_name']}."
        )

    # --------------------------------------------------------
    # MEDICAL CONTENT
    # --------------------------------------------------------

    if medical_keywords:

        keywords_text = ", ".join(
            medical_keywords
        )

        summary_parts.append(
            f"The report contains information "
            f"related to: {keywords_text}."
        )

    else:

        summary_parts.append(
            "No specific standard medical parameters "
            "were detected from the extracted text."
        )

    # --------------------------------------------------------
    # WARNING TERMS
    # --------------------------------------------------------

    if warning_terms:

        summary_parts.append(
            "The report contains terms that may "
            "require medical review: "
            + ", ".join(warning_terms)
            + "."
        )

    else:

        summary_parts.append(
            "No obvious warning keywords were "
            "detected by this basic analysis."
        )

    return " ".join(
        summary_parts
    )


# ============================================================
# CREATE RECOMMENDATION
# ============================================================

def create_recommendation(
    warning_terms: list
) -> str:

    if warning_terms:

        return (
            "Some potentially important terms were "
            "detected. Please have a qualified doctor "
            "review the original medical report before "
            "making any medical decision."
        )

    return (
        "The report has been processed successfully. "
        "For medical interpretation or diagnosis, "
        "please consult a qualified healthcare professional."
    )


# ============================================================
# MAIN MEDICAL REPORT ANALYSIS
# ============================================================

def analyze_medical_report(
    text: str
) -> dict:

    # --------------------------------------------------------
    # CLEAN TEXT
    # --------------------------------------------------------

    cleaned_text = clean_medical_text(
        text
    )

    # --------------------------------------------------------
    # PATIENT INFORMATION
    # --------------------------------------------------------

    patient_information = (
        extract_patient_information(
            cleaned_text
        )
    )

    # --------------------------------------------------------
    # MEDICAL KEYWORDS
    # --------------------------------------------------------

    medical_keywords = (
        find_medical_keywords(
            cleaned_text
        )
    )

    # --------------------------------------------------------
    # WARNING TERMS
    # --------------------------------------------------------

    warning_terms = (
        find_warning_terms(
            cleaned_text
        )
    )

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    summary = create_summary(
        text=cleaned_text,
        information=patient_information,
        medical_keywords=medical_keywords,
        warning_terms=warning_terms
    )

    # --------------------------------------------------------
    # RECOMMENDATION
    # --------------------------------------------------------

    recommendation = create_recommendation(
        warning_terms
    )

    # --------------------------------------------------------
    # FINAL RESULT
    # --------------------------------------------------------

    return {

        "patient_information":
            patient_information,

        "medical_keywords":
            medical_keywords,

        "warning_terms":
            warning_terms,

        "summary":
            summary,

        "recommendation":
            recommendation,

        "extracted_text":
            cleaned_text
    }