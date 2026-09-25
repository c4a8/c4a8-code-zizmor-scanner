# zizmor-scanner
Host Zizmor scanner used in c4a8 Sandboxs

Repositories without any GitHub Actions workflows, action definitions or
Dependabot configs pass the scan: zizmor still runs, but its "no inputs
collected" result is reported as informational instead of failing the job.

If an audit throws an exception, the scanner retries the affected file with only
that audit disabled for that file. Other files retain the audit, and existing
zizmor configuration is preserved. Multiple failing audits can be isolated;
unrecognized errors and repeated failures still fail the job, as do findings.
The PR comment and Action Summary both include a ⚠️ warning listing each skipped
audit and file. A successful fallback means reduced coverage, not a clean scan.

The workflow is self-contained for distribution to other repositories and pins
zizmor to 1.30.1. It runs in a temporary virtual environment with PyYAML 6.0.3,
which is used to merge fallback configuration without editing repository files.

To run the regression tests, install PyYAML 6.0.3 in a virtual environment and
run `python -m unittest discover -s tests -v`.
