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

In GitHub, open **Actions → Publish images to ACR → Run workflow**, select `main`, and run it.

Expected: checkout, ACR login, backend build, frontend build, edge mirror, immutable pushes, and latest pushes all succeed.

- [ ] **Step 2: Derive the immutable tag from merged main**

From the local repository:

```powershell
git fetch origin
$mergedSha = git rev-parse origin/main
$imageTag = "sha-$($mergedSha.Substring(0, 12))"
$imageTag
```

Expected: output is one exact tag in `sha-xxxxxxxxxxxx` format; use this value in the following server step.

- [ ] **Step 3: Pull the merged code on the server**

```bash
cd /opt/remote-sensing
git status --short
git pull --ff-only origin main
findmnt /opt/remote-sensing/data
```

Expected: Git remains clean, pull fast-forwards, and the data bind mount remains `/dev/vdb1[/remote-sensing/data]`.

- [ ] **Step 4: Remove the temporary healthcheck override**

Replace `/opt/remote-sensing/docker-compose.acr.yml` with image-only overrides:

```bash
tee docker-compose.acr.yml >/dev/null <<'EOF'
services:
  edge:
    image: ${ACR_REGISTRY}/${ACR_NAMESPACE}/edge:${IMAGE_TAG:-latest}
  frontend:
    image: ${ACR_REGISTRY}/${ACR_NAMESPACE}/frontend:${IMAGE_TAG:-latest}
  backend:
    image: ${ACR_REGISTRY}/${ACR_NAMESPACE}/backend:${IMAGE_TAG:-latest}
EOF
```

- [ ] **Step 5: Set the new immutable tag**

Derive the tag from the merged commit now checked out on the server, then persist it:

```bash
cd /opt/remote-sensing
IMAGE_TAG="sha-$(git rev-parse --short=12 HEAD)"
sed -i '/^IMAGE_TAG=/d' /opt/remote-sensing/.env
printf '%s\n' "IMAGE_TAG=$IMAGE_TAG" >> /opt/remote-sensing/.env
chmod 600 /opt/remote-sensing/.env
printf 'Deploying %s\n' "$IMAGE_TAG"
```

Expected: the printed value exactly matches the tag derived in Task 4 Step 2 and published by the successful workflow run.

- [ ] **Step 6: Verify the merged healthcheck before deployment**

```bash
sudo docker compose \
  -f docker-compose.yml \
  -f docker-compose.acr.yml \
  config | sed -n '/frontend:/,/logging:/p'
```

Expected: the effective frontend healthcheck contains `http://127.0.0.1:8080/` even though `docker-compose.acr.yml` no longer defines a healthcheck.

- [ ] **Step 7: Pull and start the corrected release**

```bash
sudo docker compose \
  -f docker-compose.yml \
  -f docker-compose.acr.yml \
  pull
sudo docker compose \
  -f docker-compose.yml \
  -f docker-compose.acr.yml \
  up -d --no-build --pull never
```

Expected: all three ACR images pull and Compose starts backend, frontend, and edge without the temporary healthcheck override.

- [ ] **Step 8: Verify services, routing, and data**

```bash
sudo docker compose \
  -f docker-compose.yml \
  -f docker-compose.acr.yml \
  ps
curl -fsS http://127.0.0.1/api/ready
echo
curl -I http://127.0.0.1/
findmnt /opt/remote-sensing/data
```

Expected: all three containers are healthy, readiness returns `{"status":"ready","dependencies":[]}`, the root path returns HTTP 200 via Caddy, and the data mount is intact.

- [ ] **Step 9: Preserve the rollback command**

If verification fails, restore the known-good release:

```bash
sed -i '/^IMAGE_TAG=/d' /opt/remote-sensing/.env
printf '%s\n' 'IMAGE_TAG=sha-cbc85d334080' >> /opt/remote-sensing/.env
sudo docker compose \
  -f docker-compose.yml \
  -f docker-compose.acr.yml \
  pull
sudo docker compose \
  -f docker-compose.yml \
  -f docker-compose.acr.yml \
  up -d --no-build --pull never
```

Expected: the previously verified release returns to service without modifying the data disk.
