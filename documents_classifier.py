"""
Document Classifier

Two-stage document analysis:
1. Classification - determine document type and creation method
2. Extraction - extract type-specific details and validate

Dependencies:
- openai
- models.py (ClassificationResult, ExtractionResult, DocumentAnalysis)
- prompts.py (CLASSIFICATION_PROMPT, extraction prompts)
"""

import os
import json
import base64
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

load_dotenv()
from openai import OpenAI

from models import (
    ClassificationResult,
    ExtractionResult,
    DocumentAnalysis,
    DocumentType,
    CreationMethod,
)
from prompts import (
    get_classification_prompt,
    PDF_CLASSIFICATION_PROMPT,
    IMAGE_CLASSIFICATION_PROMPT,
)


# =============================================================================
# CONFIGURATION
# =============================================================================

_client = None
MODEL = "gpt-4o"


def get_openai_client():
    """Get OpenAI client (lazy initialization)."""
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _client


# =============================================================================
# FILE HANDLING
# =============================================================================

def get_file_type(file_path: str) -> str:
    """Determine if file is PDF or image."""
    ext = Path(file_path).suffix.lower()
    if ext == ".pdf":
        return "pdf"
    elif ext in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".tiff", ".tif", ".bmp"}:
        return "image"
    return "unknown"


def encode_image_to_base64(image_path: str) -> str:
    """Encode image file to base64."""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def get_image_media_type(file_path: str) -> str:
    """Get MIME type for image."""
    ext = Path(file_path).suffix.lower()
    media_types = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".tiff": "image/tiff",
        ".tif": "image/tiff",
        ".bmp": "image/bmp",
    }
    return media_types.get(ext, "image/jpeg")


def get_pdf_page_count(file_path: str) -> Optional[int]:
    """Get number of pages in PDF."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(file_path)
        return len(reader.pages)
    except Exception:
        return None


# =============================================================================
# LLM CALLS
# =============================================================================

def call_llm_with_image(prompt: str, image_path: str) -> dict:
    """Call LLM with an image file."""
    base64_image = encode_image_to_base64(image_path)
    media_type = get_image_media_type(image_path)

    client = get_openai_client()
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{media_type};base64,{base64_image}"
                        }
                    }
                ]
            }
        ],
        max_tokens=2000,
        temperature=0.1,
    )

    return parse_json_response(response.choices[0].message.content)


def call_llm_with_pdf(prompt: str, pdf_path: str) -> dict:
    """Call LLM with a PDF file."""
    from pypdf import PdfReader

    reader = PdfReader(pdf_path)
    if reader.is_encrypted:
        return {}

    with open(pdf_path, "rb") as f:
        pdf_data = base64.standard_b64encode(f.read()).decode("utf-8")

    client = get_openai_client()
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "file",
                        "file": {
                            "filename": Path(pdf_path).name,
                            "file_data": f"data:application/pdf;base64,{pdf_data}",
                        }
                    }
                ]
            }
        ],
        max_tokens=2000,
        temperature=0.1,
    )

    return parse_json_response(response.choices[0].message.content)


def parse_json_response(content: str) -> dict:
    """Parse JSON from LLM response."""
    content = content.strip()

    # Remove markdown code blocks if present
    if content.startswith("```json"):
        content = content[7:]
    elif content.startswith("```"):
        content = content[3:]

    if content.endswith("```"):
        content = content[:-3]

    content = content.strip()

    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        return {"error": f"JSON parse error: {e}", "raw_content": content}


# =============================================================================
# IMAGE EXTRACTION FROM PDF
# =============================================================================

def extract_images_from_pdf(pdf_path: str, min_size: int = 100) -> dict:
    """
    Extract images from PDF using PyMuPDF.

    Args:
        pdf_path: Path to PDF file
        min_size: Minimum image dimension to include (filters out icons)

    Returns:
        Dictionary with extraction results:
        {
            "extraction_method": "embedded" | "rendered" | "mixed" | "none",
            "images": [
                {
                    "type": "embedded" | "page_render",
                    "page": int,
                    "index": int,
                    "width": int,
                    "height": int,
                    "format": str,
                    "data": bytes
                }
            ],
            "pages_with_images": [int],
            "total_images": int
        }
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return {
            "error": "PyMuPDF not installed",
            "extraction_method": "none",
            "images": [],
            "pages_with_images": [],
            "total_images": 0
        }

    doc = fitz.open(pdf_path)
    images = []
    pages_with_images = set()
    has_embedded = False

    for page_num, page in enumerate(doc):
        page_number = page_num + 1
        embedded_images = page.get_images()

        # Filter and extract embedded images
        valid_embedded = []
        for img_idx, img in enumerate(embedded_images):
            xref = img[0]
            try:
                base_image = doc.extract_image(xref)
                width = base_image["width"]
                height = base_image["height"]

                # Filter out small images (icons, logos)
                if width >= min_size and height >= min_size:
                    valid_embedded.append({
                        "type": "embedded",
                        "page": page_number,
                        "index": img_idx + 1,
                        "width": width,
                        "height": height,
                        "format": base_image["ext"],
                        "data": base_image["image"]
                    })
            except Exception:
                continue

        if valid_embedded:
            has_embedded = True
            pages_with_images.add(page_number)
            images.extend(valid_embedded)
        elif len(embedded_images) == 1:
            # Single image covering whole page = likely a scan
            # Don't add as separate image, will process as PDF
            pass

    doc.close()

    # Determine extraction method
    if has_embedded:
        method = "embedded"
    else:
        method = "none"

    return {
        "extraction_method": method,
        "images": images,
        "pages_with_images": sorted(pages_with_images),
        "total_images": len(images)
    }


