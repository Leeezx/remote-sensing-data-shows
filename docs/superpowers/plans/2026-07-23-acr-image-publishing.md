# ACR Image Publishing Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this plan task-by-task. Before changing repository files, use `using-git-worktrees` to create an isolated branch from the latest `origin/main`; the current local `main` is divergent and contains unrelated user work.

**Goal:** Add a manual GitHub Actions release path that builds the backend and frontend images, mirrors the pinned Caddy image, publishes all three images to the user's Alibaba Cloud ACR namespace, and documents a reproducible server deployment that never contacts Docker Hub.

**Architecture:** A dedicated `workflow_dispatch` workflow logs into ACR with GitHub Secrets, builds Linux/amd64 application images from the repository, pulls the pinned upstream Caddy image on the GitHub-hosted runner, and pushes both `latest` and immutable `sha-<12>` tags. The server keeps the existing `docker-compose.yml` as the topology source and adds an ignored `docker-compose.acr.yml` override that replaces each service's image; deployment always passes both Compose files and `--no-build`.

**Tech Stack:** GitHub Actions, Docker Engine/BuildKit, Docker Compose v5, Alibaba Cloud ACR Personal Edition, pytest, PyYAML, Markdown.

---

## Preconditions and non-negotiable constraints

- Base all implementation work on the latest `origin/main` (currently observed at `0a73199`), not the divergent local `main`.
- Preserve all unrelated modified and untracked files in `E:\遥感数据展示网站`.
- Do not commit ACR passwords, Docker auth files, `.env`, raster data, or generated deployment data.
- Keep publishing manual-only: `workflow_dispatch` must be the only trigger in the new workflow.
- Publish only `linux/amd64`, matching the current Alibaba Cloud server.
- Use these ACR coordinates:
  - Registry: `crpi-ax05xaa8wxdezs5y.cn-beijing.personal.cr.aliyuncs.com`
  - Namespace: `rs-data-show`
  - Repositories: `backend`, `frontend`, `edge`
- GitHub repository Secrets already exist: `ACR_REGISTRY`, `ACR_NAMESPACE`, `ACR_USERNAME`, `ACR_PASSWORD`.
- Keep Caddy pinned to `caddy:2.10-alpine`, matching `docker-compose.yml`.

## Task 1: Prepare an isolated implementation branch

**Files:**
- No production file changes.

- [ ] **Step 1: Fetch the latest remote state**

Run from `E:\遥感数据展示网站`:

```powershell
git fetch origin
git status --short
git rev-parse origin/main
```

Expected: fetch succeeds; the existing dirty state is only observed, not modified.

- [ ] **Step 2: Create an isolated worktree from `origin/main`**

Use the `using-git-worktrees` skill. Create branch `codex/acr-image-publishing` from `origin/main`, preferably under the repository's ignored `.worktrees/` directory.

Expected: `git status --short` is empty in the new worktree, and:

```powershell
git merge-base --is-ancestor origin/main HEAD
```

exits `0`.

- [ ] **Step 3: Copy the approved design and this plan into the isolated branch if absent**

Source files in the original workspace:

- `docs/superpowers/specs/2026-07-23-acr-image-publishing-design.md`
- `docs/superpowers/plans/2026-07-23-acr-image-publishing.md`

Use `apply_patch` in the isolated worktree; do not cherry-pick the divergent local branch wholesale.

- [ ] **Step 4: Confirm the starting deployment topology**

```powershell
git status --short
git show HEAD:docker-compose.yml
git show HEAD:Dockerfile.backend
git show HEAD:Dockerfile.frontend
```

Expected: services are `backend`, `frontend`, and `edge`; Caddy is `2.10-alpine`; backend and frontend Dockerfiles match the current production topology.

## Task 2: Add failing regression tests for the publishing contract

**Files:**
- Modify: `backend/tests/test_deployment_config.py`
- Test: `backend/tests/test_deployment_config.py`

- [ ] **Step 1: Add a helper for loading workflow text**

Append near the existing `ROOT` declaration:

```python
PUBLISH_WORKFLOW = ROOT / ".github" / "workflows" / "publish-acr.yml"


def publish_workflow_text():
    return PUBLISH_WORKFLOW.read_text(encoding="utf-8")
```

