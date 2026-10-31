# GPU-Manager

Central reusable GPU execution for this account's GitHub repositories.

## Current implementation

- Public reusable workflow: [modal-gpu.yml](.github/workflows/modal-gpu.yml)
- One-shot Modal worker: [worker.py](worker.py)
- Caller example: [examples/call-modal-gpu.yml](examples/call-modal-gpu.yml)
- Setup, credit-only guardrail, and security notes: [docs/SETUP.md](docs/SETUP.md)

A caller repository invokes the reusable workflow only for jobs that need a GPU. GitHub Actions checks out the caller's triggering commit, submits its working tree to a temporary Modal container, runs the requested command, and exits when the job finishes.

## Before first use

1. Configure the Modal token secrets in each caller repository.
2. Set the Modal workspace Spend limit to **$0** in Usage & Billing to prevent out-of-pocket compute charges after applicable credits are exhausted.
3. Run a small test job before connecting training workloads.

See [docs/SETUP.md](docs/SETUP.md) for the complete setup.

## Important current limitations

- No existing repository has been modified or connected yet.
- The worker currently runs one command and streams logs, but does not yet transfer checkpoints or other output files back to GitHub.
- GitHub secrets are not forwarded into the remote container.
- The command is trusted shell code and must only be supplied by trusted workflows.

The central workflow is reusable across public and private caller repositories, subject to each caller repository's GitHub Actions and secret permissions.
