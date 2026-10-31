"""One-shot Modal worker used by the reusable GPU-Manager workflow.

Only files inside .gpu-manager-transfer are guaranteed to be returned to GitHub Actions.
"""
from __future__ import annotations

import os
import re
import subprocess
import tarfile
from pathlib import Path

import modal

ALLOWED_GPUS = {"T4", "L4", "A10", "L40S", "A100", "H100"}
GPU = os.environ.get("GPU_MANAGER_GPU", "T4")
TIMEOUT_MINUTES = int(os.environ.get("GPU_MANAGER_TIMEOUT", "120"))
TIMEOUT_SECONDS = TIMEOUT_MINUTES * 60

if GPU not in ALLOWED_GPUS:
    raise ValueError(f"Unsupported GPU type: {GPU}")
if not 1 <= TIMEOUT_MINUTES <= 345:
    raise ValueError("GPU_MANAGER_TIMEOUT must be between 1 and 345 minutes")

TRANSFER_VOLUME = modal.Volume.from_name("gpu-manager-transfer", create_if_missing=True)
app = modal.App("gpu-manager-one-shot")

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git", "bash", "tar")
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
            ".gpu_manager_worker.py",
        ],
    )
)


def validate_transfer_key(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", value):
        raise ValueError("transfer_key contains unsupported characters")
    return value


def persist_transfer_files(transfer_key: str) -> None:
    source_dir = Path("/workspace/.gpu-manager-transfer")
    source_dir.mkdir(parents=True, exist_ok=True)

    destination_dir = Path("/transfer") / transfer_key
    destination_dir.mkdir(parents=True, exist_ok=True)
    archive_path = destination_dir / "outputs.tar.gz"
    if archive_path.exists():
        archive_path.unlink()

    with tarfile.open(archive_path, mode="w:gz") as archive:
        for child in source_dir.iterdir():
            archive.add(child, arcname=child.name, recursive=True)

    # Volume writes must be committed to become visible to the GitHub runner.
    TRANSFER_VOLUME.commit()
    print(f"Committed transfer files for run {transfer_key}")


@app.function(
    image=image,
    gpu=GPU,
    timeout=TIMEOUT_SECONDS,
    cpu=4,
    memory=16384,
    volumes={"/transfer": TRANSFER_VOLUME},
)
def execute(command: str, setup_command: str, transfer_key: str) -> int:
    """Execute trusted project code and persist checkpoints/outputs on success or failure."""
    key = validate_transfer_key(transfer_key)
    workdir = Path("/workspace")
    if not workdir.is_dir():
        raise RuntimeError("Caller workspace was not copied into the Modal image")

    print(f"GPU: {GPU}")
    print(f"Working directory: {workdir}")
    print("Starting remote workload...")

    return_code = 0
    try:
        if setup_command.strip():
            print("Running GPU environment setup...")
            setup_result = subprocess.run(
                ["bash", "-euo", "pipefail", "-c", setup_command],
                cwd=str(workdir),
                check=False,
            )
            if setup_result.returncode != 0:
                return_code = setup_result.returncode
                raise RuntimeError(f"GPU setup exited with status {return_code}")

        result = subprocess.run(
            ["bash", "-euo", "pipefail", "-c", command],
            cwd=str(workdir),
            check=False,
        )
        return_code = result.returncode
    finally:
        # Preserve partial checkpoints even if setup/training fails.
        persist_transfer_files(key)

    if return_code != 0:
        raise RuntimeError(f"GPU workload exited with status {return_code}")
    return return_code


@app.local_entrypoint()
def main(
    command: str,
    transfer_key: str,
    setup_command: str = "",
):
    """CLI entrypoint invoked by GitHub Actions."""
    key = validate_transfer_key(transfer_key)
    print(f"Submitting one-shot Modal job (GPU={GPU}, timeout={TIMEOUT_MINUTES}m)")
    execute.remote(command, setup_command, key)
    print("Remote workload completed successfully.")
