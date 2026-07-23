# Frontend IPv4 Healthcheck Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permanently prevent the frontend container from becoming unhealthy when `localhost` resolves to IPv6 but nginx listens only on IPv4.

**Architecture:** Keep nginx and the service topology unchanged. Make both the Compose-level and image-level frontend healthchecks probe the explicit IPv4 loopback address, and enforce the shared contract with the existing deployment configuration test suite. Publish a new immutable ACR release, then remove the temporary server healthcheck override so production exercises the repository fix.

**Tech Stack:** Docker Compose, Dockerfile, nginx-unprivileged, pytest, PyYAML, GitHub Actions, Alibaba Cloud ACR.

## Global Constraints

- Use `http://127.0.0.1:8080/` in both frontend healthcheck definitions.
- Do not add an IPv6 nginx listener.
- Do not change proxy behavior, application code, ports, volumes, or data mounts.
- Preserve the current working release `sha-cbc85d334080` for rollback.
- Implement on branch `codex/fix-frontend-healthcheck`, based on merged `origin/main` commit `cbc85d3`.
- Use a failing regression test before changing either production configuration file.

---

### Task 1: Lock the frontend healthcheck to IPv4

**Files:**
- Modify: `backend/tests/test_deployment_config.py`
- Modify: `docker-compose.yml`
- Modify: `Dockerfile.frontend`
- Test: `backend/tests/test_deployment_config.py`

**Interfaces:**
- Consumes: the existing `compose() -> dict` test helper and the frontend service's Docker healthcheck contract.
- Produces: a Compose healthcheck command and Dockerfile `HEALTHCHECK` that both request `http://127.0.0.1:8080/`.

- [ ] **Step 1: Verify the isolated branch baseline**

Run:

```powershell
git status --short
git rev-parse HEAD
python -m pytest backend/tests/test_deployment_config.py -v
```

Expected: clean worktree before plan artifacts, HEAD descends from `cbc85d3`, and all existing deployment configuration tests pass.

- [ ] **Step 2: Write the failing regression test**

Append to `backend/tests/test_deployment_config.py`:

```python
def test_frontend_healthchecks_use_explicit_ipv4_loopback():
    compose_healthcheck = compose()["services"]["frontend"]["healthcheck"]["test"]
    assert compose_healthcheck == [
        "CMD",
        "wget",
        "-qO-",
        "http://127.0.0.1:8080/",
    ]

    dockerfile = (ROOT / "Dockerfile.frontend").read_text(encoding="utf-8")
    assert "wget -qO- http://127.0.0.1:8080/" in dockerfile
    assert "http://localhost:8080/" not in dockerfile
```

- [ ] **Step 3: Run the regression test and verify RED**

Run:

```powershell
python -m pytest backend/tests/test_deployment_config.py::test_frontend_healthchecks_use_explicit_ipv4_loopback -v
```

Expected: FAIL because Compose currently contains `http://localhost:8080/`; the Dockerfile assertion also would not match the current image healthcheck.

- [ ] **Step 4: Change the Compose healthcheck target**

In `docker-compose.yml`, replace the frontend healthcheck with exactly:

```yaml
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://127.0.0.1:8080/"]
      interval: 30s
      timeout: 5s
      retries: 3
```

- [ ] **Step 5: Change the image healthcheck target**

In `Dockerfile.frontend`, replace the final instruction with exactly:

```dockerfile
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget -qO- http://127.0.0.1:8080/ >/dev/null || exit 1
```

- [ ] **Step 6: Run focused tests and verify GREEN**

Run:

```powershell
python -m pytest backend/tests/test_deployment_config.py -v
```

Expected: all deployment configuration tests pass, including `test_frontend_healthchecks_use_explicit_ipv4_loopback`.

- [ ] **Step 7: Check the focused diff**

Run:

```powershell
git diff --check
git diff -- docker-compose.yml Dockerfile.frontend backend/tests/test_deployment_config.py
```

Expected: only the two URL substitutions and the regression test are present; no whitespace errors.

- [ ] **Step 8: Commit the tested fix**

```powershell
git add docker-compose.yml Dockerfile.frontend backend/tests/test_deployment_config.py
git commit -m "fix: use IPv4 frontend healthchecks"
```

### Task 2: Verify the complete repository

**Files:**
- Verify: `backend/tests/`
- Verify: `frontend/`
- Verify: repository diff against `origin/main`

