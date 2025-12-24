"""
Data Models for Document Classification and Validation

Defines common structures for:
- Classification results (Stage 1)
- Extraction results (Stage 2)
- Combined document analysis
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from enum import Enum


# =============================================================================
# ENUMS
# =============================================================================

class DocumentType(str, Enum):
    """Document type categories (for PDFs)."""
    OFFICIAL_CERTIFICATE = "official_certificate"
    DAMAGE_ACT = "damage_act"
    PHOTO_COLLECTION = "photo_collection"
    IDENTITY_DOCUMENT = "identity_document"
    PROPERTY_DOCUMENT = "property_document"
    FINANCIAL_STATEMENT = "financial_statement"
    COURT_DECISION = "court_decision"
    REGISTRATION_EXTRACT = "registration_extract"
    MEDICAL_RECORD = "medical_record"
    UTILITY_BILL = "utility_bill"
    APPLICATION_FORM = "application_form"
    OTHER = "other"


class ImageCategory(str, Enum):
    """Image category (for photos)."""
    DAMAGE_PHOTO = "damage_photo"
    PROPERTY_EXTERIOR = "property_exterior"
    PROPERTY_INTERIOR = "property_interior"
    DOCUMENT_PHOTO = "document_photo"
    IDENTITY_PHOTO = "identity_photo"
    BEFORE_AFTER = "before_after"
    SCREENSHOT = "screenshot"
    OTHER = "other"


class CreationMethod(str, Enum):
    """How the document was created/captured."""
    SCANNED = "scanned"
    DIGITAL_NATIVE = "digital_native"
    PHOTO_CONVERTED = "photo_converted"
    SCREENSHOT = "screenshot"
    UNKNOWN = "unknown"


class Decision(str, Enum):
    """Final processing decision."""
    ACCEPT = "ACCEPT"
    REVIEW = "REVIEW"
    REJECT = "REJECT"


# =============================================================================
# STAGE 1: CLASSIFICATION
# =============================================================================

@dataclass
class ClassificationResult:
    """
    Stage 1 output: Document classification.

    Determines WHAT type of document this is and HOW it was created.
    """
    document_type: str = "other"
    document_type_ua: str = "Інше"
    creation_method: str = "unknown"
    brief_description: str = ""
    classification_confidence: float = 0.0
    classification_reasoning: str = ""
    red_flags: List[str] = field(default_factory=list)

    # Image detection (from Stage 1 classification)
    has_images: bool = False
    images_count: int = 0
    images_pages: List[int] = field(default_factory=list)

    # Image-specific fields (for image files, not PDFs)
    shows_damage: Optional[bool] = None
    damage_severity: Optional[str] = None
    damage_description: Optional[str] = None

    # Raw response for debugging
    _raw_response: Optional[Dict] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ClassificationResult":
        """Create from LLM response dict."""
        return cls(
            document_type=data.get("document_type", "other"),
            document_type_ua=data.get("document_type_ua", "Інше"),
            creation_method=data.get("creation_method", "unknown"),
            brief_description=data.get("brief_description", ""),
            classification_confidence=data.get("classification_confidence", 0.0),
            classification_reasoning=data.get("classification_reasoning", ""),
            red_flags=data.get("red_flags", []),
            has_images=data.get("has_images", False),
            images_count=data.get("images_count", 0),
            images_pages=data.get("images_pages", []),
            shows_damage=data.get("shows_damage"),
            damage_severity=data.get("damage_severity"),
            damage_description=data.get("damage_description"),
            _raw_response=data
        )

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "document_type": self.document_type,
            "document_type_ua": self.document_type_ua,
            "creation_method": self.creation_method,
            "brief_description": self.brief_description,
            "classification_confidence": self.classification_confidence,
            "classification_reasoning": self.classification_reasoning,
            "red_flags": self.red_flags,
            "has_images": self.has_images,
            "images_count": self.images_count,
            "images_pages": self.images_pages,
        }
        # Add image-specific fields if present
        if self.shows_damage is not None:
            result["shows_damage"] = self.shows_damage
        if self.damage_severity is not None:
            result["damage_severity"] = self.damage_severity
        if self.damage_description is not None:
            result["damage_description"] = self.damage_description
        return result


# =============================================================================
# STAGE 2: EXTRACTION
# =============================================================================

@dataclass
class ExtractionResult:
    """
    Stage 2 output: Detail extraction.

    Contains common fields + type-specific data in extracted_data dict.
    """
    # Content summary
    content_summary: str = ""
    document_date: Optional[str] = None

    # Official elements (common across types)
    has_stamp: bool = False
    has_signature: bool = False
    has_letterhead: bool = False
    issuing_authority: Optional[str] = None

    # Images
    has_images: bool = False
    images_count: int = 0
    images_description: List[str] = field(default_factory=list)
    images_match_claims: Optional[bool] = None

    # Validation results
    red_flags: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    extraction_confidence: float = 0.0

    # Type-specific data (varies by document_type)
    extracted_data: Dict[str, Any] = field(default_factory=dict)

    # Raw response for debugging
    _raw_response: Optional[Dict] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any], document_type: str, file_type: str = "pdf") -> "ExtractionResult":
        """Create from LLM response dict, extracting common and type-specific fields."""

        if file_type == "image":
            # Image-specific field mapping
            result = cls(
                content_summary=data.get("content_summary", data.get("damage_description", "")),
                document_date=data.get("document_date_visible"),
                # Map image fields to common fields
                has_stamp=data.get("has_visible_stamp", False),
                has_signature=data.get("has_visible_signature", False),
                has_letterhead=data.get("has_visible_letterhead", False),
                issuing_authority=None,
                # Image IS the content
                has_images=True,
                images_count=1,
                images_description=[data.get("content_summary", data.get("damage_description", ""))],
                images_match_claims=data.get("appears_authentic"),
                red_flags=data.get("red_flags", []),
                warnings=data.get("warnings", []),
                extraction_confidence=data.get("extraction_confidence", 0.0),
                _raw_response=data
            )
        else:
            # PDF field mapping
            # Handle has_stamp: check multiple possible fields
            has_stamp = data.get("has_stamp", False)
            if not has_stamp:
                # For damage_act: check osbb_stamp or government_stamp
                has_stamp = data.get("has_osbb_stamp", False) or data.get("has_government_stamp", False)

            result = cls(
                content_summary=data.get("content_summary", ""),
                document_date=data.get("document_date"),
                has_stamp=has_stamp,
                has_signature=data.get("has_signature", data.get("has_signatures", False)),
                has_letterhead=data.get("has_letterhead", False),
                issuing_authority=data.get("issuing_authority"),
                has_images=data.get("has_images", False),
                images_count=data.get("images_count", 0),
                images_description=data.get("images_description", []),
                images_match_claims=data.get("images_match_claims"),
                red_flags=data.get("red_flags", []),
                warnings=data.get("warnings", []),
                extraction_confidence=data.get("extraction_confidence", 0.0),
                _raw_response=data
            )

        # Extract type-specific data
        result.extracted_data = cls._extract_type_specific(data, document_type)

        return result

    @staticmethod
    def _extract_type_specific(data: Dict[str, Any], document_type: str) -> Dict[str, Any]:
        """Extract type-specific fields based on document type or image category."""

        type_specific = {}

        # ===================
        # PDF DOCUMENT TYPES
        # ===================

        if document_type == "official_certificate":
            type_specific = {
                "document_number": data.get("document_number"),
                "letterhead_authority": data.get("letterhead_authority"),
                "stamp_authority": data.get("stamp_authority"),
                "stamp_location": data.get("stamp_location"),
                "signatures_count": data.get("signatures_count", 0),
                "signatures_have_titles": data.get("signatures_have_titles", False),
                "signatures_details": data.get("signatures_details", []),
            }

        elif document_type == "damage_act":
            type_specific = {
                "property_address": data.get("property_address"),
                "owner_name": data.get("owner_name"),
                "damage_date": data.get("damage_date"),
                "act_date": data.get("act_date"),
                "damage_description": data.get("damage_description"),
                "damage_cause": data.get("damage_cause"),
                "witnesses_count": data.get("witnesses_count", 0),
                "witnesses_names": data.get("witnesses_names", []),
                "signatures_count": data.get("signatures_count", 0),
                "has_osbb_stamp": data.get("has_osbb_stamp", False),
                "osbb_name": data.get("osbb_name"),
                "has_government_stamp": data.get("has_government_stamp", False),
            }

        elif document_type == "photo_collection":
            type_specific = {
                "photo_count": data.get("photo_count", 0),
                "photos_analysis": data.get("photos_analysis", []),
                "overall_damage_visible": data.get("overall_damage_visible", False),
                "damage_types_found": data.get("damage_types_found", []),
                "appears_to_be_same_location": data.get("appears_to_be_same_location"),
                "screenshots_detected": data.get("screenshots_detected", False),
                "editing_signs_detected": data.get("editing_signs_detected", False),
            }

        elif document_type == "identity_document":
            type_specific = {
                "document_subtype": data.get("document_subtype"),
                "country": data.get("country"),
                "holder_name": data.get("holder_name"),
                "date_of_birth": data.get("date_of_birth"),
                "document_number": data.get("document_number"),
                "issue_date": data.get("issue_date"),
                "expiry_date": data.get("expiry_date"),
                "has_photo": data.get("has_photo", False),
                "photo_appears_genuine": data.get("photo_appears_genuine"),
                "data_readable": data.get("data_readable", True),
            }

        elif document_type == "property_document":
            type_specific = {
                "property_address": data.get("property_address"),
                "property_type": data.get("property_type"),
                "property_area": data.get("property_area"),
                "owner_names": data.get("owner_names", []),
                "ownership_shares": data.get("ownership_shares", []),
                "document_number": data.get("document_number"),
                "registry_name": data.get("registry_name"),
                "has_qr_code": data.get("has_qr_code", False),
            }

        elif document_type in ("utility_bill", "financial_statement"):
            type_specific = {
                "provider_name": data.get("provider_name"),
                "service_type": data.get("service_type"),
                "service_address": data.get("service_address"),
                "account_number": data.get("account_number"),
                "account_holder": data.get("account_holder"),
                "billing_period": data.get("billing_period"),
                "amount": data.get("amount"),
                "currency": data.get("currency"),
            }

        # ===================
        # IMAGE CATEGORIES
        # ===================

        elif document_type == "damage_photo":
            type_specific = {
                "damage_type": data.get("damage_type", []),
                "damaged_objects": data.get("damaged_objects", []),
                "location_in_building": data.get("location_in_building"),
                "damage_cause": data.get("damage_cause"),
                "damage_severity": data.get("damage_severity"),
                "damage_description": data.get("damage_description"),
                "appears_authentic": data.get("appears_authentic", True),
                "authenticity_concerns": data.get("authenticity_concerns", []),
            }

        elif document_type in ("property_exterior", "property_interior", "before_after"):
            type_specific = {
                "property_type": data.get("property_type"),
                "location_description": data.get("location_description"),
                "condition": data.get("condition"),
                "visible_damage": data.get("visible_damage", False),
                "damage_description": data.get("damage_description"),
                "visible_address": data.get("visible_address"),
                "identifiable_features": data.get("identifiable_features", []),
                "appears_authentic": data.get("appears_authentic", True),
                "photo_quality": data.get("photo_quality"),
            }

        elif document_type == "document_photo":
            type_specific = {
                "document_type_visible": data.get("document_type_visible"),
                "text_readable": data.get("text_readable", False),
                "key_information": data.get("key_information"),
                "visible_stamps": data.get("visible_stamps", False),
                "visible_signatures": data.get("visible_signatures", False),
                "photo_quality": data.get("photo_quality"),
                "perspective_issues": data.get("perspective_issues", False),
            }

        elif document_type == "identity_photo":
            type_specific = {
                "photo_type": data.get("photo_type"),
                "face_visible": data.get("face_visible", False),
                "document_type_if_id": data.get("document_type_if_id"),
                "readable_data": data.get("readable_data", {}),
                "appears_authentic": data.get("appears_authentic", True),
            }

        elif document_type == "screenshot":
            type_specific = {
                "screenshot_source": data.get("screenshot_source"),
                "content_shown": data.get("content_shown"),
                "contains_relevant_info": data.get("contains_relevant_info", False),
                "info_description": data.get("info_description"),
            }

        # Remove None values
        return {k: v for k, v in type_specific.items() if v is not None}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "content_summary": self.content_summary,
            "document_date": self.document_date,
            "has_stamp": self.has_stamp,
            "has_signature": self.has_signature,
            "has_letterhead": self.has_letterhead,
            "issuing_authority": self.issuing_authority,
            "has_images": self.has_images,
            "images_count": self.images_count,
            "images_description": self.images_description,
            "images_match_claims": self.images_match_claims,
            "red_flags": self.red_flags,
            "warnings": self.warnings,
            "extraction_confidence": self.extraction_confidence,
            "extracted_data": self.extracted_data,
        }


# =============================================================================
# COMBINED ANALYSIS
# =============================================================================

@dataclass
class DocumentAnalysis:
    """
    Combined result from classification + extraction stages.

    This is the main output of the document analysis pipeline.
    """
    # File info
    file_path: str = ""
    file_type: str = ""  # "pdf" or "image"
    page_count: Optional[int] = None

    # Stage 1: Classification
    document_type: str = "other"
    document_type_ua: str = "Інше"
    creation_method: str = "unknown"
    brief_description: str = ""
    classification_confidence: float = 0.0

    # Image-specific classification (from Stage 1)
    shows_damage: Optional[bool] = None
    damage_severity: Optional[str] = None

    # Stage 2: Image Analysis (independent)
    image_analysis: Optional[Dict[str, Any]] = None

    # Stage 3: Extraction (common fields)
    content_summary: str = ""
    document_date: Optional[str] = None
    issuing_authority: Optional[str] = None

    # Official elements
    has_stamp: bool = False
    has_signature: bool = False
    has_letterhead: bool = False

    # Images
    has_images: bool = False
    images_count: int = 0
    images_description: List[str] = field(default_factory=list)
    images_match_claims: Optional[bool] = None

    # Cross-validation (text vs images)
    cross_validation: Optional[Dict[str, Any]] = None

    # Combined confidence (classification * extraction)
    confidence: float = 0.0
    extraction_confidence: float = 0.0

    # All issues (combined from both stages)
    red_flags: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    # Type-specific extracted data
    extracted_data: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_stages(
        cls,
        file_path: str,
        file_type: str,
        classification: ClassificationResult,
        extraction: Optional[ExtractionResult] = None,
        page_count: Optional[int] = None
    ) -> "DocumentAnalysis":
        """Create from classification and extraction results."""

        # Start with classification data
        result = cls(
            file_path=file_path,
            file_type=file_type,
            page_count=page_count,
            document_type=classification.document_type,
            document_type_ua=classification.document_type_ua,
            creation_method=classification.creation_method,
            brief_description=classification.brief_description,
            classification_confidence=classification.classification_confidence,
            # Image-specific from classification
            shows_damage=classification.shows_damage,
            damage_severity=classification.damage_severity,
            red_flags=list(classification.red_flags),
        )

        # Add extraction data if available
        if extraction:
            result.content_summary = extraction.content_summary
            result.document_date = extraction.document_date
            result.issuing_authority = extraction.issuing_authority
            result.has_stamp = extraction.has_stamp
            result.has_signature = extraction.has_signature
            result.has_letterhead = extraction.has_letterhead
            result.has_images = extraction.has_images
            result.images_count = extraction.images_count
            result.images_description = extraction.images_description
            result.images_match_claims = extraction.images_match_claims
            result.extraction_confidence = extraction.extraction_confidence
            result.extracted_data = extraction.extracted_data

            # Combine red flags and warnings
            result.red_flags.extend(extraction.red_flags)
            result.warnings = extraction.warnings

            # Calculate combined confidence
            result.confidence = classification.classification_confidence * extraction.extraction_confidence
        else:
            result.confidence = classification.classification_confidence
            result.extraction_confidence = 0.0

        # Deduplicate red flags
        result.red_flags = list(dict.fromkeys(result.red_flags))

        return result

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "file_path": self.file_path,
            "file_type": self.file_type,
            "page_count": self.page_count,
            "document_type": self.document_type,
            "document_type_ua": self.document_type_ua,
            "creation_method": self.creation_method,
            "brief_description": self.brief_description,
            "content_summary": self.content_summary,
            "document_date": self.document_date,
            "issuing_authority": self.issuing_authority,
            "has_stamp": self.has_stamp,
            "has_signature": self.has_signature,
            "has_letterhead": self.has_letterhead,
            "has_images": self.has_images,
            "images_count": self.images_count,
            "images_description": self.images_description,
            "images_match_claims": self.images_match_claims,
            "confidence": round(self.confidence, 3),
            "classification_confidence": round(self.classification_confidence, 3),
            "extraction_confidence": round(self.extraction_confidence, 3),
            "red_flags": self.red_flags,
            "warnings": self.warnings,
            "extracted_data": self.extracted_data,
        }
        # Add image-specific fields if present
        if self.shows_damage is not None:
            result["shows_damage"] = self.shows_damage
        if self.damage_severity is not None:
            result["damage_severity"] = self.damage_severity
        # Add image analysis if present
        if self.image_analysis is not None:
            result["image_analysis"] = self.image_analysis
        # Add cross-validation if present
        if self.cross_validation is not None:
            result["cross_validation"] = self.cross_validation
        return result


# =============================================================================
# VALIDATION RESULT (from validators.py - kept for compatibility)
# =============================================================================

@dataclass
class ValidationResult:
    """Result of metadata validation checks."""

    is_valid: bool = True
    confidence: float = 1.0

    # Issues by severity
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    info: List[str] = field(default_factory=list)

    # Detailed checks
    checks_passed: List[str] = field(default_factory=list)
    checks_failed: List[str] = field(default_factory=list)

    # Extracted metadata
    extracted_data: Dict[str, Any] = field(default_factory=dict)

    # Processing info
    file_path: str = ""
    validation_timestamp: str = ""
    rules_applied: List[str] = field(default_factory=list)

    def add_error(self, message: str, check_name: str = None):
        """Add blocking error."""
        self.errors.append(message)
        self.is_valid = False
        self.confidence = 0
        if check_name:
            self.checks_failed.append(check_name)

    def add_warning(self, message: str, check_name: str = None):
        """Add warning (doesn't block but flags for review)."""
        self.warnings.append(message)
        self.confidence *= 0.8
        if check_name:
            self.checks_failed.append(check_name)

    def add_info(self, message: str):
        """Add informational message."""
        self.info.append(message)

    def pass_check(self, check_name: str, message: str = None):
        """Record passed check."""
        self.checks_passed.append(check_name)
        if message:
            self.info.append(message)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "confidence": round(self.confidence, 2),
            "errors": self.errors,
            "warnings": self.warnings,
            "info": self.info,
            "checks_passed": self.checks_passed,
            "checks_failed": self.checks_failed,
            "extracted_data": self.extracted_data,
            "file_path": self.file_path,
            "validation_timestamp": self.validation_timestamp,
            "rules_applied": self.rules_applied,
        }


