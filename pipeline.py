"""
Claims Processing Pipeline

Unified flow for processing compensation claim documents:
1. Classify document (LLM)
2. Extract details (LLM)
3. Validate metadata
4. Generate decision

Usage:
    from pipeline import process_document, process_batch

    result = process_document("photo.jpg")
    results = process_batch(["doc1.pdf", "doc2.jpg"])
"""

import json
from datetime import datetime
from pathlib import Path
from typing import List

# Import from our modules
from documents_classifier import analyze_document
from validators import validate_file, make_decision
from models import (
    DocumentAnalysis,
    ValidationResult,
    PipelineResult,
    Decision,
)


# =============================================================================
# MAIN PIPELINE
# =============================================================================

def process_document(file_path: str, verbose: bool = False) -> PipelineResult:
    """
    Process a single document through the full pipeline.

    Args:
        file_path: Path to document (image or PDF)
        verbose: Print progress messages

    Returns:
        PipelineResult with all processing data
    """
    timestamp = datetime.now().isoformat()
    path = Path(file_path)

    if verbose:
        print(f"Processing: {path.name}")

    # Step 1: Analyze document (classify + extract)
    if verbose:
        print("  → Classifying and extracting...")

    try:
        analysis = analyze_document(file_path)
    except Exception as e:
        # Handle analysis errors
        analysis = DocumentAnalysis(
            file_path=str(file_path),
            file_type="unknown",
            document_type="other",
            document_type_ua="Помилка",
            brief_description=f"Analysis error: {str(e)}",
            red_flags=["Analysis failed"],
            confidence=0,
        )

    # Step 2: Validate metadata
    if verbose:
        print("  → Validating metadata...")

    try:
        validation, metadata = validate_file(file_path, analysis)
    except Exception as e:
        validation = ValidationResult(
            file_path=str(file_path),
            validation_timestamp=timestamp
        )
        validation.add_error(f"Validation failed: {str(e)}")
        metadata = None

    # Step 3: Make decision
    if verbose:
        print("  → Making decision...")

    decision, decision_reason, is_acceptable = make_decision(analysis, validation)

    # Step 4: Calculate combined confidence
    combined_confidence = analysis.confidence * validation.confidence

    # Step 5: Compile result
    result = PipelineResult(
        file_path=str(file_path),
        file_type=analysis.file_type,
        timestamp=timestamp,
        analysis=analysis,
        validation=validation,
        decision=decision,
        decision_reason=decision_reason,
        confidence=combined_confidence,
        is_acceptable=is_acceptable,
        errors=validation.errors.copy(),
        warnings=analysis.warnings + validation.warnings,
        red_flags=analysis.red_flags.copy(),
    )

    if verbose:
        print(f"  → Done: {decision}")

    return result


def process_batch(
    file_paths: List[str],
    verbose: bool = False,
    stop_on_error: bool = False
) -> List[PipelineResult]:
    """
    Process multiple documents.

    Args:
        file_paths: List of file paths
        verbose: Print progress
        stop_on_error: Stop processing on first error

    Returns:
        List of PipelineResult
    """
    results = []

    for i, file_path in enumerate(file_paths):
        if verbose:
            print(f"\n[{i+1}/{len(file_paths)}] {Path(file_path).name}")

        try:
            result = process_document(file_path, verbose=verbose)
            results.append(result)
        except Exception as e:
            if stop_on_error:
                raise
            # Create error result
            error_result = PipelineResult(
                file_path=str(file_path),
                file_type="unknown",
                timestamp=datetime.now().isoformat(),
                analysis=None,
                validation=None,
                decision=Decision.REJECT.value,
                decision_reason=f"Processing error: {str(e)}",
                confidence=0,
                is_acceptable=False,
                errors=[str(e)],
                warnings=[],
                red_flags=[],
            )
            results.append(error_result)

    return results


def generate_report(results: List[PipelineResult]) -> str:
    """
    Generate summary report for batch processing.

    Args:
        results: List of PipelineResult

    Returns:
        Formatted report string
    """
    total = len(results)
    if total == 0:
        return "No results to report."

    accepted = sum(1 for r in results if r.decision == Decision.ACCEPT.value)
    review = sum(1 for r in results if r.decision == Decision.REVIEW.value)
    rejected = sum(1 for r in results if r.decision == Decision.REJECT.value)

    lines = [
        "=" * 60,
        " BATCH PROCESSING REPORT",
        "=" * 60,
        f"Total documents: {total}",
        f"  ✅ Accepted: {accepted} ({accepted/total*100:.1f}%)",
        f"  ⚠️ Review:   {review} ({review/total*100:.1f}%)",
        f"  ❌ Rejected: {rejected} ({rejected/total*100:.1f}%)",
        "",
        "Details:",
        "-" * 60,
    ]

    for r in results:
        lines.append(r.summary())
        lines.append("")

    return "\n".join(lines)


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    import sys


    files = ["data/akt_fake_photo.pdf"]

    print("=" * 60)
    print(" CLAIMS PROCESSING PIPELINE")
    print("=" * 60)

    if len(files) == 1:
        # Single file - detailed output
        result = process_document(files[0], verbose=True)
        print("\n" + "=" * 60)
        print(" RESULT")
        print("=" * 60)
        print(result.summary())
        print("\n" + "=" * 60)
        print(" FULL JSON")
        print("=" * 60)
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False, default=str))
    else:
        # Multiple files - batch mode
        results = process_batch(files, verbose=True)
        print("\n" + generate_report(results))

        # Save results to JSON
        output_file = "batch_results.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump([r.to_dict() for r in results], f, indent=2, ensure_ascii=False, default=str)
        print(f"\nResults saved to: {output_file}")