- [ ] **Step 2: Add tests for manual-only publishing and secret use**

Append:

```python
def test_acr_publish_workflow_is_manual_only_and_uses_secrets():
    workflow = yaml.safe_load(publish_workflow_text())
    assert set(workflow["on"]) == {"workflow_dispatch"}

    text = publish_workflow_text()
    for secret in (
        "ACR_REGISTRY",
        "ACR_NAMESPACE",
        "ACR_USERNAME",
        "ACR_PASSWORD",
    ):
        assert f"secrets.{secret}" in text
```

Note: PyYAML 6 may parse the unquoted YAML key `on` as a boolean under YAML 1.1. Quote the workflow key as `"on":` in the implementation so the test reads it as the literal string.

- [ ] **Step 3: Add tests for image sources, targets, architecture, and tags**

Append:

```python
def test_acr_publish_workflow_publishes_all_runtime_images():
    text = publish_workflow_text()
    assert "--platform linux/amd64" in text
    assert "caddy:2.10-alpine" in text
    for repository in ("backend", "frontend", "edge"):
        assert f"/${{{{ env.ACR_NAMESPACE }}}}/{repository}" in text
    assert "latest" in text
    assert "sha-${GITHUB_SHA::12}" in text
    assert "docker push" in text
```

- [ ] **Step 4: Add a test that keeps the server-only override out of Git**

Append:

```python
def test_server_acr_compose_override_is_ignored():
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "docker-compose.acr.yml" in gitignore
```

- [ ] **Step 5: Run the focused tests and confirm failure**

```powershell
python -m pytest backend/tests/test_deployment_config.py -v
```

Expected: the new tests fail because `.github/workflows/publish-acr.yml` does not exist and `docker-compose.acr.yml` is not ignored. Existing deployment tests should remain green.

## Task 3: Implement the manual ACR publishing workflow

**Files:**
- Create: `.github/workflows/publish-acr.yml`
- Modify: `.gitignore`
- Test: `backend/tests/test_deployment_config.py`

- [ ] **Step 1: Ignore the server-local Compose override**

Add under the environment/deployment portion of `.gitignore`:

```gitignore
# Server-local deployment overrides
docker-compose.acr.yml
```

- [ ] **Step 2: Create the manual publishing workflow**

Create `.github/workflows/publish-acr.yml` with this structure:

```yaml
name: Publish images to ACR

"on":
  workflow_dispatch:

permissions:
  contents: read

env:
  ACR_REGISTRY: ${{ secrets.ACR_REGISTRY }}
  ACR_NAMESPACE: ${{ secrets.ACR_NAMESPACE }}

jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - name: Check out repository
        uses: actions/checkout@v4

      - name: Log in to ACR
        uses: docker/login-action@v3
        with:
          registry: ${{ secrets.ACR_REGISTRY }}
          username: ${{ secrets.ACR_USERNAME }}
          password: ${{ secrets.ACR_PASSWORD }}

      - name: Compute immutable tag
        id: tags
        shell: bash
        run: echo "sha_tag=sha-${GITHUB_SHA::12}" >> "$GITHUB_OUTPUT"

      - name: Build backend image
        run: |
          docker build --platform linux/amd64 \
            --file Dockerfile.backend \
            --tag "${{ env.ACR_REGISTRY }}/${{ env.ACR_NAMESPACE }}/backend:${{ steps.tags.outputs.sha_tag }}" \
            --tag "${{ env.ACR_REGISTRY }}/${{ env.ACR_NAMESPACE }}/backend:latest" \
            .

      - name: Build frontend image
        run: |
          docker build --platform linux/amd64 \
            --file Dockerfile.frontend \
            --tag "${{ env.ACR_REGISTRY }}/${{ env.ACR_NAMESPACE }}/frontend:${{ steps.tags.outputs.sha_tag }}" \
            --tag "${{ env.ACR_REGISTRY }}/${{ env.ACR_NAMESPACE }}/frontend:latest" \
            .

      - name: Mirror edge image
        run: |
          docker pull --platform linux/amd64 caddy:2.10-alpine
          docker tag caddy:2.10-alpine \
            "${{ env.ACR_REGISTRY }}/${{ env.ACR_NAMESPACE }}/edge:${{ steps.tags.outputs.sha_tag }}"
          docker tag caddy:2.10-alpine \
            "${{ env.ACR_REGISTRY }}/${{ env.ACR_NAMESPACE }}/edge:latest"

      - name: Push immutable images
        run: |
          docker push "${{ env.ACR_REGISTRY }}/${{ env.ACR_NAMESPACE }}/backend:${{ steps.tags.outputs.sha_tag }}"
          docker push "${{ env.ACR_REGISTRY }}/${{ env.ACR_NAMESPACE }}/frontend:${{ steps.tags.outputs.sha_tag }}"
          docker push "${{ env.ACR_REGISTRY }}/${{ env.ACR_NAMESPACE }}/edge:${{ steps.tags.outputs.sha_tag }}"

      - name: Update latest images
        run: |
          docker push "${{ env.ACR_REGISTRY }}/${{ env.ACR_NAMESPACE }}/backend:latest"
          docker push "${{ env.ACR_REGISTRY }}/${{ env.ACR_NAMESPACE }}/frontend:latest"
          docker push "${{ env.ACR_REGISTRY }}/${{ env.ACR_NAMESPACE }}/edge:latest"
```

