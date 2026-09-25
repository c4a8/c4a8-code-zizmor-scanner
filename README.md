# c4a8 zizmor scanner

A self-contained GitHub Actions security scanning workflow for c4a8 repositories, with a manual release pipeline for versioning this repository.

## Repository layout

| File | Purpose |
| --- | --- |
| [zizmor-action.yml](.github/workflows/zizmor-action.yml) | Installs the scanner, runs audits, recovers from supported audit exceptions, and publishes findings. |
| [release.yml](.github/workflows/release.yml) | Delegates version generation, tagging, and GitHub release creation to a pinned semantic-version action. |
| [test_zizmor_fallback.py](tests/test_zizmor_fallback.py) | Regression tests for the embedded scan wrapper and report generation. |
| [dependabot.yml](.github/dependabot.yml) | Weekly GitHub Actions dependency updates, with a seven-day cooldown and grouped minor/patch updates. |

## Using the scanner

Copy `.github/workflows/zizmor-action.yml` into the same directory in the target repository. The workflow contains its installation requirements, scan wrapper, and reporting code; it does not require this repository's tests or other supporting files in the target repository. This also keeps the source workflow self-contained for centralized ruleset use.

The workflow defines `pull_request` and `workflow_dispatch` triggers. It does not expose a `workflow_call` interface for invocation as a reusable workflow.

### Triggers and permissions

The workflow runs when a pull request is opened, updated with new commits, or reopened. It can also be started manually through **Actions → zizmor → Run workflow**. There is no push or scheduled trigger.

Runs use `ubuntu-latest`. A newer run cancels an in-progress scan for the same pull request, or the same ref for manual runs.

Workflow-level permissions are empty. The scan job requests:

- `contents: read` to check out the repository, with credential persistence disabled.
- `pull-requests: write` to create or update the findings comment on same-repository pull requests.

The scanner and comment step use the run's GitHub token. Fork pull requests skip the comment step; their results remain available in the run summary and annotations.

### Scan workflow

1. **Check out the repository.** The checkout action is pinned to a full commit SHA.
2. **Install the scanner.** Create a temporary Python virtual environment and install `zizmor==1.30.1` and `PyYAML==6.0.3`. Package versions and approved Linux x86_64 wheel SHA-256 hashes are embedded in the workflow. Installation requires matching hashes and binary wheels.
3. **Run audits.** Invoke zizmor with `--format=github --color=never --persona=regular`, allowing the scanner to collect repository inputs. The initial scan runs against a temporary repository copy.
4. **Recover from recognized audit exceptions.** Isolate affected files and retry them as described below.
5. **Build a report.** Parse completed scan annotations into a Markdown report and append it to the GitHub Actions job summary. Reporting runs after failures unless the run was cancelled.
6. **Publish the PR comment.** For same-repository pull requests, create a comment or update the first comment matching `<!-- zizmor-findings-report -->`. Manual runs and fork pull requests do not post comments.

The report's input-presence check covers workflow YAML files, `action.yml`/`action.yaml` definitions, Dependabot configuration, and `.pre-commit-config.yaml`. This check only controls report wording; zizmor's exit status controls the scan result.

### Audit exception fallback

When zizmor reports a recognized audit exception with an identifiable file inside the scan root, the wrapper removes that file from the temporary copy and reruns collection for the remaining inputs. It then scans each isolated file separately with the failing audit disabled for that entire file.

Other files retain the audit. Existing repository configuration is preserved when building the temporary fallback configuration, using this discovery order at the file's Git root:

1. `.github/zizmor.yml`
2. `.github/zizmor.yaml`
3. `zizmor.yml`
4. `zizmor.yaml`

Multiple failing audits can be disabled for the same file. Checked-out files are not modified. An unrecognized error or a repeated failure of an already-disabled audit still fails the scan.

Every skipped audit/file pair produces a workflow warning and appears in the summary and eligible PR comment. **A successful fallback means reduced scan coverage.** It does not establish that the skipped checks passed.

### Results and reporting

| Scan result | Behavior |
| --- | --- |
| Completed with no findings | Scan succeeds and reports no issues. |
| No auditable inputs | Scan succeeds; the summary reports nothing to scan and no PR comment is posted. |
| Findings | Scan fails; findings are still reported. |
| Successful fallback without findings | Scan succeeds with an explicit reduced-coverage warning. |
| Scanner error | Scan fails; the report warns that scanning failed or that reported findings may be incomplete. |

The Markdown report shows up to 50 findings, with severity, audit, location, and details. Additional findings remain available in the run log. Audit names link to audit documentation; locations link to the PR head commit for PR runs or the dispatched commit for manual runs. PR runs use checkout's default checkout behavior; report links explicitly use the PR head SHA.

Completed scan output also produces GitHub annotations. Fatal diagnostics are printed with workflow-command interpretation temporarily disabled.

## Release pipeline

The [release workflow](.github/workflows/release.yml) is started manually through `workflow_dispatch`. It has one boolean input:

| Input | Default | Purpose |
| --- | --- | --- |
| `is_prerelease` | `false` | Request a prerelease version from the semantic-version action. |

### Creating a release

1. Review the intended release ref and run the regression tests below. The release workflow itself does not run tests or wait for a scanner result.
2. Open **Actions → release → Run workflow** and select the intended ref.
3. Leave `is_prerelease` disabled for a regular release, or enable it for a prerelease.
4. Start the workflow and inspect the **Create version tag** job, then verify the resulting tag and GitHub release.

The job runs on `ubuntu-latest` and grants `contents: write` to create tags and releases. Its single step calls `glueckkanja/action-semantic-version`, pinned to commit `f28349c3cc2ec7845960c583796a3b9acc54720a` (v3.0.2), passing `secrets.GITHUB_TOKEN` and the prerelease input.

Version calculation, tag naming, and release creation are delegated to that external action. This repository does not implement its own version-bump rules. Consult the [pinned action source](https://github.com/glueckkanja/action-semantic-version/tree/f28349c3cc2ec7845960c583796a3b9acc54720a) for those details.

The release job exposes the action's `version`, `tag`, `bump_type`, `previous_tag`, and `commit_subject` outputs. No downstream job consumes them in this workflow.

Release runs share one concurrency group and do not cancel an in-progress release. There are no branch restrictions or environment approval gates configured in the workflow. The pipeline has no build, package publishing, or workflow-distribution step; updating consuming repositories is a separate operation.

## Maintenance and local checks

Run the existing regression suite from the repository root:

```sh
python3 -m venv /tmp/zizmor-scanner-tests
/tmp/zizmor-scanner-tests/bin/python -m pip install PyYAML==6.0.3
/tmp/zizmor-scanner-tests/bin/python -m unittest discover -s tests -v
```

The tests exercise Python extracted directly from the workflow and mock scanner responses. They validate fallback and report behavior without performing a live zizmor scan or creating GitHub comments or releases. Neither workflow currently runs this suite automatically.

When updating zizmor or PyYAML, review the new release and update the version and approved wheel hashes together in the scanner workflow. Hashes must remain embedded in the source; they are not fetched during a workflow run. Keep the hashes compatible with the runner's Linux x86_64 environment and Python version.

Dependabot maintains GitHub Actions references. The Python package pins and hashes inside the shell script require separate maintenance. Keep action references pinned to full commit SHAs when updating either workflow.
