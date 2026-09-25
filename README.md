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
Both packages have SHA-256 wheel hashes embedded in the workflow. Installation
uses `--require-hashes --only-binary=:all:` to reject artifacts that do not match
those hashes and prevent source builds. The allowed wheels target Linux x86_64
(the hosted Ubuntu runner), with hashes for the supported Python versions.

The requirements file is generated in `RUNNER_TEMP` from the workflow itself;
centralized ruleset runs do not need any dependency files in target repositories.
When updating either package, review the new release and update its version and
wheel hashes together using the corresponding PyPI release metadata. Hashes are
never fetched dynamically during a workflow run. This locks installation to the
reviewed artifacts; it does not prove that those artifacts are free of malicious
code or vulnerabilities.

To run the regression tests, install PyYAML 6.0.3 in a virtual environment and
run `python -m unittest discover -s tests -v`.