def call_llm_with_images(prompt: str, images: list) -> dict:
    """
    Call LLM with multiple images for batch analysis.

    Args:
        prompt: Analysis prompt
        images: List of image dicts with "data" (bytes) and "format" fields

    Returns:
        Parsed JSON response
    """
    if not images:
        return {"error": "No images provided", "images_analyzed": 0}

    # Build content array with prompt and all images
    content = [{"type": "text", "text": prompt}]

    for i, img in enumerate(images):
        img_data = img["data"]
        img_format = img.get("format", "png")

        # Encode to base64 if bytes
        if isinstance(img_data, bytes):
            b64_data = base64.b64encode(img_data).decode("utf-8")
        else:
            b64_data = img_data

        media_type = f"image/{img_format}"
        if img_format == "jpg":
            media_type = "image/jpeg"

        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:{media_type};base64,{b64_data}"
            }
        })

    client = get_openai_client()
    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": content}],
        max_tokens=3000,
        temperature=0.1,
    )

    return parse_json_response(response.choices[0].message.content)


def analyze_pdf_images(pdf_path: str, classification_has_images: bool = True) -> Optional[dict]:
    """
    Stage 2: Extract and analyze images from PDF independently.

    Strategy:
    1. Try to extract embedded images from PDF
    2. If extraction works → analyze extracted images separately
    3. If extraction fails but classification says has_images →
       send FULL PDF with image-only analysis prompt (fallback)

    Args:
        pdf_path: Path to PDF file
        classification_has_images: Whether Stage 1 detected images

    Returns:
        Image analysis results or None if no images
    """
    from prompts import get_image_analysis_prompt

    # Try to extract embedded images
    extraction = extract_images_from_pdf(pdf_path)

    prompt = get_image_analysis_prompt()

    if extraction["total_images"] > 0:
        # SUCCESS: We extracted images - analyze them separately
        images = extraction["images"]

        # Limit to first 10 images to avoid token limits
        if len(images) > 10:
            images = images[:10]

        result = call_llm_with_images(prompt, images)

        # Add extraction metadata
        result["extraction_method"] = extraction["extraction_method"]
        result["pages_with_images"] = extraction["pages_with_images"]

        return result

    elif classification_has_images:
        # FALLBACK: Extraction failed but classification says there are images
        # Send full PDF with image-analysis prompt
        # LLM will see the PDF and analyze images within it

        fallback_prompt = """⚠️ CRITICAL: IMAGE-ONLY ANALYSIS MODE ⚠️

You are analyzing ONLY the PHOTOGRAPHS/PICTURES in this PDF.

STRICT RULES:
1. COMPLETELY IGNORE all text in the document
2. DO NOT read or consider any written claims about damage
3. DO NOT let text descriptions influence your image analysis
4. Pretend you CANNOT read - you can only SEE images

WHAT TO ANALYZE:
- Only photographs, pictures, photos embedded in the document
- NOT: logos, stamps, seals, signatures, diagrams, form graphics

FOR EACH PHOTO, describe:
- What you LITERALLY SEE in the image
- Physical condition of what's shown
- If damage visible: describe the ACTUAL damage you see with your eyes
- If NO damage visible: say "no visible damage" even if text claims otherwise

REMEMBER: Your image descriptions will be compared against text claims.
You must describe images INDEPENDENTLY and OBJECTIVELY.
If you see a clean room - say it's clean, regardless of what text might claim.

""" + prompt

        result = call_llm_with_pdf(fallback_prompt, pdf_path)

        # Mark as fallback method
        result["extraction_method"] = "pdf_fallback"
        result["extraction_note"] = "Could not extract embedded images, analyzed PDF directly"

        return result

    else:
        # No images detected
        return None


