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
        result.add_error(
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
            result.add_warning(
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
            result.add_warning(
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

def make_decision(
    analysis: DocumentAnalysis,
    validation: ValidationResult
) -> Tuple[str, str, bool]:
    """
    Determine processing decision based on analysis and validation.

    Args:
        analysis: DocumentAnalysis from classification/extraction
        validation: ValidationResult from metadata validation

    Returns:
        Tuple of (decision, reason, is_acceptable)
    """
    # Auto-reject conditions
    if analysis.document_type == "screenshot" or analysis.creation_method == "screenshot":
        return (Decision.REJECT.value, "Screenshot not accepted as proof", False)

    if not validation.is_valid:
        reason = validation.errors[0] if validation.errors else "Validation failed"
        return (Decision.REJECT.value, reason, False)

    # Check for images not matching claims
    if analysis.images_match_claims is False:
        return (Decision.REJECT.value, "Images do not match document claims", False)

    # Check red flags
    red_flags = analysis.red_flags
    if red_flags:
        return (Decision.REVIEW.value, f"{len(red_flags)} red flag(s) require review", False)

    # Check warnings
    warnings = analysis.warnings + validation.warnings
    if warnings:
        return (Decision.REVIEW.value, f"{len(warnings)} warning(s) require review", False)

    # Check confidence
    combined_confidence = analysis.confidence * validation.confidence
    if combined_confidence < 0.5:
        return (Decision.REVIEW.value, "Low confidence, manual verification needed", False)

    if combined_confidence >= 0.7:
        return (Decision.ACCEPT.value, "Document passed all checks", True)
    else:
        return (Decision.REVIEW.value, "Moderate confidence, verification recommended", False)


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
