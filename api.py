"""
Document Verification API

FastAPI backend for processing compensation claim documents.

Endpoints:
- POST /upload - Upload and process single file
- POST /upload-batch - Upload and process multiple files
- GET /status/{task_id} - Get processing status
- GET /result/{task_id} - Get processing result
"""

import os
import uuid
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import uvicorn

# Import our modules
from pipeline import process_document
from models import PipelineResult, Decision


# =============================================================================
# CONFIG
# =============================================================================

UPLOAD_DIR = Path("./uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# Allowed file extensions
ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp", ".gif", ".bmp"}

# Task storage (in production, use Redis or database)
tasks: Dict[str, Dict[str, Any]] = {}

# Thread pool for CPU-bound tasks
executor = ThreadPoolExecutor(max_workers=4)


# =============================================================================
# APP
# =============================================================================

app = FastAPI(
    title="Document Verification API",
    description="API for processing and validating compensation claim documents",
    version="2.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# PYDANTIC MODELS
# =============================================================================

class TaskStatus(BaseModel):
    task_id: str
    status: str  # pending, processing, completed, error
    progress: int  # 0-100
    stage: str  # current stage description
    created_at: str
    completed_at: Optional[str] = None
    error: Optional[str] = None


class UploadResponse(BaseModel):
    task_id: str
    status: str
    message: str


class BatchUploadResponse(BaseModel):
    batch_id: str
    task_ids: List[str]
    total_files: int
    message: str


# =============================================================================
# PROCESSING LOGIC
# =============================================================================

def process_file_task(file_path: str, task_id: str) -> Dict[str, Any]:
    """Process a single file through the pipeline with progress updates."""
    start_time = datetime.now()
    path = Path(file_path)

    # Update task status
    tasks[task_id]["status"] = "processing"
    tasks[task_id]["stage"] = "Starting..."
    tasks[task_id]["progress"] = 0

    # Progress callback that updates task dict
    def on_progress(stage: str, progress: float, message: str):
        tasks[task_id]["stage"] = message or stage
        tasks[task_id]["progress"] = int(progress * 100)

    try:
        # Process using pipeline with progress callback
        result = process_document(file_path, on_progress=on_progress)

        # Calculate processing time
        processing_time = int((datetime.now() - start_time).total_seconds() * 1000)

        # Convert to dict and add extra info
        result_dict = result.to_dict()
        result_dict["task_id"] = task_id
        result_dict["file_name"] = path.name
        result_dict["processing_time_ms"] = processing_time

        # Update task
        tasks[task_id]["status"] = "completed"
        tasks[task_id]["stage"] = "Done"
        tasks[task_id]["progress"] = 100
        tasks[task_id]["completed_at"] = datetime.now().isoformat()
        tasks[task_id]["result"] = result_dict

        return result_dict

    except Exception as e:
        tasks[task_id]["status"] = "error"
        tasks[task_id]["error"] = str(e)
        tasks[task_id]["stage"] = "Error"
        raise


async def process_file_async(file_path: str, task_id: str):
    """Async wrapper for file processing."""
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            executor,
            process_file_task,
            file_path,
            task_id
        )
        return result
    except Exception as e:
        tasks[task_id]["status"] = "error"
        tasks[task_id]["error"] = str(e)
        tasks[task_id]["stage"] = "Error"
        raise


# =============================================================================
# ENDPOINTS
# =============================================================================

@app.get("/")
async def root():
    return {
        "service": "Document Verification API",
        "version": "2.0.0",
        "endpoints": {
            "POST /upload": "Upload and process single file",
            "POST /upload-batch": "Upload multiple files (parallel)",
            "GET /status/{task_id}": "Get task status",
            "GET /result/{task_id}": "Get processing result",
            "GET /batch/{batch_id}": "Get batch status",
            "POST /retry/{task_id}": "Retry a task",
            "POST /retry-batch/{batch_id}": "Retry batch (failed or all)",
            "DELETE /task/{task_id}": "Delete task and file",
            "GET /health": "Health check"
        }
    }


@app.post("/upload", response_model=UploadResponse)
async def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...)
):
    """Upload and process a single file."""

    # Validate extension
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type {ext} not allowed. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    # Generate task ID
    task_id = str(uuid.uuid4())

    # Save file
    file_path = UPLOAD_DIR / f"{task_id}_{file.filename}"
    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)

    # Initialize task
    tasks[task_id] = {
        "task_id": task_id,
        "status": "pending",
        "progress": 0,
        "stage": "Queued",
        "created_at": datetime.now().isoformat(),
        "file_name": file.filename,
        "file_path": str(file_path)
    }

    # Start processing in background
    background_tasks.add_task(process_file_async, str(file_path), task_id)

    return UploadResponse(
        task_id=task_id,
        status="pending",
        message=f"File {file.filename} queued for processing"
    )