# =============================================================================
# STAGE 1: CLASSIFICATION
# =============================================================================

def classify_document(file_path: str) -> ClassificationResult:
    """
    Stage 1: Classify document type and creation method.

    Args:
        file_path: Path to PDF or image file

    Returns:
        ClassificationResult with document_type, creation_method, etc.
    """
    file_type = get_file_type(file_path)

    # Get appropriate classification prompt
    classification_prompt = get_classification_prompt(file_type)

    if file_type == "pdf":
        response = call_llm_with_pdf(classification_prompt, file_path)
    elif file_type == "image":
        response = call_llm_with_image(classification_prompt, file_path)
    else:
        return ClassificationResult(
            document_type="other",
            document_type_ua="Невідомий формат",
            creation_method="unknown",
            brief_description=f"Unknown file type: {file_type}",
            classification_confidence=0.0,
            red_flags=["Unknown file format"],
        )

    if "error" in response:
        return ClassificationResult(
            document_type="other",
            document_type_ua="Помилка обробки",
            creation_method="unknown",
            brief_description=response.get("error", "Unknown error"),
            classification_confidence=0.0,
            red_flags=["Classification failed"],
            _raw_response=response,
        )

    # For images, map 'category' to 'document_type'
    if file_type == "image" and "category" in response:
        response["document_type"] = response.get("category", "other")
        response["document_type_ua"] = response.get("category_ua", "Інше")
        # Images don't have creation_method in the same way
        response["creation_method"] = "original_photo"
        if response.get("document_type") == "screenshot":
            response["creation_method"] = "screenshot"
        # Preserve image-specific classification fields
        # These are already in response: shows_damage, damage_severity, damage_description

    return ClassificationResult.from_dict(response)


# =============================================================================
# STAGE 3: EXTRACTION
# =============================================================================

def extract_details_with_images(
    file_path: str,
    document_type: str,
    image_analysis: Optional[dict] = None
) -> Optional[ExtractionResult]:
    """
    Stage 3: Extract details with image analysis context.

    This is the main extraction function that supports cross-validation
    between document text and image analysis results.

    Args:
        file_path: Path to document
        document_type: Type from classification
        image_analysis: Results from Stage 2 (or None)

    Returns:
        ExtractionResult with cross-validation
    """
    from prompts import get_extraction_prompt_with_images

    file_type = get_file_type(file_path)

    # Get prompt with image analysis injected
    prompt = get_extraction_prompt_with_images(
        document_type=document_type,
        file_type=file_type,
        image_analysis=image_analysis
    )

    if not prompt:
        return None

    # Call LLM
    if file_type == "pdf":
        response = call_llm_with_pdf(prompt, file_path)
    else:
        response = call_llm_with_image(prompt, file_path)

    if "error" in response:
        return ExtractionResult(
            content_summary=response.get("error", "Extraction failed"),
            red_flags=["Detail extraction failed"],
            extraction_confidence=0.0,
            _raw_response=response,
        )

    # Convert to ExtractionResult
    return ExtractionResult.from_dict(response, document_type, file_type)


