"""Generic one-shot Modal GPU worker for the reusable GitHub Actions workflow."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import modal

ALLOWED_GPUS = {"T4", "L4", "A10", "A10G", "A100", "H100"}
GPU = os.environ.get("GPU_MANAGER_GPU", "T4")
TIMEOUT_SECONDS = int(os.environ.get("GPU_MANAGER_TIMEOUT", "120")) * 60

if GPU not in ALLOWED_GPUS:
    raise ValueError(f"Unsupported GPU type: {GPU}")
if not 60 <= TIMEOUT_SECONDS <= 720 * 60:
    raise ValueError("GPU_MANAGER_TIMEOUT must be between 1 and 720 minutes")

app = modal.App("gpu-manager-one-shot")

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git", "bash")
    .add_local_dir(
        ".",
        remote_path="/workspace",
        copy=True,
        ignore=[
            ".git",
            ".github",
            ".env",
            ".env.*",
            "*.pem",
            "*.key",
            "*secret*",
            "*credential*",
            ".venv",
            "venv",
            "__pycache__",
        ],
    )
)


@app.function(
    image=image,
    gpu=GPU,
    timeout=TIMEOUT_SECONDS,
    cpu=4,
    memory=16384,
)
def execute(command: str) -> int:
    """Execute the caller-provided command in the checked-out repository."""
    workdir = Path("/workspace")
    if not workdir.is_dir():
        raise RuntimeError("Workspace was not copied into the Modal image")

    print(f"GPU: {GPU}")
    print(f"Working directory: {workdir}")
    print("Starting requested workload...")

    completed = subprocess.run(
        ["bash", "-lc", command],
        cwd=str(workdir),
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"Workload exited with status {completed.returncode}")
    return completed.returncode


@app.local_entrypoint()
def main(command: str):
    """CLI entrypoint invoked by Modal from GitHub Actions."""
    print(f"Submitting one-shot job to Modal ({GPU}, timeout={TIMEOUT_SECONDS}s)")
    execute.remote(command)
    print("Remote workload completed successfully.")