**Interfaces:**
- Consumes: the configuration change from Task 1.
- Produces: test, lint, build, and diff evidence suitable for the pull request.

- [ ] **Step 1: Run the complete backend suite**

```powershell
python -m pytest backend/tests/ -v
```

Expected: all backend tests pass with zero failures.

- [ ] **Step 2: Install locked Node dependencies if absent**

```powershell
npm ci
npm --prefix frontend ci
```

Expected: both commands exit `0`; generated `node_modules/` directories remain ignored.

- [ ] **Step 3: Run frontend tests**

```powershell
npm --prefix frontend test
```

Expected: all Vitest files and tests pass.

- [ ] **Step 4: Run frontend lint**

```powershell
npm --prefix frontend run lint
```

Expected: exit `0`. The pre-existing `MapView.tsx` exhaustive-deps warning may remain, but this change must introduce no new lint error.

- [ ] **Step 5: Run the production build**

```powershell
npm run build
```

Expected: TypeScript and Vite build successfully.

- [ ] **Step 6: Review final scope**

```powershell
git status --short
git diff origin/main...HEAD --check
git diff --stat origin/main...HEAD
git log --oneline origin/main..HEAD
```

Expected: the branch contains the approved design and plan documents plus the two URL substitutions and regression test; no unrelated application or data changes.

### Task 3: Review, push, and merge the permanent fix

**Files:**
- No new file changes unless review finds a correctness issue.

**Interfaces:**
- Consumes: verified commits from Tasks 1 and 2.
- Produces: merged `main` containing the permanent IPv4 healthcheck contract.

- [ ] **Step 1: Perform final code review**

Review the diff for these exact conditions:

- Compose and Dockerfile both use `127.0.0.1`.
- Neither healthcheck contains `localhost:8080`.
- nginx configuration is unchanged.
- no credential, `.env`, raster, or server-local override is committed.

- [ ] **Step 2: Push the branch**

```powershell
git push -u origin codex/fix-frontend-healthcheck
```

Expected: the remote branch is created and tracks the local branch.

- [ ] **Step 3: Create a draft pull request**

Create a PR from `codex/fix-frontend-healthcheck` to `main` with title:

```text
fix: use IPv4 frontend healthchecks
```

The PR body must include the production evidence (`localhost -> [::1]` failed; `127.0.0.1` returned 200), the two configuration files changed, regression coverage, and the complete validation commands.

- [ ] **Step 4: Merge after checks pass**

Expected: `origin/main` advances to a merge commit that contains the fix and the GitHub CI workflow is green.

### Task 4: Publish and deploy the corrected immutable release

**Files on server:**
- Update: `/opt/remote-sensing/.env`
- Update: `/opt/remote-sensing/docker-compose.acr.yml`

**Interfaces:**
- Consumes: merged `main`, GitHub Secrets, and the existing three ACR repositories.
- Produces: a production deployment where the base Compose file itself supplies the correct frontend healthcheck.

- [ ] **Step 1: Run the ACR workflow on merged `main`**

In GitHub, open **Actions → Publish images to ACR → Run workflow**, select `main`, and run it. Wait for that manually dispatched run to finish successfully before continuing.

Expected: checkout, ACR login, backend build, frontend build, edge mirror, immutable pushes, and latest pushes all succeed.

- [ ] **Step 2: Record the exact successful workflow SHA and immutable image tag**

Run this PowerShell from the local repository. It uses GitHub's public Actions API rather than `gh`, selects the newest successful `workflow_dispatch` run for `publish-acr.yml` on `main`, and records the run's immutable `head_sha` exactly once.

