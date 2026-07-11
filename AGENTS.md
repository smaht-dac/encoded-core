# Project agent memory

This is the shared model library for Park Lab ENCODE-style portals. Keep this guide focused on
repository-intrinsic facts and use the referenced files as the source of truth.

## Architecture and integration boundaries

- `encoded-core` is a Python/Poetry package, not a complete production portal. It supplies common
  Snovault/Pyramid item types, schemas, views, authorization behavior, and project metadata for
  downstream encoded portals. See `README.rst`, `[tool.poetry]`, and the Paste entry points in
  `pyproject.toml`.
- `src/encoded_core/__init__.py:main` is a minimal WSGI app factory intended for testing. It wires
  Pyramid, multiauth, the local-role policy, database sessions, Snovault, upgrades, package scans,
  and optional Elasticsearch support. Production portals own their application composition,
  environment configuration, deployment assets, and portal-specific types.
- Snovault is the persistence/indexing framework and `dcicutils` supplies project registration and
  release utilities. `src/encoded_core/project_defs.py` registers the package with
  `C4ProjectRegistry`; preserve that name/accession contract for consumers.
- Item behavior is split between Python classes in `src/encoded_core/types/` and JSON Schemas in
  `src/encoded_core/schemas/`. A type class points to its schema with `load_schema`; changes to a
  field may also require calculated properties, embeds/reverse links, validation callbacks, tests,
  and a migration/upgrade step. Search for the item type across both directories before editing.
- Venusian scanning discovers decorated collections, views, calculated properties, callbacks, and
  upgrade hooks. `src/encoded_core/types/__init__.py:includeme` and the package app factory call
  `config.scan()`; avoid manual registration that duplicates scanning.

## Repository map

- `src/encoded_core/types/`: shared Snovault collections and abstract bases. Files/workflows and
  their embed graphs are concentrated in `file*.py`, `workflow.py`, and `meta_workflow.py`;
  content/page models are in `page.py` and `user_content.py`.
- `src/encoded_core/schemas/`: packaged JSON Schemas. `mixins.json` holds reusable schema fragments;
  inheritance and `$merge` relationships make changes broader than a single schema file.
- `src/encoded_core/file_views.py`: upload/download/DRS endpoints and File validation callbacks.
  These cross the S3, credentials, and request/authorization boundary.
- `src/encoded_core/page_views.py` and `qc_views.py`: page-tree/static-page behavior and quality
  metric downloads.
- `src/encoded_core/local_roles.py`: authorization policy and local-principal merging. Treat changes
  as security-sensitive and cover precedence/inheritance cases in `test_local_roles.py`.
- `src/encoded_core/upgrade.py`: Snovault upgrade finalizer integration. Put durable data migrations
  behind the framework upgrade machinery rather than request-time compatibility code.
- `src/encoded_core/tests/`: unit and server-backed tests plus shared fixtures. Root `conftest.py`
  loads `datafixtures.py` and defines Elasticsearch CLI options; package `tests/conftest.py` builds
  the Postgres/Elasticsearch Pyramid fixtures.
- `pyproject.toml`: authoritative package metadata, supported Python range, dependencies, scripts,
  and Paste factories. `poetry.lock` is the resolved dependency set. `setup_eb.py` derives legacy
  setuptools metadata from `pyproject.toml`; do not maintain a second version there.
- `Makefile`: canonical build, test, remote-test, and publish wrappers. `.github/workflows/` is the
  authority for CI and release behavior.

## Development and tests

- Use the `encoded-core311` pyenv virtualenv (`pyenv activate encoded-core311`, or source
  `~/.pyenv/versions/3.11.9/envs/encoded-core311/bin/activate`). `make build` installs the Poetry
  version selected by the Makefile and the locked dependencies; avoid incidental lockfile changes.
- Run the suite with `make test` (equivalent to the verbose, fail-fast pytest command in the
  Makefile). Narrow runs use, for example,
  `poetry run python -m pytest src/encoded_core/tests/test_page_views.py -xvv`.
- A local checkout-specific editable install can point at a different worktree. In a worktree,
  prepend this tree's `src` to `PYTHONPATH` so imports and the collected `conftest.py` agree, or
  pytest can fail with `ImportPathMismatchError`.
- Server-backed fixtures need local Postgres and Elasticsearch configuration; see `pytest.ini`,
  root `conftest.py`, and `src/encoded_core/tests/conftest.py`. `make remote-test` names the supported
  remote-ES invocation, but is an integration operation rather than a default local check.
- Tests that POST/PATCH File items generate external S3 credentials. Without a valid AWS session,
  `botocore.exceptions.TokenRetrievalError` is an environment failure, not necessarily a regression.
  CI supplies AWS credentials and an upload role before running the full suite.
- Prefer pure unit tests where behavior permits it (`test_local_roles.py`, `test_page_views.py`, and
  `test_types_workflow_run_steps.py`). `@calculated_property` methods remain directly callable on
  lightweight instances/stubs, which avoids starting database, search, and AWS services.
- CI in `.github/workflows/main.yml` runs the suite against the declared Python matrix with
  PostgreSQL 11, AWS credentials, and index cleanup. Keep local assertions compatible with every
  Python version allowed by `pyproject.toml`, not only the preferred 3.11 environment.

## Configuration, compatibility, and operations

- The app factory enables nested Elasticsearch mappings before including Snovault; ordering is
  intentional. It enables search only when `elasticsearch.server` is present and testing-only views
  only when `testing` is true. Its Elasticsearch branch still references the historical
  `encoded_core.search` package, which is not present here; do not assume the standalone factory is
  a complete search-enabled portal. Preserve include/commit ordering unless framework behavior is
  fully verified.
- Authentication settings are supplied by the host application. The representative test contract
  is in `src/encoded_core/tests/conftest_settings.py`; it is fixture configuration, not a production
  settings template.
- `ENCODED_VERSION` populates the app-version registry value when deployment has not already set it.
  AWS IP ranges are loaded from `aws_ip_ranges_path`; absent input intentionally yields an empty set.
- Compatibility pins and comments in `pyproject.toml` are deliberate, especially the SQLAlchemy
  constraint. Dependency widening is a cross-portal compatibility change and requires consumer and
  integration testing.
- File schemas, embed lists, and workflow step schemas encode API/index documents consumed by other
  portals. Renames, required-field changes, calculated-property changes, and embed changes can break
  stored data or search mappings even when this repository's unit tests pass.

## Release conventions

- The release version lives only in `pyproject.toml`; tags use that bare version. Do not alter the
  version or changelog unless the task explicitly includes a release.
- `.github/workflows/main.yml` tests pushes/PRs and, after a successful push to `main`, checks the git
  tag and PyPI release independently, creates a missing tag, and publishes a missing package in the
  same job. This supports recovery from a tag-created/package-not-published partial failure.
- `.github/workflows/main-publish.yml` remains the manual/tag-triggered publishing path. Do not make
  the automatic main release depend on a workflow triggered by its `GITHUB_TOKEN` tag push; GitHub's
  anti-recursion behavior prevents that follow-on run.
- The publish job uses `POETRY_VIRTUALENVS_CREATE=true`, asserts a clean checkout after dependency
  installation, and scopes `contents: write` to the publish job. Preserve those release invariants.

## Maintaining this file

Keep entries scoped to durable, project-intrinsic knowledge: build/test/release mechanics,
architecture decisions, and sharp edges that aren't obvious from reading the code. Prefer pointing
at the authoritative file/command over duplicating details that will drift. Update or remove
entries when they go stale; don't let this file grow into a changelog.
