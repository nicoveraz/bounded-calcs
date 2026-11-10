# Releasing

A release puts a version on PyPI, where it cannot be changed or deleted, only superseded.
The maintainer decides when to release. An agent prepares a release only when asked, and
never pushes a tag or publishes a GitHub release on its own.

## How it works

Pushing a tag `vX.Y.Z` starts `.github/workflows/publish.yml`. It checks that the tag matches
the version in `pyproject.toml`, runs the tests, builds the sdist and the wheel, smoke-tests
both as installed packages (`scripts/smoke_test.py`), and uploads them to PyPI.

No token is stored anywhere. PyPI accepts the upload because the project lists this workflow
as a Trusted Publisher.

## One-time setup on PyPI (maintainer)

1. Sign in at pypi.org and open **Publishing** in the account sidebar.
2. Under "Add a new pending publisher", choose GitHub and enter:

   | Field | Value |
   |---|---|
   | PyPI project name | `bounded-calcs` |
   | Owner | `nicoveraz` |
   | Repository name | `bounded-calcs` |
   | Workflow name | `publish.yml` |
   | Environment name | `pypi` |

A pending publisher does not reserve the name: the project exists on PyPI only after the
first successful upload. Optionally, in the GitHub repository settings, add yourself as a
required reviewer of the `pypi` environment so that every upload waits for your approval.

## Each release

1. **Choose the version** (see "What a version means").
2. **Set it in two places**: `version` in `pyproject.toml` and `version=` in
   `src/bounded_calcs/mcp_server.py`. Then run `uv lock`. A test fails if the two differ.
3. **Check locally**:

   ```sh
   uv run pytest
   rm -rf dist && uv build
   uv run --isolated --no-project --with dist/*.whl --with "mcp>=2,<3" scripts/smoke_test.py
   uv run --isolated --no-project --with dist/*.tar.gz --with "mcp>=2,<3" scripts/smoke_test.py
   ```

4. **Commit** as `Release X.Y.Z` and push to `main`.
5. **Publish** (maintainer): on GitHub, create a release with the new tag `vX.Y.Z` on `main`,
   with notes that list new calculators and any change in scoring. This starts the workflow.
6. **Verify**: the workflow is green, https://pypi.org/project/bounded-calcs/ shows the
   version, and `uvx --from "bounded-calcs[mcp]==X.Y.Z" bounded-calcs-mcp` starts.

If the workflow fails before the upload, fix the cause, delete the tag and the release, and
repeat from step 4. If a bad version reached PyPI, yank it on pypi.org and release a fixed
one with a higher number; a version number can never be reused.

## What a version means

While the version is below 1.0, the output fields and the input format may still change
between minor versions.

| Change | Bump |
|---|---|
| Fix that changes no result | patch (0.1.0 to 0.1.1) |
| New calculator, new rule type, new optional output field | minor (0.1.0 to 0.2.0) |
| A calculator's scoring changes: bump the spec's own `version` too, and name the calculator in the release notes | minor |
| Output field renamed or removed, input format changed | minor while below 1.0, major afterwards |

## Details worth knowing

- Supported Python versions are those listed in the classifiers of `pyproject.toml`; each was
  tested against the built wheel before being listed.
- The MCP SDK is capped below version 3 because version 2 renamed its server classes. Raise
  the cap only after running the tests against the new major version.
- Core metadata is pinned to 2.4 in `pyproject.toml` because uploads with 2.5 have been
  rejected by PyPI. Remove the pin once PyPI is known to accept 2.5.
- The actions in the workflow are pinned to commits, because that job can upload to PyPI.
  Update a pin only to a tagged release of the action.