def extract_details(file_path: str, document_type: str) -> Optional[ExtractionResult]:
    """
    Stage 3: Extract type-specific details (without image analysis).

    This is a backward-compatible wrapper. For full functionality with
    image cross-validation, use extract_details_with_images() directly.

    Args:
        file_path: Path to PDF or image file
        document_type: Document type or category from classification

    Returns:
        ExtractionResult with extracted details, or None if no prompt available
    """
    return extract_details_with_images(
        file_path=file_path,
        document_type=document_type,
        image_analysis=None
    )


# =============================================================================
# MAIN FUNCTION: ANALYZE DOCUMENT
# =============================================================================

def analyze_document(file_path: str, skip_extraction: bool = False) -> DocumentAnalysis:
    """
    Analyze document through classification, image analysis, and extraction stages.

    Three-stage process:
    1. Classification - determine document type, check if has images
    2. Image Analysis - if has images, analyze them INDEPENDENTLY (no text)
    3. Extraction - extract details, using image analysis as FACTS for cross-validation

    Args:
        file_path: Path to PDF or image file
        skip_extraction: If True, only run classification (faster)

    Returns:
        DocumentAnalysis with combined results
    """
    from prompts import get_extraction_prompt_with_images

    file_type = get_file_type(file_path)
    page_count = None

    if file_type == "pdf":
        page_count = get_pdf_page_count(file_path)

    # =========================================================================
    # STAGE 1: Classification
    # =========================================================================
    classification = classify_document(file_path)

    # Check if document has images (from classification)
    has_images = getattr(classification, 'has_images', False) or \
                 classification.__dict__.get('has_images', False)

    # Also check raw response if available
    if hasattr(classification, '_raw_response'):
        has_images = classification._raw_response.get('has_images', has_images)

    # =========================================================================
    # STAGE 2: Image Analysis (if has images and PDF)
    # =========================================================================
    image_analysis = None

    if file_type == "pdf" and has_images and not skip_extraction:
        try:
            image_analysis = analyze_pdf_images(
                pdf_path=file_path,
                classification_has_images=has_images
            )
        except Exception as e:
            # Log but don't fail - continue without image analysis
            print(f"Warning: Image analysis failed: {e}")
            image_analysis = None

    # =========================================================================
    # STAGE 3: Extraction with image analysis context
    # =========================================================================
    extraction = None

    if not skip_extraction:
        extraction = extract_details_with_images(
            file_path=file_path,
            document_type=classification.document_type,
            image_analysis=image_analysis
        )

    # =========================================================================
    # Combine results
    # =========================================================================
    analysis = DocumentAnalysis.from_stages(
        file_path=file_path,
        file_type=file_type,
        classification=classification,
        extraction=extraction,
        page_count=page_count,
    )

    # Add image analysis to result if available
    if image_analysis:
        analysis.image_analysis = image_analysis

        # Check for cross-validation issues
        if extraction and hasattr(extraction, 'cross_validation'):
            cv = extraction.cross_validation
            if cv and cv.get('match_status') == 'mismatch':
                if "Images don't match text claims" not in analysis.red_flags:
                    analysis.red_flags.append("Images don't match text claims")
                    mismatch_detail = cv.get('mismatch_details')
                    if mismatch_detail:
                        analysis.red_flags.append(f"Mismatch: {mismatch_detail}")

    return analysis




# =============================================================================
# CONVENIENCE FUNCTIONS (backward compatibility)
# =============================================================================

def classify_file(file_path: str) -> dict:
    """
    Backward compatible function - returns dict.

    Use analyze_document() for new code.
    """
    analysis = analyze_document(file_path)

    # Return dict in old format
    return {
        "_file_type": analysis.file_type,
        "document_type": analysis.document_type,
        "document_type_ua": analysis.document_type_ua,
        "creation_method": analysis.creation_method,
        "description": analysis.brief_description,
        "content_summary": analysis.content_summary,
        "document_date": analysis.document_date,
        "issuing_authority": analysis.issuing_authority,
        "has_stamp": analysis.has_stamp,
        "has_signature": analysis.has_signature,
        "has_letterhead": analysis.has_letterhead,
        "has_images": analysis.has_images,
        "images_description": analysis.images_description,
        "images_match_claims": analysis.images_match_claims,
        "confidence": analysis.confidence,
        "red_flags": analysis.red_flags,
        "warnings": analysis.warnings,
        **analysis.extracted_data,  # Include type-specific data
    }


