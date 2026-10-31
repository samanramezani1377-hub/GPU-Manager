# Setup and operating rules

## 1. Modal credentials (GPU stages only)

1. Create or sign in to a Modal account: https://modal.com/
2. Create a dedicated Modal token for GitHub Actions.
3. In each repository that will execute a GPU stage, add these Actions repository secrets:
   - MODAL_TOKEN_ID
   - MODAL_TOKEN_SECRET
4. Never put either value in workflow YAML, source files, logs, or committed files.

CPU-only workflows do not need Modal credentials.

## 2. Credit-only billing guardrail

Before enabling GPU workloads:

1. Open the Modal workspace Usage & Billing settings.
2. Find the workspace Spend limit, not just the usage budget.
3. Set the out-of-pocket Spend limit to $0 if the account UI permits it, save, and verify the saved value.
4. Re-check after plan, payment, or workspace changes.

Do not assume included credits alone prevent overage. A spend limit is the intended billing guardrail, but users should verify Modal's current billing behavior and the exact setting in their own workspace. Do not run production training until the guardrail is confirmed.

## 3. Choose a pipeline shape

Use one reusable workflow call in the caller repository:

- CPU only: set cpu_command; no Modal secrets required.
- GPU only: set gpu_command; Modal secrets required.
- Sequential: set cpu_before_gpu, gpu_command, and/or cpu_after_gpu.
- Parallel: add cpu_parallel_command for an independent CPU job.
- Final join: add cpu_finalize_command to run after the main and parallel jobs complete.

See the examples directory for complete caller workflows.

## 4. File handoff

The transfer folder is .gpu-manager-transfer/.

- CPU preparation writes files needed by GPU into this folder.
- GPU code reads and writes files in this folder.
- The worker archives the folder to a per-run path in the Modal Volume gpu-manager-transfer and explicitly commits the Volume.
- The GitHub runner downloads the archive, restores the folder, then runs the CPU-after-GPU stage.
- Main and parallel transfer folders are retained as GitHub artifacts for 7 days.

The independent parallel CPU branch uses .gpu-manager-parallel/. Keep its files separate from the main transfer folder. The final CPU stage receives both directories.

A cancelled job can leave a run-specific directory in the Modal Volume. Remove stale run folders from the Modal dashboard or with the Modal CLI after confirming the run is no longer active.

## 5. Runtime and dependencies

- Supported GPU labels: T4, L4, A10, L40S, A100, H100.
- GPU timeout: 1–345 minutes.
- CPU work runs on GitHub-hosted ubuntu-latest; GitHub runner usage limits and quotas still apply.
- GPU dependencies are not inferred. Use gpu_setup_command, for example: python -m pip install -r requirements.txt.
- CPU dependencies must be installed by the CPU command or project scripts.

## Security notes

- Treat every command input as trusted code. Do not let untrusted pull requests control commands.
- GitHub secrets are used only by the runner to authenticate to Modal; they are not passed into the remote workload.
- The worker excludes common secret-file patterns and Git metadata, but this is not a substitute for keeping credentials out of the repository.
- The workflow checks out the caller's triggering commit with checkout credentials disabled.
- The Modal Volume path is unique per workflow run and attempt, avoiding intentional file-path collisions between concurrent runs.
- The public reusable workflow currently references the central worker on main. Pin the caller's reusable workflow reference to an immutable commit SHA if stricter supply-chain pinning is required.
