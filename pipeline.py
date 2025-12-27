"""
Claims Processing Pipeline

Unified flow for processing compensation claim documents:
1. Classify document (LLM)
2. Extract images and analyze (LLM)
3. Extract details (LLM)
4. Validate metadata
5. Generate decision

Usage:
    from pipeline import process_document, process_batch

    result = process_document("photo.jpg")
    results = process_batch(["doc1.pdf", "doc2.jpg"])

    # With progress callback:
    def on_progress(stage, progress, message):
        print(f"[{progress*100:.0f}%] {stage}: {message}")

    result = process_document("doc.pdf", on_progress=on_progress)
"""

import json
from datetime import datetime
from pathlib import Path
from typing import List, Callable, Optional

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

def process_document(
    file_path: str,
    verbose: bool = False,
    on_progress: Optional[Callable[[str, float, str], None]] = None
) -> PipelineResult:
    """
    Process a single document through the full pipeline.

    Args:
        file_path: Path to document (image or PDF)
        verbose: Print progress messages
        on_progress: Optional callback(stage, progress, message) for progress updates
            - stage: str - current stage name
            - progress: float - 0.0 to 1.0
            - message: str - human-readable status

    Returns:
        PipelineResult with all processing data
    """
    timestamp = datetime.now().isoformat()
    path = Path(file_path)

    def progress(stage: str, pct: float, msg: str = ""):
        if verbose:
            print(f"  [{pct*100:3.0f}%] {msg}")
        if on_progress:
            on_progress(stage, pct, msg)

    progress("start", 0.0, f"Processing {path.name}...")

    # Step 1: Analyze document (classify + extract with images)
    # This internally handles: classification → image extraction → image analysis → extraction
    try:
        # Create a wrapper to scale progress from analyze_document (0-85%) to our scale (0-80%)
        def analysis_progress(stage, pct, msg):
            # Scale: analyze_document reports 0-0.85, we want 0.05-0.80
            scaled_pct = 0.05 + (pct * 0.88)  # 0.85 * 0.88 ≈ 0.75
            progress(stage, scaled_pct, msg)

        analysis = analyze_document(file_path, on_progress=analysis_progress)

    except Exception as e:
        progress("error", 0.80, f"Analysis error: {str(e)}")
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
    progress("validation", 0.82, "Validating metadata...")

    try:
        validation, metadata = validate_file(file_path, analysis)
        progress("validation", 0.90, "Metadata validated")
    except Exception as e:
        progress("validation", 0.90, f"Validation error: {str(e)}")
        validation = ValidationResult(
            file_path=str(file_path),
            validation_timestamp=timestamp
        )
        validation.add_error(f"Validation failed: {str(e)}")
        metadata = None

    # Step 3: Make decision
    progress("decision", 0.92, "Making decision...")
    decision, decision_reason, is_acceptable = make_decision(analysis, validation)
    progress("decision", 0.95, f"Decision: {decision}")

    # Step 4: Calculate combined confidence
    combined_confidence = analysis.confidence * validation.confidence

    # Step 5: Compile result
    progress("finalizing", 0.98, "Finalizing result...")

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

    progress("done", 1.0, f"Complete: {decision}")

    return result


def process_batch(
    file_paths: List[str],
    verbose: bool = False,
    stop_on_error: bool = False,
    on_file_progress: Optional[Callable[[int, int, str, float, str], None]] = None
) -> List[PipelineResult]:
    """
    Process multiple documents.

    Args:
        file_paths: List of file paths
        verbose: Print progress
        stop_on_error: Stop processing on first error
        on_file_progress: Optional callback(file_index, total_files, stage, progress, message)

    Returns:
        List of PipelineResult
    """
    results = []
    total = len(file_paths)

    for i, file_path in enumerate(file_paths):
        if verbose:
            print(f"\n[{i+1}/{total}] {Path(file_path).name}")

        # Create per-file progress callback
        def file_progress(stage, pct, msg):
            if on_file_progress:
                on_file_progress(i, total, stage, pct, msg)

        try:
            result = process_document(file_path, verbose=verbose, on_progress=file_progress)
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

    files = sys.argv[1:] if len(sys.argv) > 1 else ["data/dsns_damage_certificate.pdf"]

    print("=" * 60)
    print(" CLAIMS PROCESSING PIPELINE")
    print("=" * 60)

    if len(files) == 1:
        # Single file - detailed output with progress
        def show_progress(stage, pct, msg):
            bar = "█" * int(pct * 20) + "░" * (20 - int(pct * 20))
            print(f"\r  [{bar}] {pct*100:3.0f}% {msg:<50}", end="", flush=True)

        result = process_document(files[0], on_progress=show_progress)
        print()  # New line after progress bar

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