Implementation notes:

- Keep `latest` pushes after all immutable pushes, so a partial build/push failure does not prematurely advance `latest`.
- Do not add `push`, `pull_request`, `schedule`, or `workflow_call` triggers.
- Do not use repository literals for credentials; only reference Secrets.
- Keep the upstream Caddy tag synchronized with `docker-compose.yml`.

- [ ] **Step 3: Run focused deployment tests**

```powershell
python -m pytest backend/tests/test_deployment_config.py -v
```

Expected: all tests pass.

- [ ] **Step 4: Validate the workflow YAML as loaded by PyYAML**

```powershell
python -c "from pathlib import Path; import yaml; p=Path('.github/workflows/publish-acr.yml'); d=yaml.safe_load(p.read_text(encoding='utf-8')); assert set(d['on']) == {'workflow_dispatch'}; assert set(d['jobs']) == {'publish'}; print('workflow YAML OK')"
```

Expected: `workflow YAML OK`.

- [ ] **Step 5: Commit the workflow contract**

```powershell
git add .github/workflows/publish-acr.yml .gitignore backend/tests/test_deployment_config.py
git commit -m "feat: publish deployment images to ACR"
```

## Task 4: Add a reproducible ACR server deployment guide

**Files:**
- Create: `docs/deployment-acr.md`
- Modify: `backend/tests/test_deployment_config.py`
- Test: `backend/tests/test_deployment_config.py`

- [ ] **Step 1: Add a failing documentation contract test**

Append:

```python
def test_acr_deployment_guide_uses_override_and_disables_builds():
    guide = (ROOT / "docs" / "deployment-acr.md").read_text(encoding="utf-8")
    assert "docker-compose.acr.yml" in guide
    assert "--no-build" in guide
    assert "IMAGE_TAG=sha-" in guide
    assert "docker login" in guide
    assert "registry-1.docker.io" not in guide
```

- [ ] **Step 2: Run the test and confirm it fails**

```powershell
python -m pytest backend/tests/test_deployment_config.py::test_acr_deployment_guide_uses_override_and_disables_builds -v
```

Expected: failure because `docs/deployment-acr.md` does not exist.

- [ ] **Step 3: Write `docs/deployment-acr.md`**

The guide must include:

1. Running **Actions → Publish images to ACR → Run workflow**.
2. Recording the immutable tag shown by the workflow, for example `sha-0123456789ab`.
3. Logging the server's root Docker client into ACR without putting the password on the command line:

```bash
read -rp 'ACR username: ' ACR_USERNAME
sudo docker login \
  crpi-ax05xaa8wxdezs5y.cn-beijing.personal.cr.aliyuncs.com \
  --username "$ACR_USERNAME"
unset ACR_USERNAME
```