@app.post("/upload-batch", response_model=BatchUploadResponse)
async def upload_batch(
    files: List[UploadFile] = File(...)
):
    """Upload and process multiple files in parallel."""

    batch_id = str(uuid.uuid4())
    task_ids = []
    file_tasks = []  # (file_path, task_id) pairs

    # Step 1: Save all files and initialize tasks
    for file in files:
        ext = Path(file.filename).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            continue  # Skip invalid files

        task_id = str(uuid.uuid4())
        task_ids.append(task_id)

        # Save file
        file_path = UPLOAD_DIR / f"{task_id}_{file.filename}"
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)

        # Initialize task
        tasks[task_id] = {
            "task_id": task_id,
            "batch_id": batch_id,
            "status": "pending",
            "progress": 0,
            "stage": "Queued",
            "created_at": datetime.now().isoformat(),
            "file_name": file.filename,
            "file_path": str(file_path)
        }

        file_tasks.append((str(file_path), task_id))

    # Step 2: Process all files in parallel (fire and forget)
    async def process_all():
        await asyncio.gather(
            *[process_file_async(fp, tid) for fp, tid in file_tasks],
            return_exceptions=True  # Don't fail if one task fails
        )

    # Start parallel processing without blocking response
    asyncio.create_task(process_all())

    return BatchUploadResponse(
        batch_id=batch_id,
        task_ids=task_ids,
        total_files=len(task_ids),
        message=f"{len(task_ids)} files queued for parallel processing"
    )


@app.get("/status/{task_id}", response_model=TaskStatus)
async def get_status(task_id: str):
    """Get task status."""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")

    task = tasks[task_id]
    return TaskStatus(
        task_id=task_id,
        status=task["status"],
        progress=task["progress"],
        stage=task["stage"],
        created_at=task["created_at"],
        completed_at=task.get("completed_at"),
        error=task.get("error")
    )


@app.get("/result/{task_id}")
async def get_result(task_id: str):
    """Get processing result."""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")

    task = tasks[task_id]

    if task["status"] == "pending":
        return {"status": "pending", "message": "Processing not started yet"}

    if task["status"] == "processing":
        return {
            "status": "processing",
            "progress": task["progress"],
            "stage": task["stage"]
        }

    if task["status"] == "error":
        raise HTTPException(status_code=500, detail=task.get("error", "Unknown error"))

    return task.get("result", {})


@app.get("/batch/{batch_id}")
async def get_batch_status(batch_id: str):
    """Get batch processing status."""
    batch_tasks = [t for t in tasks.values() if t.get("batch_id") == batch_id]

    if not batch_tasks:
        raise HTTPException(status_code=404, detail="Batch not found")

    completed = [t for t in batch_tasks if t["status"] == "completed"]
    errors = [t for t in batch_tasks if t["status"] == "error"]

    results = []
    summary = {Decision.ACCEPT.value: 0, Decision.REVIEW.value: 0, Decision.REJECT.value: 0}

    for task in completed:
        result = task.get("result", {})
        results.append(result)
        decision = result.get("decision", Decision.REJECT.value)
        if decision in summary:
            summary[decision] += 1

    return {
        "batch_id": batch_id,
        "total_files": len(batch_tasks),
        "completed": len(completed),
        "errors": len(errors),
        "pending": len(batch_tasks) - len(completed) - len(errors),
        "results": results,
        "summary": summary
    }