def classify_image(image_path: str) -> dict:
    """Classify an image file (backward compatible)."""
    return classify_file(image_path)


def classify_pdf(pdf_path: str) -> dict:
    """Classify a PDF file (backward compatible)."""
    return classify_file(pdf_path)


# =============================================================================
# PROCESSING RULES (for validators.py compatibility)
# =============================================================================

def get_image_processing_rules(category: str) -> dict:
    """Get validation rules based on image category."""

    base_rules = {
        "check_gps": True,
        "check_date": True,
        "check_device": True,
        "check_editing_software": True,
        "check_resolution": True,
    }

    category_rules = {
        "damage_photo": {
            **base_rules,
            "require_gps": True,
            "require_date": True,
        },
        "property_exterior": {
            **base_rules,
            "require_gps": False,
            "require_date": False,
        },
        "property_interior": {
            **base_rules,
            "require_gps": False,
            "require_date": False,
        },
        "document_photo": {
            **base_rules,
            "check_gps": False,  # Documents don't need GPS
            "require_date": False,
            "require_gps": False,
        },
        "identity_photo": {
            **base_rules,
            "check_gps": False,
            "require_date": False,
            "require_gps": False,
        },
        "before_after": {
            **base_rules,
            "require_gps": False,
            "require_date": False,
        },
        "screenshot": {
            "auto_reject": True,
            "reason": "Screenshots are not accepted as proof",
        },
        "other": base_rules,
    }

    return category_rules.get(category, base_rules)


def get_pdf_processing_rules(document_type: str, creation_method: str) -> dict:
    """Get validation rules based on PDF type and creation method."""

    base_rules = {
        "check_modification": True,
        "check_producer": True,
        "check_encryption": True,
    }

    # Screenshot PDFs are always rejected
    if creation_method == "screenshot":
        return {
            "auto_reject": True,
            "reason": "Screenshot PDFs are not accepted",
        }

    # Type-specific rules
    type_rules = {
        "official_certificate": {
            **base_rules,
            "require_stamp": True,
            "require_signature": True,
            "require_letterhead": True,
        },
        "damage_act": {
            **base_rules,
            "require_stamp": False,  # OSBB stamp optional
            "require_signature": True,
            "min_signatures": 2,
        },
        "photo_collection": {
            **base_rules,
            "require_stamp": False,
            "require_signature": False,
            "check_images": True,
        },
        "identity_document": {
            **base_rules,
            "require_photo": True,
        },
        "property_document": {
            **base_rules,
            "require_stamp": True,
        },
        "utility_bill": {
            **base_rules,
            "require_stamp": False,
            "require_signature": False,
        },
    }

    return type_rules.get(document_type, base_rules)


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    import sys

    file_path = "data/dsns_damage_certificate.pdf"

    print(f"Analyzing: {file_path}")
    print("=" * 50)

    analysis = analyze_document(file_path)

    print(f"Document Type: {analysis.document_type}")
    print(f"Type (UA): {analysis.document_type_ua}")
    print(f"Creation Method: {analysis.creation_method}")
    print(f"Description: {analysis.brief_description}")
    print(f"Confidence: {analysis.confidence:.0%}")
    print()

    print("Official Elements:")
    print(f"  Stamp: {'✓' if analysis.has_stamp else '—'}")
    print(f"  Signature: {'✓' if analysis.has_signature else '—'}")
    print(f"  Letterhead: {'✓' if analysis.has_letterhead else '—'}")
    print()

    if analysis.red_flags:
        print("🚩 Red Flags:")
        for flag in analysis.red_flags:
            print(f"  • {flag}")
        print()

    if analysis.warnings:
        print("⚠️ Warnings:")
        for warn in analysis.warnings:
            print(f"  • {warn}")
        print()

    if analysis.extracted_data:
        print("📋 Extracted Data:")
        for key, value in analysis.extracted_data.items():
            print(f"  {key}: {value}")

    print()
    print("Full JSON:")
    print(json.dumps(analysis.to_dict(), indent=2, ensure_ascii=False))