# Connect Application Server A to the middleware repository

## Server and repository

```text
Server: 65.109.65.169
Role: Codestra Application Server A
Repository: appolon1908-hue/Middleware-
Target checkout: /srv/codestra-middleware/repository
Deployment account: middleware-deploy
```

The middleware shares this host with Odoo and related Codestra services. Every discovery and deployment command must be scoped to the exact middleware Compose project and service names. Never restart the entire Docker host or an entire shared Compose project merely to deploy the middleware.

## Mandatory safety boundary

The repository is currently public. Change it to **private** before importing live source or operational configuration.

GitHub is the source of truth for application code, workers, migrations, tests, Dockerfiles, non-secret Compose templates, and documentation. Keep these outside Git:

- `.env` and live Compose override files;
- database, Redis, outbox, inbox, queue, dead-letter, or webhook payload data;
- Keycloak, Odoo, n8n, VICIdial, Kong, Caddy, SMTP, SMS, provider, or database credentials;
- TLS certificates and private keys;
- customer or agent personally identifiable information;
- production logs, packet captures, backups, and secret-bearing evidence.

A Git rollback cannot reverse a database migration, an externally delivered event, or a consumed queue message. Data-changing releases require matching recovery points and tested rollback procedures.

## Intended GitOps flow

```text
feature branch
  -> pull request
  -> locked dependency install
  -> lint, type, unit, integration, migration, security, and container tests
  -> merge protected main
  -> build image once for exact commit SHA
  -> publish immutable image digest
  -> deploy digest to staging with all external writes disabled
  -> run smoke, replay, idempotency, cross-system, and rollback tests
  -> explicit production approval
  -> deploy the identical accepted image digest to production
```

Do not deploy a mutable branch, `latest` tag, locally edited checkout, or image rebuilt after staging acceptance.

## 1. Change repository visibility

In GitHub:

```text
Middleware- -> Settings -> General -> Danger Zone
-> Change repository visibility -> Make private
```

Do this before importing the live middleware source.

## 2. Create a separate read-only deploy key

GitHub deploy keys are repository-specific. Do not reuse the Odoo repository deploy key.

Run on Application Server A:

```bash
ssh root@65.109.65.169
set -Eeuo pipefail

id middleware-deploy >/dev/null 2>&1 || \
  useradd --system --create-home --shell /bin/bash middleware-deploy

install -d \
  -m 0700 \
  -o middleware-deploy \
  -g middleware-deploy \
  /home/middleware-deploy/.ssh

if [[ ! -f /home/middleware-deploy/.ssh/github_middleware_readonly ]]; then
  sudo -u middleware-deploy -H ssh-keygen \
    -t ed25519 \
    -C "middleware-deploy@$(hostname)" \
    -f /home/middleware-deploy/.ssh/github_middleware_readonly \
    -N ''
fi

printf '\n===== ADD THIS PUBLIC KEY TO THE MIDDLEWARE REPOSITORY =====\n'
cat /home/middleware-deploy/.ssh/github_middleware_readonly.pub
```

In GitHub:

```text
Middleware- -> Settings -> Deploy keys -> Add deploy key
Title: Codestra Middleware Application Server A
Allow write access: leave unchecked
```

Create a dedicated SSH alias:

```bash
cat >/home/middleware-deploy/.ssh/config <<'EOF'
Host github-middleware
  HostName github.com
  User git
  IdentityFile /home/middleware-deploy/.ssh/github_middleware_readonly
  IdentitiesOnly yes
EOF

chown middleware-deploy:middleware-deploy \
  /home/middleware-deploy/.ssh/config
chmod 0600 /home/middleware-deploy/.ssh/config
```

Capture GitHub's host key into a temporary file and compare its fingerprint with GitHub's official published SSH fingerprints before installing it:

```bash
ssh-keyscan -t ed25519 github.com 2>/dev/null \
  > /tmp/github-middleware-ed25519-known-host
ssh-keygen -lf /tmp/github-middleware-ed25519-known-host
```

After the fingerprint is verified:

```bash
install \
  -m 0600 \
  -o middleware-deploy \
  -g middleware-deploy \
  /tmp/github-middleware-ed25519-known-host \
  /home/middleware-deploy/.ssh/known_hosts
rm -f /tmp/github-middleware-ed25519-known-host

sudo -u middleware-deploy -H git ls-remote \
  git@github-middleware:appolon1908-hue/Middleware-.git HEAD
```

Do not add `middleware-deploy` to the `docker` group. Docker access is effectively root access. Later automation should invoke one root-owned, allowlisted deployment command through tightly restricted `sudo`.

## 3. Clone the bootstrap checkout

