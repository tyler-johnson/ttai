# Tiltfile

# =============================================================================
# Extensions
# =============================================================================

load('ext://helm_resource', 'helm_resource', 'helm_repo')

# =============================================================================
# Configuration
# =============================================================================

# Load config if exists
config_file = "./tilt_config.json"
settings = read_json(config_file, {
    "default_registry": "",
    "hot_reload": True,
})

# Allow Minikube's built-in registry
allow_k8s_contexts("minikube")

# =============================================================================
# Namespace Setup
# =============================================================================

k8s_yaml("k8s/dev/namespace.yaml")
k8s_resource(
    objects=["ttai:namespace"],
    new_name="namespace",
    labels=["setup"],
)

# =============================================================================
# Secrets (auto-synced from .env.local)
# =============================================================================

local_resource(
    'dev-secrets',
    cmd='kubectl create secret generic dev-secrets --namespace=ttai --from-env-file=.env.local --dry-run=client -o yaml | kubectl apply -f -',
    deps=['.env.local'],
    resource_deps=['namespace'],
    labels=['setup'],
)

# =============================================================================
# Helm Repositories
# =============================================================================

helm_repo('bitnami', 'https://charts.bitnami.com/bitnami')
helm_repo('temporalio', 'https://temporalio.github.io/helm-charts')

# =============================================================================
# Dependencies (Helm Charts)
# =============================================================================

# PostgreSQL
helm_resource(
    name='postgresql',
    chart='bitnami/postgresql',
    namespace='ttai',
    flags=['--values=helm/postgresql-dev.yaml'],
    resource_deps=['bitnami'],
    port_forwards=['5432:5432'],
    labels=['deps'],
)

# Redis
helm_resource(
    name='redis',
    chart='bitnami/redis',
    namespace='ttai',
    flags=['--values=helm/redis-dev.yaml'],
    resource_deps=['bitnami'],
    port_forwards=['6379:6379'],
    labels=['deps'],
)

# Temporal
helm_resource(
    name='temporal',
    chart='temporalio/temporal',
    namespace='ttai',
    flags=['--values=helm/temporal-dev.yaml'],
    resource_deps=['temporalio', 'postgresql'],
    labels=['deps'],
)

# Temporal port forwards (helm_resource can't target specific services in multi-service charts)
local_resource(
    'temporal-web-forward',
    serve_cmd='kubectl port-forward -n ttai svc/temporal-web 8080:8080',
    resource_deps=['temporal'],
    labels=['deps'],
)

local_resource(
    'temporal-frontend-forward',
    serve_cmd='kubectl port-forward -n ttai svc/temporal-frontend 7233:7233',
    resource_deps=['temporal'],
    labels=['deps'],
)

# Temporal namespace setup (creates 'default' namespace for workflows)
k8s_yaml("k8s/dev/temporal-setup.yaml")
k8s_resource(
    "temporal-namespace-setup",
    resource_deps=["temporal"],
    labels=["setup"],
)

# =============================================================================
# MCP Server (TypeScript)
# =============================================================================

# Build MCP server image with live reload
docker_build(
    "mcp-server",
    context="./mcp-server",
    dockerfile="./mcp-server/Dockerfile.dev",
    live_update=[
        # Sync source files
        sync("./mcp-server/src", "/app/src"),
        sync("./mcp-server/package.json", "/app/package.json"),
        # Run npm install if package.json changes
        run(
            "cd /app && npm install",
            trigger=["./mcp-server/package.json"],
        ),
    ],
)

# Deploy MCP server
k8s_yaml("k8s/dev/mcp-server.yaml")
k8s_resource(
    "mcp-server",
    port_forwards=["3000:3000"],
    resource_deps=["dev-secrets", "redis", "temporal-namespace-setup"],
    labels=["app"],
)

# =============================================================================
# Python Worker
# =============================================================================

# Build Python worker image with live reload
docker_build(
    "python-worker",
    context="./workers",
    dockerfile="./workers/Dockerfile.dev",
    live_update=[
        # Sync Python source files
        sync("./workers/activities", "/app/activities"),
        sync("./workers/agents", "/app/agents"),
        sync("./workers/services", "/app/services"),
        sync("./workers/tools", "/app/tools"),
        sync("./workers/models", "/app/models"),
        sync("./workers/workflows", "/app/workflows"),
        sync("./workers/worker.py", "/app/worker.py"),
        # Run pip install if pyproject.toml changes
        run(
            "cd /app && pip install -e .",
            trigger=["./workers/pyproject.toml"],
        ),
    ],
)

# Deploy Python worker
k8s_yaml("k8s/dev/python-worker.yaml")
k8s_resource(
    "python-worker",
    resource_deps=["dev-secrets", "redis", "postgresql", "temporal-namespace-setup"],
    labels=["app"],
)

# =============================================================================
# Streaming Worker
# =============================================================================

docker_build(
    "streaming-worker",
    context="./workers",
    dockerfile="./workers/Dockerfile.streaming.dev",
    live_update=[
        sync("./workers/services", "/app/services"),
        sync("./workers/streaming_worker.py", "/app/streaming_worker.py"),
    ],
)

k8s_yaml("k8s/dev/streaming-worker.yaml")
k8s_resource(
    "streaming-worker",
    resource_deps=["dev-secrets", "redis"],
    labels=["app"],
)

# =============================================================================
# Port Forwards for Dependencies (configured in helm_resource above)
# =============================================================================
# Port forwards are now set directly in the helm_resource calls:
# - postgresql: 5432
# - redis: 6379
# - temporal: 8080 (web UI), 7233 (frontend)

# =============================================================================
# Local Resource: Run Tests
# =============================================================================

local_resource(
    "test-mcp-server",
    cmd="cd mcp-server && npm test",
    deps=["./mcp-server/src"],
    auto_init=False,
    labels=["test"],
)

local_resource(
    "test-workers",
    cmd="cd workers && pytest",
    deps=["./workers"],
    auto_init=False,
    labels=["test"],
)

# =============================================================================
# Local Resource: Database Migrations
# =============================================================================

local_resource(
    "run-migrations",
    cmd="cd workers && alembic upgrade head",
    auto_init=False,
    labels=["setup"],
)

# =============================================================================
# Local Resource: Seed Data
# =============================================================================

local_resource(
    "seed-playbook",
    cmd="cd workers && python scripts/seed_playbook.py",
    auto_init=False,
    labels=["setup"],
)
