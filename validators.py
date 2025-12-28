"""
Validators for Compensation Claims Processing

Validates images and PDFs according to processing rules:
- GPS location verification (Ukraine boundaries)
- Date validation (after 2022-02-24)
- Metadata integrity checks
- Fraud detection signals

Requires: metadata_extractor.py, documents_classifier.py, models.py
"""


from datetime import datetime, date
from typing import Optional, Dict, Any, Tuple
import re

import numpy as np

# Import our modules
from metadata_extractor import extract_grouped_metadata, MetadataGroups
from documents_classifier import (
    get_image_processing_rules,
    get_pdf_processing_rules,
    analyze_document,
)
from models import (
    DocumentAnalysis,
    ValidationResult,
    PipelineResult,
    Decision,
)


# =============================================================================
# CONSTANTS
# =============================================================================

# War start date - claims must be after this
WAR_START_DATE = date(2022, 2, 24)

# Ukraine approximate bounding box (generous margins)
UKRAINE_BOUNDS = {
    "min_lat": 44.0,   # Southern Crimea
    "max_lat": 52.5,   # Northern border
    "min_lon": 22.0,   # Western border
    "max_lon": 40.5,   # Eastern border (includes Donbas)
}

# Suspicious software that indicates editing
SUSPICIOUS_SOFTWARE = [
    "photoshop",
    "gimp",
    "lightroom",
    "capture one",
    "affinity",
    "pixelmator",
    "paint.net",
    "corel",
    "snapseed",
    "vsco",
]

# Stock photo watermark patterns
STOCK_PATTERNS = [
    "shutterstock",
    "getty",
    "istock",
    "adobe stock",
    "dreamstime",
    "123rf",
    "depositphotos",
    "alamy",
]

# Legitimate camera/phone software
LEGITIMATE_SOFTWARE = [
    "camera",
    "samsung",
    "huawei",
    "xiaomi",
    "oppo",
    "vivo",
    "oneplus",
    "google",
    "apple",
    "iphone",
    "dji",
    "micasense",
    "pix4d",
]


# =============================================================================
# GEO UTILITIES
# =============================================================================

def is_in_ukraine(lat: float, lon: float) -> bool:
    """Check if coordinates are within Ukraine's approximate boundaries."""
    return (
        UKRAINE_BOUNDS["min_lat"] <= lat <= UKRAINE_BOUNDS["max_lat"] and
        UKRAINE_BOUNDS["min_lon"] <= lon <= UKRAINE_BOUNDS["max_lon"]
    )


def get_location_description(lat: float, lon: float) -> str:
    """Get approximate location description based on coordinates."""
    if not is_in_ukraine(lat, lon):
        if lat > UKRAINE_BOUNDS["max_lat"]:
            return "North of Ukraine (possibly Belarus/Russia)"
        elif lat < UKRAINE_BOUNDS["min_lat"]:
            return "South of Ukraine (possibly Black Sea/Turkey)"
        elif lon < UKRAINE_BOUNDS["min_lon"]:
            return "West of Ukraine (possibly Poland/Slovakia/Hungary)"
        elif lon > UKRAINE_BOUNDS["max_lon"]:
            return "East of Ukraine (possibly Russia)"
        return "Outside Ukraine"

    # Rough regions within Ukraine
    if lat > 50.5:
        if lon < 32:
            return "Northern Ukraine (Kyiv region)"
        else:
            return "Northeastern Ukraine (Sumy/Chernihiv region)"
    elif lat > 48.5:
        if lon < 32:
            return "Central Ukraine"
        elif lon < 37:
            return "Eastern Ukraine (Kharkiv/Donetsk region)"
        else:
            return "Eastern Ukraine (Luhansk region)"
    elif lat > 46.5:
        if lon < 34:
            return "Southern Ukraine (Zaporizhzhia/Kherson region)"
        else:
            return "Southeastern Ukraine"
    else:
        return "Southern Ukraine (Crimea region)"


