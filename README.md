# GPU-Manager

Central reusable CPU/GPU compute pipelines for this account's GitHub repositories.

Ordinary CPU work stays on GitHub-hosted Actions runners. Only explicitly requested GPU stages are sent to Modal. One reusable workflow supports CPU-only, GPU-only, sequential CPU → GPU → CPU, and independent parallel CPU + GPU work.

## Architecture

- CPU-only: GitHub Actions runner; no Modal credentials required.
- GPU-only: Modal; the runner submits the caller repository and streams logs.
- Sequential mixed pipeline: optional CPU preparation → Modal GPU stage → optional CPU stage.
- Parallel mixed pipeline: an independent CPU job can run alongside the main pipeline; an optional final CPU job waits for both.
- File handoff: the GPU worker returns the transfer directory through a per-run Modal Volume path. GitHub Actions retains transfer outputs as workflow artifacts for 7 days.

## Quick start

1. For GPU workloads, add MODAL_TOKEN_ID and MODAL_TOKEN_SECRET to the caller repository's Actions secrets. CPU-only workflows do not need these secrets.
2. Copy one example from the examples folder into the caller repository's .github/workflows directory.
3. Change the commands to match the project. Commands run from the repository root.
4. For mixed workflows, use .gpu-manager-transfer/ for files that must pass into or out of the GPU stage.
5. Review the Modal billing guardrail in docs/SETUP.md before running GPU workloads.

## Examples

- CPU only: examples/cpu-only.yml
- GPU only: examples/call-modal-gpu.yml
- Sequential CPU → GPU → CPU: examples/sequential-cpu-gpu-cpu.yml
- Parallel CPU + GPU, then final CPU: examples/parallel-cpu-gpu.yml

## Caller interface

The reusable workflow is:

```yaml
jobs:
  compute:
    uses: samanramezani1377-hub/GPU-Manager/.github/workflows/modal-gpu.yml@main
    with:
      cpu_before_gpu: "python prepare.py"
      gpu_command: "python train.py"
      gpu_setup_command: "python -m pip install -r requirements.txt"
      cpu_after_gpu: "python evaluate.py"
      gpu: "T4"
      timeout_minutes: 120
    secrets:
      MODAL_TOKEN_ID: ${{ secrets.MODAL_TOKEN_ID }}
      MODAL_TOKEN_SECRET: ${{ secrets.MODAL_TOKEN_SECRET }}
```

## Inputs

| Input | Purpose |
|---|---|
| cpu_command | CPU-only command; use when gpu_command is empty |
| cpu_before_gpu | CPU preparation before GPU |
| gpu_command | Command executed remotely on Modal |
| gpu_setup_command | Optional dependency/setup command inside Modal |
| cpu_after_gpu | CPU stage after GPU |
| cpu_parallel_command | Independent CPU job in parallel with the main pipeline |
| cpu_finalize_command | CPU stage after main and parallel jobs finish |
| gpu | T4, L4, A10, L40S, A100, or H100 |
| timeout_minutes | GPU timeout, 1–345 minutes |
| python_version | GitHub runner Python version; defaults to 3.11 |

## File handoff

Only files inside .gpu-manager-transfer/ are guaranteed to be returned from Modal.

- CPU preparation writes datasets/configuration needed by GPU into this directory.
- The Modal worker receives the checked-out repository, including this directory.
- The GPU command reads inputs from it and writes checkpoints/results back into it.
- The worker mounts this directory from a run-specific Modal Volume path and commits it periodically while the GPU job runs, then commits again before normal exit.
- GitHub Actions downloads and restores it before cpu_after_gpu.
- Main and parallel transfer folders are uploaded as GitHub workflow artifacts for 7 days.

The independent parallel CPU job uses .gpu-manager-parallel/. Keep its files separate from the main transfer directory. The optional final CPU job downloads both directories.

For large checkpoints, the Modal Volume is the transport between Modal and the GitHub runner. GitHub artifact retention is a separate copy and remains subject to GitHub artifact size and storage limits.

## Dependencies

- CPU dependencies must be installed by CPU commands or project scripts.
- GPU dependencies are not guessed or installed automatically. Use gpu_setup_command, for example: python -m pip install -r requirements.txt.

## Security and operational limits

- Command inputs are trusted shell code. Never let untrusted pull-request content control them.
- GitHub secrets are used only by the runner to authenticate to Modal; they are not forwarded into the remote workload.
- Common credential files are excluded from the Modal image, but credentials should never be committed to the repository.
- The central worker is fetched from the public main branch. For stricter supply-chain control, callers can pin the reusable workflow to an immutable commit SHA after reviewing a release.
- The worker uses a dedicated Modal Volume named gpu-manager-transfer. Each run has a unique run/attempt directory and removes it after download. Periodic commits can preserve earlier checkpoints if a long-running job is interrupted, although a forced termination can still prevent the final commit. A cancelled workflow may leave a temporary directory behind.
- No live Modal execution test is claimed until Modal credentials are configured and a small test is run.