```powershell
$originUrl = (git remote get-url origin).Trim()
if ($originUrl -notmatch 'github\.com[:/](?<repo>[^/]+/[^/]+?)(?:\.git)?/?$') {
    throw "Cannot derive the GitHub owner/repository from origin: $originUrl"
}
$repository = $Matches['repo']
$headers = @{
    Accept = 'application/vnd.github+json'
    'X-GitHub-Api-Version' = '2022-11-28'
    'User-Agent' = 'remote-sensing-rollout'
}
$runsUri = "https://api.github.com/repos/$repository/actions/workflows/publish-acr.yml/runs?branch=main&event=workflow_dispatch&status=success&per_page=1"
$response = Invoke-RestMethod -Uri $runsUri -Headers $headers
$workflowRun = $response.workflow_runs | Sort-Object created_at -Descending | Select-Object -First 1
if ($null -eq $workflowRun) {
    throw 'No successful manual publish-acr.yml run was found on main.'
}
if ($workflowRun.event -ne 'workflow_dispatch' -or $workflowRun.head_branch -ne 'main' -or $workflowRun.conclusion -ne 'success') {
    throw 'The selected workflow run does not meet the required main/workflow_dispatch/success criteria.'
}
$workflowSha = [string]$workflowRun.head_sha
if ($workflowSha -notmatch '^[0-9a-f]{40}$') {
    throw "Unexpected workflow head_sha: $workflowSha"
}
$imageTag = "sha-$($workflowSha.Substring(0, 12))"
[pscustomobject]@{
    html_url = $workflowRun.html_url
    head_sha = $workflowSha
    image_tag = $imageTag
} | Format-List
Write-Output "WORKFLOW_SHA=$workflowSha"
Write-Output "IMAGE_TAG=$imageTag"
```

Copy the printed `html_url`, `head_sha`, and `image_tag` to the deployment record. Copy the two final output lines, exactly as printed, to the server operator: `WORKFLOW_SHA=<40 hex>` and `IMAGE_TAG=sha-<12 hex>`. Keep `$workflowSha` and `$imageTag` in the same PowerShell session; they are the sole deployment identity for every remaining step. Do not derive a tag from a later `origin/main`, local `HEAD`, or server `HEAD`.

Expected: one `html_url`, a 40-character `head_sha`, and exactly one `sha-xxxxxxxxxxxx` tag, all tied to the selected successful workflow run.

- [ ] **Step 3: Verify that the successful run contains the healthcheck fix**

Use the SHA captured in Step 2; fetching `main` only obtains the commit object and is not a tag derivation.

```powershell
git fetch origin main
git cat-file -e "$workflowSha^{commit}"
if ($LASTEXITCODE -ne 0) {
    throw "The selected workflow head_sha is not available locally: $workflowSha"
}
git merge-base --is-ancestor b1a417d $workflowSha
if ($LASTEXITCODE -ne 0) {
    throw "Workflow run $($workflowRun.html_url) does not contain b1a417d in its ancestry."
}
Write-Host "Verified b1a417d is an ancestor of $workflowSha; deploying $imageTag."
```

Expected: the ancestry check exits `0`; the workflow-run SHA, not a moving branch reference, remains the recorded source of `$imageTag`.

- [ ] **Step 4: Fast-forward the server checkout to the exact workflow commit while retaining the temporary IPv4 override**

On the server, paste the two exact assignment lines printed in Step 2. Do not calculate either value with Git on the server. Before reading Compose configuration or changing `.env`, validate both values, require a clean tracked worktree, fetch from origin, switch to `main`, and fast-forward only to `WORKFLOW_SHA`. Keep this SSH shell open through Step 8 so the validated variables remain in scope. Keep the existing `docker-compose.acr.yml` intact: it must still define the explicit IPv4 frontend healthcheck during this first deployment verification.

```bash
cd /opt/remote-sensing
WORKFLOW_SHA='REPLACE-WITH-THE-STEP-2-WORKFLOW_SHA'
IMAGE_TAG='REPLACE-WITH-THE-STEP-2-IMAGE_TAG'
if ! [[ "$WORKFLOW_SHA" =~ ^[0-9a-f]{40}$ ]]; then
  echo "Invalid recorded workflow SHA: $WORKFLOW_SHA" >&2
  exit 1
fi
if ! [[ "$IMAGE_TAG" =~ ^sha-[0-9a-f]{12}$ ]]; then
  echo "Invalid recorded image tag: $IMAGE_TAG" >&2
  exit 1
fi
if [[ "$IMAGE_TAG" != "sha-${WORKFLOW_SHA:0:12}" ]]; then
  echo 'IMAGE_TAG does not match the first 12 characters of WORKFLOW_SHA.' >&2
  exit 1
fi
if [[ -n "$(git status --porcelain)" ]]; then
  echo 'Tracked files are dirty; refusing to change the server checkout.' >&2
  git status --short
  exit 1
fi
git fetch origin main
git switch main
if ! git cat-file -e "${WORKFLOW_SHA}^{commit}"; then
  echo "Origin did not provide recorded workflow commit $WORKFLOW_SHA." >&2
  exit 1
fi
if ! git merge-base --is-ancestor HEAD "$WORKFLOW_SHA"; then
  echo "Current main cannot fast-forward to recorded workflow commit $WORKFLOW_SHA." >&2
  exit 1
fi
git merge --ff-only "$WORKFLOW_SHA"
if [[ "$(git rev-parse HEAD)" != "$WORKFLOW_SHA" ]]; then
  echo "Server HEAD is not the recorded workflow commit $WORKFLOW_SHA." >&2
  exit 1
fi
grep -F 'http://127.0.0.1:8080/' docker-compose.acr.yml
sudo docker compose \
  -f docker-compose.yml \
  -f docker-compose.acr.yml \
  config | sed -n '/frontend:/,/logging:/p'
findmnt /opt/remote-sensing/data
```