# =============================================================================
# PIPELINE RESULT
# =============================================================================

@dataclass
class PipelineResult:
    """
    Final output of the complete processing pipeline.

    Combines: DocumentAnalysis + ValidationResult + Decision
    """
    # File info
    file_path: str = ""
    file_type: str = ""
    timestamp: str = ""

    # Document analysis (from LLM)
    analysis: Optional[DocumentAnalysis] = None

    # Metadata validation
    validation: Optional[ValidationResult] = None

    # Final decision
    decision: str = "REVIEW"
    decision_reason: str = ""
    confidence: float = 0.0
    is_acceptable: bool = False

    # Combined issues
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    red_flags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_path": self.file_path,
            "file_type": self.file_type,
            "timestamp": self.timestamp,
            "analysis": self.analysis.to_dict() if self.analysis else None,
            "validation": self.validation.to_dict() if self.validation else None,
            "decision": self.decision,
            "decision_reason": self.decision_reason,
            "confidence": round(self.confidence, 3),
            "is_acceptable": self.is_acceptable,
            "errors": self.errors,
            "warnings": self.warnings,
            "red_flags": self.red_flags,
        }

    def summary(self) -> str:
        """Human-readable summary."""
        icon = {"ACCEPT": "✅", "REVIEW": "⚠️", "REJECT": "❌"}.get(self.decision, "❓")

        lines = [
            f"{icon} {self.decision}: {self.decision_reason}",
            f"   Confidence: {self.confidence:.0%}",
            f"   File: {self.file_path}",
        ]

        if self.errors:
            lines.append(f"   Errors: {len(self.errors)}")
        if self.warnings:
            lines.append(f"   Warnings: {len(self.warnings)}")
        if self.red_flags:
            lines.append(f"   Red flags: {len(self.red_flags)}")

        return "\n".join(lines)