```bash
install -d \
  -m 0750 \
  -o middleware-deploy \
  -g middleware-deploy \
  /srv/codestra-middleware

sudo -u middleware-deploy -H git clone \
  git@github-middleware:appolon1908-hue/Middleware-.git \
  /srv/codestra-middleware/repository

sudo -u middleware-deploy -H \
  git -C /srv/codestra-middleware/repository status --short
sudo -u middleware-deploy -H \
  git -C /srv/codestra-middleware/repository rev-parse HEAD
```

The checkout is a deployment input, not a place for manual production editing.

## 4. Discover the live middleware runtime without changing it

Run the included read-only inventory:

```bash
sudo bash \
  /srv/codestra-middleware/repository/scripts/discover_middleware_runtime.sh \
  | tee /root/middleware-git-discovery.txt
```

When automatic selection finds the wrong container, specify the exact running middleware container:

```bash
sudo MIDDLEWARE_CONTAINER=<exact_container_name_or_id> bash \
  /srv/codestra-middleware/repository/scripts/discover_middleware_runtime.sh \
  | tee /root/middleware-git-discovery.txt
```

The report records only non-secret runtime facts:

- middleware container name, image, image ID, and repository digest;
- Compose project, service, working directory, and configuration files;
- source/config/data mounts and whether each is writable;
- published ports and container networks;
- health, restart count, container user, privileged mode, and read-only root filesystem state;
- a strict allowlist of non-secret safety flags;
- related Odoo, n8n, PostgreSQL, Redis, Keycloak, Kong, Caddy, callback, and worker containers.

It deliberately does not print the complete container environment or read database passwords.

Record at minimum:

```text
MIDDLEWARE_CONTAINER_NAME=
MIDDLEWARE_IMAGE=
MIDDLEWARE_IMAGE_DIGEST=
COMPOSE_PROJECT=
COMPOSE_SERVICE=
COMPOSE_WORKING_DIR=
COMPOSE_CONFIG_FILES=
SOURCE_OR_BUILD_CONTEXT=
DATABASE_SERVICE=
REDIS_SERVICE=
WORKER_SERVICES=
CALLBACK_SERVICE=
HEALTH_ENDPOINT=
CURRENT_SAFE_FLAG_NAMES=
```

Do not alter mounts, images, Compose files, or service names until these values are confirmed.

## 5. Import only the authoritative source

Identify the original source directory or image build context from the Compose metadata and bind mounts. Prefer the host source tree used to build the running image. Do not treat a running container filesystem as authoritative unless no source tree exists and the export has been independently reviewed.

Use a temporary working tree, not the production checkout:

```bash
export EXISTING_SOURCE=/actual/verified/middleware/source
export WORKTREE=/tmp/codestra-middleware-import

rm -rf "$WORKTREE"
git clone \
  git@github-middleware:appolon1908-hue/Middleware-.git \
  "$WORKTREE"

rsync -a \
  --exclude='.git/' \
  --exclude='.env' \
  --exclude='.env.*' \
  --exclude='secrets/' \
  --exclude='credentials/' \
  --exclude='__pycache__/' \
  --exclude='.venv/' \
  --exclude='venv/' \
  --exclude='node_modules/' \
  --exclude='logs/' \
  --exclude='runtime/' \
  --exclude='data/' \
  --exclude='backups/' \
  --exclude='*.log' \
  --exclude='*.dump' \
  --exclude='*.backup' \
  --exclude='*.sqlite*' \
  --exclude='*.rdb' \
  --exclude='*.aof' \
  --exclude='*.pem' \
  --exclude='*.key' \
  "$EXISTING_SOURCE"/ "$WORKTREE"/

cd "$WORKTREE"
git switch -c import/live-middleware-baseline
bash scripts/run_ci.sh
git status --short
```

Review every imported file. Search for credentials, private URLs containing embedded passwords, webhook samples, production payloads, customer data, TLS material, and generated artifacts. Add a dedicated secret scanner and the actual locked dependency/test pipeline in the same import pull request.

The source import pull request must identify:

- application framework and Python/runtime version;
- API and worker entry points;
- package manager and lock files;
- database migration framework and current migration head;
- PostgreSQL and Redis responsibilities;
- outbox, inbox, idempotency, retry, replay, and dead-letter behavior;
- Keycloak/OIDC, Odoo, n8n, VICIdial, Kong/Caddy, SMS, email, and webhook integrations;
- health/readiness endpoints;
- external-write and kill-switch controls;
- tests that currently pass and tests still missing.

## 6. Replace the bootstrap CI hook with the real test pipeline

The bootstrap workflow runs `scripts/run_ci.sh`. The source import must add an executable:

```text
scripts/project_ci.sh
```

That script must use the repository's locked dependency mechanism and run, as applicable:

```text
format/lint check
static type checking
unit tests
PostgreSQL integration tests
Redis integration tests
migration upgrade and rollback tests
outbox/inbox and lease tests
idempotency and deduplication collision tests
webhook signature, replay, and timestamp tests
cross-tenant and authorization tests
Odoo/n8n/VICIdial adapter contract tests
container build and health tests
secret, dependency, and container vulnerability scans
```