Expected: the checkout fast-forwards only to the exact recorded `WORKFLOW_SHA`, `git rev-parse HEAD` matches it byte-for-byte, the existing override retains the explicit IPv4 healthcheck, and the data bind mount remains `/dev/vdb1[/remote-sensing/data]`.

- [ ] **Step 5: Validate ACR variables and pull all three recorded immutable images before changing `.env`**

Source the existing `.env` only to obtain the registry and namespace, validate them, then restore the recorded `IMAGE_TAG` before every image pull. Do not run `docker compose pull` in this step because `.env` still contains the previous release tag.

```bash
cd /opt/remote-sensing
recordedImageTag="$IMAGE_TAG"
set -a
. ./.env
set +a
if [[ -z "$ACR_REGISTRY" || -z "$ACR_NAMESPACE" ]]; then
  echo 'ACR_REGISTRY and ACR_NAMESPACE must both be set in .env.' >&2
  exit 1
fi
IMAGE_TAG="$recordedImageTag"
export IMAGE_TAG
sudo docker pull "${ACR_REGISTRY}/${ACR_NAMESPACE}/backend:${IMAGE_TAG}"
sudo docker pull "${ACR_REGISTRY}/${ACR_NAMESPACE}/frontend:${IMAGE_TAG}"
sudo docker pull "${ACR_REGISTRY}/${ACR_NAMESPACE}/edge:${IMAGE_TAG}"
```

Expected: Docker reports a successful pull for backend, frontend, and edge with the same exact `sha-xxxxxxxxxxxx` tag from Step 2; `.env` remains unchanged.

- [ ] **Step 6: Persist the recorded tag and verify the release with the temporary override**

Update `.env` from the validated recorded `IMAGE_TAG`, start all three services without any additional pulls, and verify the first deployment while the server-local explicit IPv4 override is still present.

```bash
cd /opt/remote-sensing
sed -i '/^IMAGE_TAG=/d' .env
printf '%s\n' "IMAGE_TAG=$IMAGE_TAG" >> .env
chmod 600 .env
export IMAGE_TAG
printf 'Deploying recorded workflow tag %s\n' "$IMAGE_TAG"
sudo docker compose \
  -f docker-compose.yml \
  -f docker-compose.acr.yml \
  up -d --no-build --pull never --force-recreate backend frontend edge
sudo docker compose \
  -f docker-compose.yml \
  -f docker-compose.acr.yml \
  ps
curl -fsS http://127.0.0.1/api/ready
echo
curl -fsSI http://127.0.0.1/
findmnt /opt/remote-sensing/data
```

Expected: backend, frontend, and edge are healthy; readiness returns `{"status":"ready","dependencies":[]}`; Caddy returns HTTP 200 for `/`; and the data mount is intact. Do not remove the temporary override unless every check passes.

- [ ] **Step 7: Replace the temporary override with image-only overrides and confirm the base healthcheck**

Only after Step 6 passes, replace `/opt/remote-sensing/docker-compose.acr.yml` with these image-only service overrides. The base `docker-compose.yml` must now supply the frontend healthcheck.

```bash
cd /opt/remote-sensing
tee docker-compose.acr.yml >/dev/null <<'EOF'
services:
  edge:
    image: ${ACR_REGISTRY}/${ACR_NAMESPACE}/edge:${IMAGE_TAG:-latest}
  frontend:
    image: ${ACR_REGISTRY}/${ACR_NAMESPACE}/frontend:${IMAGE_TAG:-latest}
  backend:
    image: ${ACR_REGISTRY}/${ACR_NAMESPACE}/backend:${IMAGE_TAG:-latest}
EOF
sudo docker compose \
  -f docker-compose.yml \
  -f docker-compose.acr.yml \
  config | sed -n '/frontend:/,/logging:/p'
```

