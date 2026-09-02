# Project Notes

## GitHub Actions package export

- It is worth considering a GitHub Actions workflow that exports the NVHP/project layout into a normal Houdini package on push or release.
- Prefer generating the exported package as a workflow artifact or release asset instead of committing generated package files back into the repository.
- If the export path can stay pure Python, CI should call the existing export logic without requiring Houdini to be installed or licensed.
- A practical split is:
  - Pull requests / main pushes: run the export into a temporary directory as a validation check, optionally upload an artifact.
  - Version tags: export, zip the normal Houdini package, and attach it to the GitHub Release.
- Keep the workflow deterministic: export from a clean checkout, write into a temporary output directory, and avoid modifying tracked files during CI.
