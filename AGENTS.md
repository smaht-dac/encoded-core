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

## Automatic tag-and-publish-on-main release workflow

`.github/workflows/main.yml`'s `publish` job (`needs: build`, runs only on `push` to `main`) reads
the version from `pyproject.toml` (`poetry version -s`) and checks both for its git tag and for an
existing PyPI release. It creates the tag if missing and publishes only if PyPI does not already
have the version, all **in the same job run**. It deliberately does not rely on
`.github/workflows/main-publish.yml`'s tag-triggered `on: push: tags` event, because GitHub Actions
does not start a new workflow run from a tag pushed using the default `GITHUB_TOKEN`
(anti-recursion rule) — `main-publish.yml` remains only for manual/`workflow_dispatch` publishing.

The "Create and push tag" step is gated on the tag-existence check (`exists == 'false'`) — tag once
per version. The "Publish to PyPI" step instead uses the independently checked
`pypi_exists == 'false'` condition. Its curl request treats only HTTP 200 (present) and 404 (absent)
as valid; any other status fails the job closed. This split preserves recovery from a
tag-exists-but-never-published state, while avoiding a failing duplicate-upload attempt on later
merges. `publish-to-pypi` itself treats an existing release as an error, rather than an idempotent
success.

This repo has no tracked `poetry.toml` (unlike dcicsnovault, where `poetry config --local
virtualenvs.create true` used to dirty a tracked `poetry.toml` and break the release checkout) — so
the `publish` job just sets `POETRY_VIRTUALENVS_CREATE: "true"` job-wide before running `make build`
(which runs `poetry install`), the same environment-variable form, so that a tracked `poetry.toml`
added later still won't be dirtied by this job. The workflow asserts `git diff --exit-code`
directly after dependency install regardless, so any future mutation names the affected file at the
source of the failure.

The `publish` job's `permissions: contents: write` (needed to push the tag) is scoped to that job
only; the `build` job needs no elevated permissions here since this repo authenticates its AWS step
with static `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` secrets rather than OIDC, so (unlike
dcicsnovault) no workflow-level `permissions:` block is needed.

## Maintaining this file

Keep entries scoped to durable, project-intrinsic knowledge: build/test/release mechanics,
architecture decisions, and sharp edges that aren't obvious from reading the code. Prefer pointing
at the authoritative file/command over duplicating details that will drift. Update or remove
entries when they go stale; don't let this file grow into a changelog.