Expected: `docker-compose.acr.yml` contains no `healthcheck`, while the effective frontend service displays `http://127.0.0.1:8080/` from the base Compose file.

- [ ] **Step 8: Force-recreate frontend and edge with image-only overrides, then verify again**

Use the same exported recorded `IMAGE_TAG` from Step 6. Do not recompute or replace it.

```bash
cd /opt/remote-sensing
if [[ "$IMAGE_TAG" != "sha-${WORKFLOW_SHA:0:12}" ]]; then
  echo "Refusing to recreate services: IMAGE_TAG=$IMAGE_TAG does not match WORKFLOW_SHA=$WORKFLOW_SHA." >&2
  exit 1
fi
sudo docker compose \
  -f docker-compose.yml \
  -f docker-compose.acr.yml \
  up -d --no-build --pull never --force-recreate frontend edge
sudo docker compose \
  -f docker-compose.yml \
  -f docker-compose.acr.yml \
  ps
curl -fsS http://127.0.0.1/api/ready
echo
curl -fsSI http://127.0.0.1/
findmnt /opt/remote-sensing/data
```

Expected: frontend and edge are recreated from the recorded immutable images, all three containers are healthy, readiness returns `{"status":"ready","dependencies":[]}`, Caddy returns HTTP 200 for `/`, and the data mount remains intact.

- [ ] **Step 9: Roll back exactly if either verification fails**

This rollback is self-contained and may be run from a fresh SSH shell. Source and validate the ACR variables before changing `.env` or pulling. Then restore the temporary explicit IPv4 frontend healthcheck override first, set the separate exact rollback tag, pull its three images, start the services, and run the same health, routing, and data checks. Do not reset the data disk.

```bash
cd /opt/remote-sensing
set -a
. /opt/remote-sensing/.env
set +a
if [[ -z "$ACR_REGISTRY" || -z "$ACR_NAMESPACE" ]]; then
  echo 'ACR_REGISTRY and ACR_NAMESPACE must both be set in .env.' >&2
  exit 1
fi
ROLLBACK_IMAGE_TAG='sha-cbc85d334080'
tee docker-compose.acr.yml >/dev/null <<'EOF'
services:
  edge:
    image: ${ACR_REGISTRY}/${ACR_NAMESPACE}/edge:${IMAGE_TAG:-latest}
  frontend:
    image: ${ACR_REGISTRY}/${ACR_NAMESPACE}/frontend:${IMAGE_TAG:-latest}
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://127.0.0.1:8080/"]
      interval: 30s
      timeout: 5s
      retries: 3
  backend:
    image: ${ACR_REGISTRY}/${ACR_NAMESPACE}/backend:${IMAGE_TAG:-latest}
EOF
sed -i '/^IMAGE_TAG=/d' .env
printf '%s\n' "IMAGE_TAG=$ROLLBACK_IMAGE_TAG" >> .env
chmod 600 .env
export IMAGE_TAG="$ROLLBACK_IMAGE_TAG"
sudo docker pull "${ACR_REGISTRY}/${ACR_NAMESPACE}/backend:${ROLLBACK_IMAGE_TAG}"
sudo docker pull "${ACR_REGISTRY}/${ACR_NAMESPACE}/frontend:${ROLLBACK_IMAGE_TAG}"
sudo docker pull "${ACR_REGISTRY}/${ACR_NAMESPACE}/edge:${ROLLBACK_IMAGE_TAG}"
sudo docker compose \
  -f docker-compose.yml \
  -f docker-compose.acr.yml \
  up -d --no-build --pull never --force-recreate backend frontend edge
sudo docker compose \
  -f docker-compose.yml \
  -f docker-compose.acr.yml \
  ps
curl -fsS http://127.0.0.1/api/ready
echo
curl -fsSI http://127.0.0.1/
findmnt /opt/remote-sensing/data
```

Expected: the previously verified `sha-cbc85d334080` release is healthy with the explicit IPv4 protection restored, Caddy returns HTTP 200, and the data disk is unchanged.
