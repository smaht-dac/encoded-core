# Project agent memory

This file is the project's committed home for project-intrinsic agent knowledge: build, test, release, architecture, and sharp-edge notes that should travel with the code.

- Add durable project-specific notes here as they are discovered through real work.

## Running the test suite

- Tests live under `src/encoded_core/tests/` and run in the `encoded-core311` pyenv virtualenv
  (`pyenv activate encoded-core311`, or source `~/.pyenv/versions/3.11.9/envs/encoded-core311/bin/activate`).
- `make test` / `poetry run python -m pytest` is the canonical invocation. The suite needs a local
  Postgres (spun up by `snovault.tests.serverfixtures`, wired via `pytest.ini`); collection also needs
  ES config for the server-backed tests.
- The `encoded-core311` venv installs `encoded_core` as an **editable install pointing at a specific
  checkout** (e.g. `~/Documents/4dn/encoded-core/src`), not necessarily the checkout you are running
  from. When running from a different worktree, prepend that worktree's `src` to `PYTHONPATH`
  (`export PYTHONPATH=/path/to/worktree/src`) so imports and the collected `conftest.py` resolve to the
  same tree — otherwise pytest fails with `ImportPathMismatchError`.
- Tests that POST/PATCH File items trigger S3 credential generation (`external_creds`), which needs
  live AWS credentials. Without a valid AWS session these fail with
  `botocore.exceptions.TokenRetrievalError` — an environmental failure, not a code regression.
- Pure-logic modules can be unit-tested without a server or AWS by importing them directly and calling
  their functions/methods on light stub objects (see `test_local_roles.py`, `test_page_views.py`,
  `test_types_workflow_run_steps.py`). Calculated-property methods are left as plain functions by the
  `@calculated_property` decorator, so they can be called on a bare `Cls.__new__(Cls)` instance or via
  `Cls.method(stub, request)` when they only read `self.properties`.
