# Setup and operating rules

## 1. Create Modal credentials

1. Create or sign in to a Modal account: https://modal.com/
2. Create a Modal token for GitHub Actions.
3. In every caller repository (or an eligible GitHub organization secret scope), add:
   - MODAL_TOKEN_ID
   - MODAL_TOKEN_SECRET
4. Never put either value in source code, workflow YAML, logs, or committed files.

## 2. Enforce credit-only usage

The architecture is intended to stop when included credits are exhausted. Before enabling any caller workflow:

1. Open Modal Usage & Billing for the workspace.
2. Find Spend limit (not only the usage budget).
3. Set the monthly Spend limit to $0 and save it.
4. Confirm the saved value in the dashboard.

Modal documents that the spend limit caps net out-of-pocket charges after credits. At the limit, workloads that would incur additional out-of-pocket charges are stopped; work still covered by remaining applicable credits can continue until the usage limit is reached.

Do not assume that the Starter plan's included credits alone prevent overage. Re-check the saved spend limit in Modal after account or billing changes. A job already running when a limit is reached may have final usage settlement behavior governed by Modal's billing system.

## 3. Connect a repository

Copy examples/call-modal-gpu.yml into the caller repository at:
.github/workflows/run-gpu-job.yml

Then change command, gpu, and timeout_minutes for that repository. The caller workflow's trigger determines when the remote job starts. Only call this reusable workflow from jobs that genuinely need a GPU.

Supported GPU labels in this initial version: T4, L4, A10, A10G, A100, H100.

## 4. What runs remotely

- GitHub Actions checks out the calling repository at the triggering commit.
- The central worker is copied into the checkout.
- Modal receives the working tree, excluding common credential files and Git metadata.
- The command runs in a temporary Modal container with the selected GPU.
- The one-shot container exits when the command finishes or fails.

The initial worker does not automatically upload training outputs back to GitHub. Add an explicit artifact/volume transfer step for a workload before relying on it to preserve checkpoints or generated files.

## Security notes

- Treat the command input as trusted code: it is executed by Bash inside the remote container.
- Do not store secrets in files that are part of the checked-out repository.
- The worker excludes common secret-file patterns, but this is not a substitute for keeping credentials out of the source tree.
- This first version does not pass GitHub secrets into the remote workload.
- The Modal token should be a dedicated token with the minimum permissions available for the intended workspace.
