"""One-shot Modal worker used by the reusable GPU-Manager workflow.

The .gpu-manager-transfer directory is mounted through a per-run Modal Volume path.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
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
            ".gpu_manager_worker.py",
        ],
    )
)


def validate_transfer_key(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", value):
        raise ValueError("transfer_key contains unsupported characters")
    return value


def prepare_transfer_directory(transfer_key: str) -> Path:
    """Copy input files to a unique Volume path and link the project folder to it."""
    key = validate_transfer_key(transfer_key)
    source_dir = Path("/workspace/.gpu-manager-transfer")
    volume_dir = Path("/transfer") / key
    volume_dir.mkdir(parents=True, exist_ok=True)

    if source_dir.is_symlink():
        raise RuntimeError("The incoming transfer directory must not be a symlink")
    if source_dir.exists():
        if not source_dir.is_dir():
            raise RuntimeError(".gpu-manager-transfer exists but is not a directory")
        for child in source_dir.iterdir():
            destination = volume_dir / child.name
            if child.is_dir() and not child.is_symlink():
                shutil.copytree(child, destination, dirs_exist_ok=True)
            else:
                shutil.copy2(child, destination, follow_symlinks=False)
        shutil.rmtree(source_dir)

    source_dir.parent.mkdir(parents=True, exist_ok=True)
    source_dir.symlink_to(volume_dir, target_is_directory=True)
    TRANSFER_VOLUME.commit()
    return source_dir


def start_periodic_volume_commits() -> tuple[threading.Event, threading.Thread]:
    """Commit changed checkpoints periodically while a long GPU process is running."""
    stop_event = threading.Event()

    def commit_loop() -> None:
        while not stop_event.wait(120):
            try:
                TRANSFER_VOLUME.commit()
                print("Periodic Modal Volume checkpoint commit completed.")
            except Exception as exc:  # Keep the workload alive; final commit retries.
                print(f"Warning: periodic Volume commit failed: {exc}")

    thread = threading.Thread(target=commit_loop, name="modal-volume-commit", daemon=True)
    thread.start()
    return stop_event, thread


@app.function(
    image=image,
    gpu=GPU,
    timeout=TIMEOUT_SECONDS,
    cpu=4,
    memory=16384,
    volumes={"/transfer": TRANSFER_VOLUME},
)
def execute(command: str, setup_command: str, transfer_key: str) -> int:
    """Execute trusted project code with live checkpoint persistence to Modal Volume."""
    key = validate_transfer_key(transfer_key)
    workdir = Path("/workspace")
    if not workdir.is_dir():
        raise RuntimeError("Caller workspace was not copied into the Modal image")

    transfer_path = prepare_transfer_directory(key)
    print(f"GPU: {GPU}")
    print(f"Working directory: {workdir}")
    print(f"Persistent transfer directory: {transfer_path}")
    print("Starting remote workload...")

    stop_event, commit_thread = start_periodic_volume_commits()
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
        stop_event.set()
        commit_thread.join()
        # Ensure the last checkpoint/output changes are visible to the runner.
        TRANSFER_VOLUME.commit()

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