4. Adding non-secret coordinates to `/opt/remote-sensing/.env`:

```dotenv
ACR_REGISTRY=crpi-ax05xaa8wxdezs5y.cn-beijing.personal.cr.aliyuncs.com
ACR_NAMESPACE=rs-data-show
IMAGE_TAG=sha-0123456789ab
```

5. Creating `/opt/remote-sensing/docker-compose.acr.yml`:

```yaml
services:
  edge:
    image: ${ACR_REGISTRY}/${ACR_NAMESPACE}/edge:${IMAGE_TAG:-latest}
  frontend:
    image: ${ACR_REGISTRY}/${ACR_NAMESPACE}/frontend:${IMAGE_TAG:-latest}
  backend:
    image: ${ACR_REGISTRY}/${ACR_NAMESPACE}/backend:${IMAGE_TAG:-latest}
```

6. Validating, pulling, and starting with both Compose files every time:

```bash
cd /opt/remote-sensing
sudo docker compose \
  -f docker-compose.yml \
  -f docker-compose.acr.yml \
  config --quiet
sudo docker compose \
  -f docker-compose.yml \
  -f docker-compose.acr.yml \
  pull
sudo docker compose \
  -f docker-compose.yml \
  -f docker-compose.acr.yml \
  up -d --no-build --pull never
```

7. Verifying containers and HTTP endpoints:

```bash
sudo docker compose \
  -f docker-compose.yml \
  -f docker-compose.acr.yml \
  ps
sudo docker compose \
  -f docker-compose.yml \
  -f docker-compose.acr.yml \
  logs --tail=100 backend frontend edge
curl -fsS http://127.0.0.1/api/ready
curl -I http://127.0.0.1/
```

8. Updating by changing `IMAGE_TAG` to a newer immutable tag, then repeating `pull` and `up`.
9. Rolling back by restoring the prior `IMAGE_TAG`, then repeating `pull` and `up`.
10. A warning that running only the base Compose file reintroduces Docker Hub/build behavior.

- [ ] **Step 4: Run the focused tests**

```powershell
python -m pytest backend/tests/test_deployment_config.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit the guide**

```powershell
git add docs/deployment-acr.md backend/tests/test_deployment_config.py
git commit -m "docs: add ACR deployment runbook"
```

## Task 5: Verify the repository change before publishing

**Files:**
- Verify all changed files from Tasks 2–4.

- [ ] **Step 1: Run the complete backend test suite**

```powershell
python -m pytest backend/tests/ -v
```

Expected: all backend tests pass.

- [ ] **Step 2: Run frontend tests, lint, and production build**

```powershell
npm --prefix frontend test
npm --prefix frontend run lint
npm run build
```

Expected: each command exits `0`.

- [ ] **Step 3: Inspect the final diff and commits**

```powershell
git status --short
git diff origin/main...HEAD --check
git diff --stat origin/main...HEAD
git log --oneline origin/main..HEAD
```

Expected: no whitespace errors; only the approved design/plan, ACR workflow, deployment test updates, `.gitignore`, and ACR deployment guide differ from `origin/main`.

- [ ] **Step 4: Request code review**

Use the `requesting-code-review` skill. Address any correctness issue before pushing.

## Task 6: Publish the branch and run GitHub Actions

**Files:**
- No additional repository changes unless review finds an issue.

- [ ] **Step 1: Push the isolated branch**

```powershell
git push -u origin codex/acr-image-publishing
```

- [ ] **Step 2: Open and merge a pull request into `main`**

The PR must mention:

- manual-only trigger;
- images and tags produced;
- the four required GitHub Secrets;
- validation commands from Task 5;
- no Docker Hub access is required from the Alibaba Cloud server after deployment.

- [ ] **Step 3: Run the workflow manually on merged `main`**

In GitHub: **Actions → Publish images to ACR → Run workflow → Branch: main**.

Expected: backend, frontend, and edge builds/mirroring succeed; six pushes complete (three immutable tags and three `latest` tags).

- [ ] **Step 4: Record the immutable release tag**

If the merged commit SHA begins with `0123456789ab`, record:

```text
IMAGE_TAG=sha-0123456789ab
```

Use the actual 12-character prefix shown by the workflow.

## Task 7: Deploy the immutable ACR release on the Alibaba Cloud server

**Files on server:**
- Modify: `/opt/remote-sensing/.env`
- Create: `/opt/remote-sensing/docker-compose.acr.yml` (ignored by Git)

- [ ] **Step 1: Pull the merged repository changes without touching mounted data**

On the server:

```bash
cd /opt/remote-sensing
git status --short
git pull --ff-only origin main
findmnt /opt/remote-sensing/data
```

Expected: the Git worktree is clean before pull; pull fast-forwards; the bind mount still resolves to `/dev/vdb1[/remote-sensing/data]`.

- [ ] **Step 2: Authenticate Docker to ACR**

Follow `docs/deployment-acr.md`. Use the ACR username interactively and enter the ACR password only at Docker's password prompt.

- [ ] **Step 3: Set the exact immutable image tag**

Edit `/opt/remote-sensing/.env` to contain the ACR registry, namespace, and the actual `sha-<12>` tag from Task 6. Preserve the existing runtime values such as `UVICORN_WORKERS=1` and `GDAL_CACHEMAX=256`.

- [ ] **Step 4: Create the local ACR Compose override**

Create `/opt/remote-sensing/docker-compose.acr.yml` exactly as documented. Then confirm it is ignored:

```bash
git status --short
git check-ignore -v docker-compose.acr.yml
```

Expected: `git status --short` remains empty; `git check-ignore` points to the new `.gitignore` rule.

- [ ] **Step 5: Validate and pull from ACR**

```bash
sudo docker compose \
  -f docker-compose.yml \
  -f docker-compose.acr.yml \
  config --quiet