Do not make CI pass by silently skipping unavailable services. Report unsupported or missing test categories explicitly.

## 7. Keep secrets outside Git

Use root-readable files or a dedicated secret manager on the server. A typical separation is:

```text
/etc/codestra-middleware/runtime.env
/etc/codestra-middleware/credentials/
/etc/codestra-middleware/tls/
```

Recommended ownership:

```text
root:root
```

Recommended permissions:

```text
runtime.env: 0600
credential files: 0600
credential directories: 0700
```

The repository may contain `.env.example` files with variable names and safe placeholder values, never live values.

## 8. Stage with fail-closed capabilities

`config/preproduction-safety.env.example` is a control baseline, not proof that the current application recognizes every variable. Map it to the actual code after import and add startup validation that fails closed when required controls are missing or malformed.

At staging startup, all externally effective behavior must remain disabled, including:

```text
SEND_EVENTS=false
ENABLE_EXTERNAL_DELIVERY=false
LIVE_WRITE=false
LIVE_WRITES=false
ODOO_WRITE=false
CALLBACK_DISPATCH=false
N8N_DELIVERY_ENABLED=false
VICIDIAL_WRITES_ENABLED=false
EXTERNAL_DIAL_ENABLED=false
PRODUCTION_CALLBACKS_ENABLED=false
N8N_PRODUCTION_WORKFLOWS_ENABLED=false
PRODUCTION_DIALING=DISABLED
```

Validate the effective runtime values from the container after deployment. Do not accept the source `.env.example` as runtime evidence.

## 9. Build once and deploy an immutable image

The preferred production model is:

```text
reviewed commit SHA
  -> GitHub-hosted CI build
  -> tests and scans
  -> GHCR image
  -> image digest
  -> staging deployment by digest
  -> accepted digest
  -> production deployment of the same digest
```

The production Compose template should require a digest-bearing image value, for example:

```yaml
services:
  middleware:
    image: ${MIDDLEWARE_IMAGE:?set immutable image digest}
    env_file:
      - /etc/codestra-middleware/runtime.env
```

The deployed value should resemble:

```text
ghcr.io/appolon1908-hue/codestra-middleware@sha256:<digest>
```

Do not use `latest`, an unpinned branch-derived tag, or an image rebuilt separately on the server after staging acceptance.

## 10. Scope deployment on the shared server

After discovery confirms the Compose directory and service names, use service-scoped commands. A representative pattern is:

```bash
cd <COMPOSE_WORKING_DIR>

docker compose \
  -f <CONFIRMED_COMPOSE_FILE> \
  pull <MIDDLEWARE_SERVICE> <WORKER_SERVICES>

docker compose \
  -f <CONFIRMED_COMPOSE_FILE> \
  up -d --no-deps <MIDDLEWARE_SERVICE> <WORKER_SERVICES>
```

Do not run unscoped commands such as:

```bash
docker compose down
docker system prune -a
docker restart $(docker ps -q)
```

Those commands can interrupt Odoo, n8n, PostgreSQL, Redis, Keycloak, Caddy, Kong, and other applications on the same host.

## 11. Minimum staging evidence

Before production approval, capture evidence for the exact commit SHA and image digest:

- clean repository and exact SHA;
- immutable image digest and build provenance;
- database backup and restore test;
- migration upgrade and rollback test;
- Redis/outbox/inbox recovery behavior;
- API health and readiness;
- authentication and authorization;
- cross-tenant isolation where applicable;
- idempotency and duplicate request handling;
- webhook signature, replay, timestamp, and deduplication controls;
- Odoo and n8n duplicate-delivery behavior;
- VICIdial write denial while disabled;
- external delivery and dialing denial while disabled;
- worker retry, lease expiry, dead-letter, and replay behavior;
- Kong/Caddy routing, TLS, mTLS, rate limit, and allowlist behavior;
- rollback to the prior image and matching data recovery point.

## 12. GitHub deployment automation

Use a GitHub-hosted runner that connects to a restricted server account and invokes one root-owned deployment command. Do not install a general-purpose self-hosted Actions runner on this shared production server.

Separate staging and production GitHub environments. Typical environment secrets are:

```text
MIDDLEWARE_DEPLOY_HOST
MIDDLEWARE_DEPLOY_PORT
MIDDLEWARE_DEPLOY_USER
MIDDLEWARE_DEPLOY_SSH_KEY
MIDDLEWARE_DEPLOY_HOST_KEY
MIDDLEWARE_GHCR_READ_TOKEN
```

Keep application and integration credentials on the server or in a dedicated secret manager, not in deployment workflow YAML. Protect production with required reviewers and deploy only from the protected release branch or reviewed `main` commit according to the repository's release policy.
