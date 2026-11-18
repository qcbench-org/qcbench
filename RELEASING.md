# Releasing

Run core and optional-adapter tests, build both distribution formats, inspect their contents and check package metadata:

```bash
python -m pip install -e '.[ibm,dev]'
python -m pytest -q
python -m build
python -m twine check --strict dist/*
```

Tests use local devices/samplers and stubbed submission only; a passing release check does not imply a paid QPU validation. Document any actual hardware validation separately with device, job ID, acquisition conditions and data permissions.

Update versions in pyproject.toml and src/qcbench/__init__.py, tag the tested commit, and keep publishing credentials outside the repository. Verify artifact hashes and installation from PyPI after upload. Release files on PyPI cannot be overwritten.

For subsequent GitHub release automation, configure a PyPI Trusted Publisher and matching GitHub environment:

- Owner: qcbench-org
- Repository: qcbench
- Workflow filename: publish.yml
- Environment: pypi

The workflow tests/builds/checks and publishes with OIDC when a GitHub release is published. It does not configure the trust relationship itself. First publication may use a PyPI API token in the publishing process environment.