sudo docker compose \
  -f docker-compose.yml \
  -f docker-compose.acr.yml \
  pull
```

Expected: all three image references use the ACR hostname and pull successfully; output must not show `registry-1.docker.io`.

- [ ] **Step 6: Start without local builds**

```bash
sudo docker compose \
  -f docker-compose.yml \
  -f docker-compose.acr.yml \
  up -d --no-build --pull never
```

Expected: Compose creates/starts `backend`, `frontend`, and `edge` from already-pulled ACR images.

- [ ] **Step 7: Verify health and routing**

```bash
sudo docker compose \
  -f docker-compose.yml \
  -f docker-compose.acr.yml \
  ps
sudo docker compose \
  -f docker-compose.yml \
  -f docker-compose.acr.yml \
  logs --tail=100 backend frontend edge
curl -fsS http://127.0.0.1/api/ready
curl -I http://127.0.0.1/
```

Expected: all three services are running/healthy; readiness returns success; the root request returns an HTTP response through Caddy.

- [ ] **Step 8: Confirm deployment data remains available**

```bash
findmnt /opt/remote-sensing/data
du -sh /opt/remote-sensing/data/rasters
test -f /opt/remote-sensing/data/vectors/irrigation/county/china_county.shp
```

Expected: bind mount is intact, raster size remains about 45 GB, and the normalized county Shapefile exists.

## Task 8: Verify external access and document rollback

**Files:**
- No repository changes unless deployment reveals a documented correction.

- [ ] **Step 1: Confirm Alibaba Cloud firewall rules**

In the Simple Application Server console, allow inbound TCP `80`; allow TCP `443` when a domain is configured. Do not expose ports `8000` or `8080` publicly.

- [ ] **Step 2: Test from a browser or a machine outside the server**

Open the public IP (HTTP) or configured domain (HTTPS). Verify the application loads and at least one raster/API request succeeds.

- [ ] **Step 3: Record rollback coordinates**

Keep the previous working `IMAGE_TAG=sha-<12>` value. Rollback consists only of restoring that tag in `.env`, then rerunning the documented `pull` and `up -d --no-build --pull never` commands with both Compose files.

- [ ] **Step 4: Final evidence capture**

Capture:

- successful GitHub Actions run URL;
- deployed immutable tag;
- `docker compose ... ps` output;
- `/api/ready` response;
- public URL response;
- confirmation that `git status --short` is clean on the server.

Only then declare the deployment complete.