def calculate_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two points using Haversine formula."""
    from math import radians, sin, cos, sqrt, atan2

    R = 6371  # Earth's radius in km

    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))

    return R * c


# =============================================================================
# DATE UTILITIES
# =============================================================================

def parse_exif_datetime(date_str: str) -> Optional[datetime]:
    """Parse EXIF datetime format to datetime object."""
    if not date_str:
        return None

    # Common EXIF formats
    formats = [
        "%Y:%m:%d %H:%M:%S",     # Standard EXIF
        "%Y-%m-%d %H:%M:%S",     # ISO-like
        "%Y:%m:%d",              # Date only
        "%Y-%m-%d",              # ISO date
        "%Y-%m-%dT%H:%M:%S",     # ISO with T
        "%Y-%m-%dT%H:%M:%SZ",    # ISO with timezone
    ]

    for fmt in formats:
        try:
            return datetime.strptime(str(date_str).strip(), fmt)
        except ValueError:
            continue

    return None


def is_date_valid_for_claim(dt: datetime, min_date: date = WAR_START_DATE) -> Tuple[str, str]:
    """
    Check if date is valid for a damage claim.

    Returns:
        Tuple of (status, reason) where status is 'ok', 'warning', or 'error'
    """
    if dt.date() < min_date:
        return 'error', f"Photo date {dt.date()} is before war start ({min_date})"

    if dt.date() > date.today():
        return 'error', f"Photo date {dt.date()} is in the future"

    # Check if date is very old (before 2020 - likely metadata error)
    if dt.year < 2020:
        return 'warning', f"Photo date {dt.date()} seems too old - verify metadata"

    return 'ok', f"Photo date {dt.date()} is valid"


# =============================================================================
# GPS PARSING
# =============================================================================

def parse_gps_coordinate(coord_data: Any, ref: str = None) -> Optional[float]:
    """Parse GPS coordinate from various EXIF formats to decimal degrees."""
    if coord_data is None:
        return None

    try:
        # Already a float
        if isinstance(coord_data, (int, float)):
            val = float(coord_data)
            if ref and ref.upper() in ('S', 'W'):
                val = -val
            return val

        # String format "49.1234" or "49° 7' 24.12""
        if isinstance(coord_data, str):
            # Try simple float
            try:
                val = float(coord_data)
                if ref and ref.upper() in ('S', 'W'):
                    val = -val
                return val
            except ValueError:
                pass

            # Try DMS format
            match = re.match(r"(\d+)[°\s]+(\d+)['\s]+(\d+\.?\d*)", coord_data)
            if match:
                d, m, s = map(float, match.groups())
                val = d + m/60 + s/3600
                if ref and ref.upper() in ('S', 'W'):
                    val = -val
                return val

        # Tuple/list format (degrees, minutes, seconds)
        if isinstance(coord_data, (tuple, list)):
            if len(coord_data) >= 3:
                d, m, s = coord_data[0], coord_data[1], coord_data[2]
                # Handle IFDRational or fractions
                d = float(d) if not hasattr(d, 'numerator') else d.numerator / d.denominator
                m = float(m) if not hasattr(m, 'numerator') else m.numerator / m.denominator
                s = float(s) if not hasattr(s, 'numerator') else s.numerator / s.denominator

                val = d + m/60 + s/3600
                if ref and ref.upper() in ('S', 'W'):
                    val = -val
                return val
    except Exception:
        pass

    return None


def extract_gps_from_metadata(metadata: MetadataGroups) -> Optional[Dict[str, float]]:
    """Extract GPS coordinates from metadata groups."""
    gps_data = metadata.gps_location

    if not gps_data:
        return None

    lat = parse_gps_coordinate(
        gps_data.get("GPSLatitude"),
        gps_data.get("GPSLatitudeRef")
    )

    lon = parse_gps_coordinate(
        gps_data.get("GPSLongitude"),
        gps_data.get("GPSLongitudeRef")
    )

    if lat is not None and lon is not None:
        return {"latitude": lat, "longitude": lon}

    return None


# =============================================================================
# IMAGE VALIDATORS
# =============================================================================

def validate_image_gps(
    metadata: MetadataGroups,
    result: ValidationResult,
    require_gps: bool = False
) -> None:
    """Validate GPS coordinates in image metadata."""
    result.rules_applied.append("check_gps")

    gps_coords = extract_gps_from_metadata(metadata)

    if gps_coords is None:
        if require_gps:
            result.add_warning(
                "No GPS coordinates found in image. Location cannot be verified.",
                "gps_exists"
            )
        else:
            result.add_info("No GPS coordinates in metadata")
        return

    lat, lon = gps_coords["latitude"], gps_coords["longitude"]
    result.extracted_data["gps_latitude"] = lat
    result.extracted_data["gps_longitude"] = lon

    # Check if in Ukraine
    if is_in_ukraine(lat, lon):
        location = get_location_description(lat, lon)
        result.pass_check("gps_valid", f"Location: {location} ({lat:.4f}, {lon:.4f})")
        result.extracted_data["gps_location"] = location
    else:
        location = get_location_description(lat, lon)
        result.add_warning(
            f"GPS coordinates ({lat:.4f}, {lon:.4f}) are outside Ukraine: {location}",
            "gps_valid"
        )
        result.extracted_data["gps_location"] = location


def validate_image_date(
    metadata: MetadataGroups,
    result: ValidationResult,
    min_date: date = WAR_START_DATE
) -> None:
    """Validate image capture date."""
    result.rules_applied.append("validate_date")

    # Try multiple date sources
    date_sources = [
        ("DateTimeOriginal", metadata.exif_camera.get("DateTimeOriginal")),
        ("DateTimeDigitized", metadata.exif_camera.get("DateTimeDigitized")),
        ("DateTime", metadata.tiff_structure.get("DateTime")),
    ]

    capture_date = None
    date_source = None

    for source_name, date_str in date_sources:
        if date_str:
            parsed = parse_exif_datetime(str(date_str))
            if parsed:
                capture_date = parsed
                date_source = source_name
                break

    if capture_date is None:
        result.add_warning(
            "No capture date found in metadata. Cannot verify when photo was taken.",
            "date_exists"
        )
        return

    result.extracted_data["capture_datetime"] = capture_date.isoformat()
    result.extracted_data["capture_date_source"] = date_source

    # Validate date range
    val_res, reason = is_date_valid_for_claim(capture_date, min_date)

    if val_res == 'ok':
        result.pass_check("date_valid", reason)
    elif val_res == 'error':
        result.add_error(reason, "date_valid")
    else:
        result.add_warning(reason, "date_valid")


def validate_image_device(
    metadata: MetadataGroups,
    result: ValidationResult
) -> None:
    """Validate device/software information."""
    result.rules_applied.append("check_device")

    make = metadata.tiff_structure.get("Make", "")
    model = metadata.tiff_structure.get("Model", "")
    software = metadata.tiff_structure.get("Software", "")

    result.extracted_data["device_make"] = make
    result.extracted_data["device_model"] = model
    result.extracted_data["software"] = software

    # Check if device info exists
    if not make and not model:
        result.add_warning(
            "No camera/device information found. Photo may have been downloaded or stripped of metadata.",
            "device_exists"
        )
    else:
        result.pass_check("device_exists", f"Device: {make} {model}")

    # Check for suspicious software
    software_lower = software.lower() if software else ""

    for suspicious in SUSPICIOUS_SOFTWARE:
        if suspicious in software_lower:
            result.add_error(
                f"Image was processed with editing software: {software}",
                "software_check"
            )
            return

    # Check for legitimate software
    is_legitimate = False
    for legit in LEGITIMATE_SOFTWARE:
        if legit in software_lower or legit in make.lower() or legit in model.lower():
            is_legitimate = True
            break

    if software and not is_legitimate:
        result.add_info(f"Software: {software} (not in known list)")
    elif is_legitimate:
        result.pass_check("software_check", "Legitimate software/device detected")


def validate_image_integrity(
    metadata: MetadataGroups,
    result: ValidationResult
) -> None:
    """Check for signs of image manipulation."""
    result.rules_applied.append("check_integrity")

    width = metadata.basic_info.get("width", 0)
    height = metadata.basic_info.get("height", 0)

    result.extracted_data["image_width"] = width
    result.extracted_data["image_height"] = height

    # Very small images are suspicious
    if width < 500 or height < 500:
        result.add_warning(
            f"Very low resolution image: {width}x{height}. May be thumbnail or heavily compressed.",
            "resolution_check"
        )
    elif width > 10000 or height > 10000:
        result.add_info(f"Very high resolution: {width}x{height}")
    else:
        result.pass_check("resolution_check", f"Resolution: {width}x{height}")


# =============================================================================
# PDF VALIDATORS
# =============================================================================

def extract_pdf_metadata(file_path: str) -> dict:
    """Extract metadata from PDF file."""
    try:
        from pypdf import PdfReader

        reader = PdfReader(file_path)
        metadata = reader.metadata or {}

        # Convert to dict with string keys
        result = {
            "page_count": len(reader.pages),
            "is_encrypted": reader.is_encrypted,
        }

        # Standard PDF metadata fields
        for key in ["/Title", "/Author", "/Subject", "/Creator", "/Producer",
                    "/CreationDate", "/ModDate"]:
            if key in metadata:
                result[key.lstrip("/")] = str(metadata[key])

        return result

    except Exception as e:
        return {"error": str(e)}


def validate_pdf_modification(
    pdf_metadata: dict,
    result: ValidationResult
) -> None:
    """Check PDF modification dates."""
    result.rules_applied.append("check_modification")

    creation_date = pdf_metadata.get("CreationDate")
    mod_date = pdf_metadata.get("ModDate")

    if creation_date:
        result.extracted_data["pdf_creation_date"] = creation_date
    if mod_date:
        result.extracted_data["pdf_modification_date"] = mod_date

    # Check if modified after creation (might indicate tampering)
    if creation_date and mod_date and creation_date != mod_date:
        result.add_info(f"PDF was modified after creation")


def validate_pdf_producer(
    pdf_metadata: dict,
    result: ValidationResult
) -> None:
    """Check PDF producer/creator software."""
    result.rules_applied.append("check_producer")

    producer = pdf_metadata.get("Producer", "")
    creator = pdf_metadata.get("Creator", "")

    result.extracted_data["pdf_producer"] = producer
    result.extracted_data["pdf_creator"] = creator

    # Check for suspicious producers
    producer_lower = producer.lower()

    suspicious_producers = ["adobe photoshop", "gimp"]
    for susp in suspicious_producers:
        if susp in producer_lower:
            result.add_error(
                f"PDF created with image editing software: {producer}",
                "producer_check"
            )
            return

    result.pass_check("producer_check", f"Producer: {producer or 'Unknown'}")


# =============================================================================
# MAIN VALIDATION FUNCTIONS
# =============================================================================

def validate_image(
    file_path: str,
    rules: dict
) -> Tuple[ValidationResult, Optional[MetadataGroups]]:
    """
    Validate an image file according to specified rules.

    Args:
        file_path: Path to image file
        rules: Dictionary of validation rules

    Returns:
        Tuple of (ValidationResult, MetadataGroups or None)
    """
    result = ValidationResult(
        file_path=file_path,
        validation_timestamp=datetime.now().isoformat()
    )

    # Check for auto-reject
    if rules.get("auto_reject"):
        result.add_error(rules.get("reason", "Auto-rejected"), "auto_reject")
        return result, None

    # Extract metadata
    try:
        metadata = extract_grouped_metadata(file_path)
    except Exception as e:
        result.add_error(f"Failed to extract metadata: {str(e)}", "metadata_extraction")
        return result, None

    # Run applicable validations
    if rules.get("check_gps", True):
        validate_image_gps(metadata, result, rules.get("require_gps", False))

    if rules.get("check_date", True):
        min_date = WAR_START_DATE
        if rules.get("min_date"):
            try:
                min_date = datetime.strptime(rules["min_date"], "%Y-%m-%d").date()
            except ValueError:
                pass
        validate_image_date(metadata, result, min_date)

    if rules.get("check_device", True):
        validate_image_device(metadata, result)

    # Always check integrity
    validate_image_integrity(metadata, result)

    return result, metadata


def validate_pdf(
    file_path: str,
    rules: dict
) -> Tuple[ValidationResult, Optional[dict]]:
    """
    Validate a PDF file according to specified rules.

    Args:
        file_path: Path to PDF file
        rules: Dictionary of validation rules

    Returns:
        Tuple of (ValidationResult, pdf_metadata dict or None)
    """
    result = ValidationResult(
        file_path=file_path,
        validation_timestamp=datetime.now().isoformat()
    )

    # Check for auto-reject
    if rules.get("auto_reject"):
        result.add_error(rules.get("reason", "Auto-rejected"), "auto_reject")
        return result, None

    # Extract PDF metadata
    try:
        pdf_metadata = extract_pdf_metadata(file_path)
    except Exception as e:
        result.add_error(f"Failed to extract PDF metadata: {str(e)}", "pdf_extraction")
        return result, None

    if "error" in pdf_metadata:
        result.add_warning(f"PDF parsing issue: {pdf_metadata['error']}", "pdf_parse")

    # Run applicable validations
    if rules.get("check_modification", True):
        validate_pdf_modification(pdf_metadata, result)

    # Always check producer
    validate_pdf_producer(pdf_metadata, result)

    # Store basic info
    result.extracted_data["pdf_page_count"] = pdf_metadata.get("page_count")
    result.extracted_data["pdf_encrypted"] = pdf_metadata.get("is_encrypted", False)

    if pdf_metadata.get("is_encrypted"):
        result.add_warning("PDF is encrypted", "pdf_encrypted")

    return result, pdf_metadata


def validate_file(
    file_path: str,
    analysis: DocumentAnalysis
) -> Tuple[ValidationResult, Any]:
    """
    Validate any file based on its analysis.

    Args:
        file_path: Path to file
        analysis: DocumentAnalysis from analyze_document()

    Returns:
        Tuple of (ValidationResult, metadata)
    """
    file_type = analysis.file_type

    if file_type == "image":
        # For images, document_type is actually the category
        category = analysis.document_type
        rules = get_image_processing_rules(category)
        return validate_image(file_path, rules)

    elif file_type == "pdf":
        doc_type = analysis.document_type
        creation_method = analysis.creation_method
        rules = get_pdf_processing_rules(doc_type, creation_method)
        return validate_pdf(file_path, rules)

    else:
        result = ValidationResult(
            file_path=file_path,
            validation_timestamp=datetime.now().isoformat()
        )
        result.add_error(f"Unknown file type: {file_type}", "file_type")
        return result, None


# =============================================================================
# DECISION LOGIC
# =============================================================================

# Critical red flags that lead to confidence = 0 (REJECT)
CRITICAL_RED_FLAGS = [
    "images don't match",
    "images dont match",  # Without apostrophe
    "don't match text claims",
    "dont match text claims",
    "document appears forged",
    "tampering detected",
    "fake document",
    "editing software",  # Photoshop, GIMP, etc.
    "photoshop",
    "gimp",
]

# Suspicious red flags that lead to confidence = 0.25 (REVIEW)
SUSPICIOUS_RED_FLAGS = [
    "government stamp",
    "no gps",
    "no camera",
    "no device",
    "date before war",
    "low resolution",
    "metadata stripped",
    "downloaded",
    "outside ukraine",  # GPS coordinates outside Ukraine
]

# Technical errors that should be REVIEW (not REJECT)
TECHNICAL_ERRORS = [
    "encrypted",
    "encripted",  # Common typo
    "decrypted",
    "corrupted",
    "cannot read",
    "parsing issue",
    "password protected",
]


def is_critical_issue(issue: str) -> bool:
    """Check if issue is critical (leads to confidence = 0)."""
    issue_lower = issue.lower()
    return any(critical in issue_lower for critical in CRITICAL_RED_FLAGS)


def is_suspicious_issue(issue: str) -> bool:
    """Check if issue is suspicious (leads to confidence = 0.25)."""
    issue_lower = issue.lower()
    # Suspicious if matches suspicious patterns OR is any red flag not matching critical
    if any(susp in issue_lower for susp in SUSPICIOUS_RED_FLAGS):
        return True
    return False


def is_technical_error(error: str) -> bool:
    """Check if error is technical (should be REVIEW, not REJECT)."""
    error_lower = error.lower()
    return any(tech in error_lower for tech in TECHNICAL_ERRORS)


def bucket_confidence(raw_confidence: float) -> float:
    """
    Bucket raw LLM confidence into discrete levels.
    
    > 0.8  → 1.0
    > 0.6  → 0.7
    >= 0.3 → 0.5
    < 0.3  → 0.25
    """
    if raw_confidence > 0.8:
        return 1.0
    elif raw_confidence > 0.6:
        return 0.7
    elif raw_confidence >= 0.3:
        return 0.5
    else:
        return 0.25


def calculate_confidence(
    llm_confidence: float,
    validation_confidence: float,
    all_issues: list
) -> float:
    """
    Calculate final confidence using two-stage approach.
    
    Stage 1: LLM confidence + red flags
    - Bucket raw LLM confidence
    - If critical issue → 0
    - If suspicious issue → 0.25
    
    Stage 2: Apply validation penalties
    - Multiply by validation.confidence
    
    Args:
        llm_confidence: Raw confidence from LLM (classification × extraction)
        validation_confidence: Confidence from metadata validation
        all_issues: Combined list of red_flags + errors + warnings
    
    Returns:
        Final confidence score
    """
    # Stage 1: Bucket LLM confidence
    bucketed = bucket_confidence(llm_confidence)
    
    # Stage 1: Check for critical/suspicious issues
    has_critical = any(is_critical_issue(issue) for issue in all_issues)
    has_suspicious = any(is_suspicious_issue(issue) for issue in all_issues)
    
    if has_critical:
        stage1_confidence = 0.0
    elif has_suspicious:
        stage1_confidence = 0.25
    else:
        stage1_confidence = bucketed
    
    # Stage 2: Apply validation confidence (already has penalties from add_error/add_warning)
    final_confidence = stage1_confidence * validation_confidence
    
    return final_confidence


# Keep old function for backward compatibility, but redirect to new logic
def calculate_adjusted_confidence(
    base_confidence: float,
    red_flags: list,
    warnings: list
) -> float:
    """
    DEPRECATED: Use calculate_confidence() instead.
    Kept for backward compatibility.
    """
    all_issues = red_flags + warnings
    # Assume validation_confidence = 1.0 if not provided
    return calculate_confidence(base_confidence, 1.0, all_issues)


def deduplicate_issues(issues: list) -> list:
    """Remove duplicate/similar issues."""
    if not issues:
        return []
    
    # Keywords that indicate same underlying issue
    ENCRYPTION_KEYWORDS = ["encrypt", "decrypt", "password", "encript"]
    CORRUPTION_KEYWORDS = ["corrupt", "damaged", "invalid"]
    
    def is_encryption_related(text: str) -> bool:
        text_lower = text.lower()
        return any(kw in text_lower for kw in ENCRYPTION_KEYWORDS)
    
    def is_corruption_related(text: str) -> bool:
        text_lower = text.lower()
        return any(kw in text_lower for kw in CORRUPTION_KEYWORDS)
    
    seen_exact = set()
    seen_encryption = False
    seen_corruption = False
    result = []
    
    for issue in issues:
        normalized = issue.lower().strip()
        
        # Skip exact duplicates
        if normalized in seen_exact:
            continue
        
        # Skip if we already have an encryption-related issue
        if is_encryption_related(normalized):
            if seen_encryption:
                continue
            seen_encryption = True
        
        # Skip if we already have a corruption-related issue
        if is_corruption_related(normalized):
            if seen_corruption:
                continue
            seen_corruption = True
        
        seen_exact.add(normalized)
        result.append(issue)
    
    return result


def make_decision(
    analysis: DocumentAnalysis,
    validation: ValidationResult
) -> Tuple[str, str, bool]:
    """
    Determine processing decision based on analysis and validation.

    Decision hierarchy:
    1. Screenshot → REJECT (always)
    2. Critical issues → REJECT (confidence = 0)
    3. Technical errors → REVIEW (not reject, it's not fraud)
    4. Suspicious issues → REVIEW (confidence capped at 0.25)
    5. Confidence-based decision

    Returns:
        Tuple of (decision, reason, is_acceptable)
    """
    # Collect all issues and deduplicate together
    raw_red_flags = analysis.red_flags or []
    raw_warnings = (analysis.warnings or []) + (validation.warnings or [])
    raw_errors = validation.errors or []
    
    # Deduplicate ALL together to catch cross-category duplicates
    all_issues_raw = raw_errors + raw_red_flags + raw_warnings
    deduped_all = deduplicate_issues(all_issues_raw)
    deduped_set = set(i.lower().strip() for i in deduped_all)
    
    # Filter to keep only deduped
    red_flags = [f for f in raw_red_flags if f.lower().strip() in deduped_set]
    all_warnings = [w for w in raw_warnings if w.lower().strip() in deduped_set]
    errors = [e for e in raw_errors if e.lower().strip() in deduped_set]
    all_issues = errors + red_flags + all_warnings
    
    # 1. Screenshot → always REJECT
    if analysis.document_type == "screenshot" or analysis.creation_method == "screenshot":
        return (Decision.REJECT.value, "Screenshot not accepted as proof", False)
    
    # 2. Check for critical issues (leads to confidence = 0, REJECT)
    critical_issues = [i for i in all_issues if is_critical_issue(i) and not is_technical_error(i)]
    if critical_issues:
        return (Decision.REJECT.value, critical_issues[0], False)
    
    # 3. Technical errors → REVIEW (not REJECT, it's not fraud)
    technical_issues = [i for i in all_issues if is_technical_error(i)]
    if technical_issues:
        return (Decision.REVIEW.value, f"Technical issue: {technical_issues[0]}", False)
    
    # 4. Check for suspicious issues (leads to confidence = 0.25, REVIEW)
    suspicious_issues = [i for i in all_issues if is_suspicious_issue(i)]
    if suspicious_issues:
        return (Decision.REVIEW.value, f"{len(suspicious_issues)} issue(s) require review", False)
    
    # 5. ANY issues at all → REVIEW (even warnings)
    if all_issues:
        return (Decision.REVIEW.value, f"{len(all_issues)} issue(s) require review", False)
    
    # 6. Calculate confidence for remaining cases (no issues)
    llm_confidence = analysis.confidence
    validation_confidence = validation.confidence
    final_confidence = calculate_confidence(llm_confidence, validation_confidence, all_issues)
    
    # 7. Confidence-based final decision (only when no issues)
    if final_confidence >= 0.7:
        return (Decision.ACCEPT.value, "Document passed all checks", True)
    elif final_confidence >= 0.4:
        return (Decision.REVIEW.value, "Moderate confidence, verification recommended", False)
    else:
        return (Decision.REJECT.value, "Low confidence", False)


# =============================================================================
# PIPELINE FUNCTION
# =============================================================================

def process_document(file_path: str) -> PipelineResult:
    """
    Full processing pipeline for a document.

    1. Analyze document (classify + extract)
    2. Validate metadata
    3. Make decision

    Args:
        file_path: Path to document

    Returns:
        PipelineResult with complete analysis
    """
    timestamp = datetime.now().isoformat()

    # Step 1: Analyze document
    analysis = analyze_document(file_path)

    # Step 2: Validate metadata
    validation, metadata = validate_file(file_path, analysis)

    # Step 3: Make decision
    decision, decision_reason, is_acceptable = make_decision(analysis, validation)

    # Combine confidence
    combined_confidence = analysis.confidence * validation.confidence

    # Combine all issues
    all_errors = validation.errors.copy()
    all_warnings = analysis.warnings + validation.warnings
    all_red_flags = analysis.red_flags.copy()

    # Create result
    result = PipelineResult(
        file_path=file_path,
        file_type=analysis.file_type,
        timestamp=timestamp,
        analysis=analysis,
        validation=validation,
        decision=decision,
        decision_reason=decision_reason,
        confidence=combined_confidence,
        is_acceptable=is_acceptable,
        errors=all_errors,
        warnings=all_warnings,
        red_flags=all_red_flags,
    )

    return result


# =============================================================================
# BACKWARD COMPATIBILITY
# =============================================================================

def process_claim_document(file_path: str) -> dict:
    """
    Full processing pipeline (backward compatible, returns dict).

    Use process_document() for new code.
    """
    result = process_document(file_path)
    return result.to_dict()


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":

    import json

    file_path = "data/dsns_damage_certificate.pdf"

    print("=" * 60)
    print(" DOCUMENT VALIDATOR")
    print("=" * 60)
    print(f"File: {file_path}")
    print()

    try:
        result = process_document(file_path)

        # Print summary
        print(result.summary())
        print()

        # Print extracted data
        if result.validation and result.validation.extracted_data:
            print("📊 EXTRACTED METADATA:")
            for key, value in result.validation.extracted_data.items():
                print(f"   {key}: {value}")
            print()

        if result.analysis and result.analysis.extracted_data:
            print("📋 EXTRACTED DATA:")
            for key, value in result.analysis.extracted_data.items():
                print(f"   {key}: {value}")
            print()

        # Full JSON
        print("=" * 60)
        print(" FULL RESULT (JSON)")
        print("=" * 60)
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False, default=str))

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()