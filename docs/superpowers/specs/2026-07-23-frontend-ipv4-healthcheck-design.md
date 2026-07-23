# Frontend IPv4 Healthcheck Fix Design

## Problem

The deployed frontend container runs nginx successfully and serves the site on `127.0.0.1:8080`, but Docker reports the container as unhealthy. The frontend healthcheck requests `http://localhost:8080/`. In the production Alpine container, `localhost` resolves to IPv6 `[::1]`, while the nginx server block listens only on IPv4 port 8080. Every probe therefore receives `Connection refused`. Because the edge service depends on a healthy frontend, Caddy does not start and host ports 80 and 443 remain unavailable.

Production diagnostics confirmed the boundary precisely:

- `nginx -t` succeeds;
- `wget http://localhost:8080/` connects to `[::1]` and fails;
- `wget http://127.0.0.1:8080/` returns HTTP 200;
- overriding only the probe URL makes the frontend healthy and starts Caddy successfully.

## Chosen approach

Use the explicit IPv4 loopback address in both definitions of the frontend healthcheck:

- `docker-compose.yml`, which controls normal Compose deployments;
- `Dockerfile.frontend`, which supplies the image-level fallback healthcheck.

This is the smallest change that matches the nginx listener already used in production. The fix does not add an IPv6 listener, change proxy behavior, modify application code, or alter ports and mounts.

## Alternatives rejected

### Add an IPv6 nginx listener

Adding `listen [::]:8080` would make the existing hostname probe succeed, but it expands the server's listening behavior to solve a local probe ambiguity. It also introduces platform-dependent dual-stack binding considerations that are unnecessary for the current container network.

### Keep only the server-local Compose override

The temporary override restores the current deployment, but every new environment using the repository defaults would reproduce the failure. The repository must contain the correct healthcheck contract.

## Files and behavior

`docker-compose.yml` will change the frontend healthcheck target from `http://localhost:8080/` to `http://127.0.0.1:8080/`.

`Dockerfile.frontend` will make the same substitution in its `HEALTHCHECK` instruction.

`backend/tests/test_deployment_config.py` will assert the exact IPv4 URL in the Compose healthcheck and the Dockerfile, and will reject `localhost:8080` in both sources. This prevents either definition from drifting back to the production-breaking hostname.

## Verification

Implementation will follow a red-green test cycle:

1. Add the deployment configuration regression test and confirm it fails against the current `localhost` definitions.
2. Change only the two healthcheck URLs.
3. Run the focused deployment configuration tests.
4. Run the complete backend suite, frontend tests, lint, and production frontend build.

After merge, manually run `Publish images to ACR` on `main`. Deploy the resulting immutable `sha-<12>` tag, pull all three images through the existing ACR override, and verify:

- backend, frontend, and edge are healthy;
- `/api/ready` returns ready;
- `/` returns HTTP 200 through Caddy;
- the data bind mount remains intact.

## Rollout and rollback

The currently working server release `sha-cbc85d334080` remains available throughout the change. The server-local frontend healthcheck override stays in place until the corrected release is pulled and verified. Rollback restores `IMAGE_TAG=sha-cbc85d334080` and reruns the existing Compose pull and start commands; no data migration or cache reset is required.