@app.delete("/task/{task_id}")
async def delete_task(task_id: str):
    """Delete task and associated file."""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")

    task = tasks[task_id]

    # Delete file
    file_path = task.get("file_path")
    if file_path and Path(file_path).exists():
        Path(file_path).unlink()

    # Delete task
    del tasks[task_id]

    return {"message": "Task deleted", "task_id": task_id}


@app.post("/retry/{task_id}")
async def retry_task(task_id: str):
    """Retry a failed or completed task."""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")

    task = tasks[task_id]

    # Check if file still exists
    file_path = task.get("file_path")
    if not file_path or not Path(file_path).exists():
        raise HTTPException(status_code=400, detail="File no longer exists, cannot retry")

    # Check if task is in a retriable state
    if task["status"] == "processing":
        raise HTTPException(status_code=400, detail="Task is already processing")

    # Reset task status
    tasks[task_id] = {
        **task,
        "status": "pending",
        "progress": 0,
        "stage": "Retrying...",
        "error": None,
        "result": None,
        "completed_at": None,
        "retry_count": task.get("retry_count", 0) + 1,
        "retried_at": datetime.now().isoformat(),
    }

    # Start processing
    asyncio.create_task(process_file_async(file_path, task_id))

    return {
        "task_id": task_id,
        "status": "pending",
        "message": f"Task restarted (attempt #{tasks[task_id]['retry_count']})"
    }


@app.post("/retry-batch/{batch_id}")
async def retry_batch(batch_id: str, only_failed: bool = True):
    """Retry all tasks in a batch.

    Args:
        batch_id: Batch ID
        only_failed: If True, only retry failed tasks. If False, retry all.
    """
    batch_tasks = [t for t in tasks.values() if t.get("batch_id") == batch_id]

    if not batch_tasks:
        raise HTTPException(status_code=404, detail="Batch not found")

    # Filter tasks to retry
    if only_failed:
        tasks_to_retry = [t for t in batch_tasks if t["status"] == "error"]
    else:
        tasks_to_retry = [t for t in batch_tasks if t["status"] != "processing"]

    if not tasks_to_retry:
        return {
            "batch_id": batch_id,
            "retried": 0,
            "message": "No tasks to retry"
        }

    # Collect file paths and task IDs
    file_tasks = []
    for task in tasks_to_retry:
        file_path = task.get("file_path")
        if file_path and Path(file_path).exists():
            task_id = task["task_id"]

            # Reset task
            tasks[task_id] = {
                **task,
                "status": "pending",
                "progress": 0,
                "stage": "Retrying...",
                "error": None,
                "result": None,
                "completed_at": None,
                "retry_count": task.get("retry_count", 0) + 1,
                "retried_at": datetime.now().isoformat(),
            }

            file_tasks.append((file_path, task_id))

    # Process all in parallel
    async def process_all():
        await asyncio.gather(
            *[process_file_async(fp, tid) for fp, tid in file_tasks],
            return_exceptions=True
        )

    asyncio.create_task(process_all())

    return {
        "batch_id": batch_id,
        "retried": len(file_tasks),
        "message": f"{len(file_tasks)} tasks restarted"
    }


# =============================================================================
# HEALTH
# =============================================================================

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "tasks_count": len(tasks),
        "tasks_by_status": {
            "pending": sum(1 for t in tasks.values() if t["status"] == "pending"),
            "processing": sum(1 for t in tasks.values() if t["status"] == "processing"),
            "completed": sum(1 for t in tasks.values() if t["status"] == "completed"),
            "error": sum(1 for t in tasks.values() if t["status"] == "error"),
        }
    }


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    uvicorn.run(
        "api:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )