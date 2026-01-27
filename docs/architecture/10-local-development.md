# Local Development with Tilt + Minikube

## Overview

Local development uses Tilt with Minikube to provide a Kubernetes-native development experience that mirrors production. This includes hot-reload for both TypeScript and Python components, local instances of all dependencies, and integrated log viewing.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Local Development Environment                     │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                         Tilt UI                               │   │
│  │  http://localhost:10350                                       │   │
│  │  - Resource status                                            │   │
│  │  - Log streaming                                              │   │
│  │  - Trigger rebuilds                                           │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                              │                                       │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                        Minikube                               │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐        │   │
│  │  │ MCP Server   │  │ Python Worker│  │ Temporal     │        │   │
│  │  │ (live reload)│  │ (live reload)│  │              │        │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘        │   │
│  │                                                               │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐        │   │
│  │  │ PostgreSQL   │  │    Redis     │  │ Temporal UI  │        │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘        │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  Port Forwards:                                                      │
│  - 3000: MCP Server (SSE)                                           │
│  - 7233: Temporal Frontend                                          │
│  - 8080: Temporal UI                                                │
│  - 5432: PostgreSQL                                                 │
│  - 6379: Redis                                                      │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

## Prerequisites

### Install Required Tools

```bash
# Minikube
brew install minikube

# Tilt
brew install tilt

# kubectl
brew install kubectl

# Helm
brew install helm

# Docker (for building images)
brew install --cask docker
```

### Start Minikube

```bash
# Start with adequate resources
minikube start \
  --cpus=4 \
  --memory=8192 \
  --disk-size=50g \
  --driver=docker

# Enable required addons
minikube addons enable ingress
minikube addons enable metrics-server

# Verify
minikube status
kubectl get nodes
```

## Project Structure

```
ttai/
├── Tiltfile                    # Main Tilt configuration
├── tilt_config.json            # Tilt settings (gitignored)
│
├── mcp-server/                 # TypeScript MCP server
│   ├── Dockerfile
│   ├── Dockerfile.dev          # Development Dockerfile
│   ├── package.json
│   └── src/
│
├── workers/                    # Python workers
│   ├── Dockerfile
│   ├── Dockerfile.dev          # Development Dockerfile
│   ├── pyproject.toml
│   └── ...
│
├── k8s/                        # Kubernetes manifests
│   ├── dev/                    # Development-specific
│   │   ├── namespace.yaml
│   │   ├── mcp-server.yaml
│   │   ├── python-worker.yaml
│   │   └── streaming-worker.yaml
│   └── base/                   # Shared base manifests
│       └── ...
│
└── helm/                       # Helm value overrides
    ├── temporal-dev.yaml
    ├── postgresql-dev.yaml
    └── redis-dev.yaml
```

## Tiltfile Configuration

```python
# Tiltfile

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

# =============================================================================
# Dependencies (Helm Charts)
# =============================================================================

# PostgreSQL
helm_release(
    name="postgresql",
    chart="oci://registry-1.docker.io/bitnamicharts/postgresql",
    namespace="ttai",
    values=["helm/postgresql-dev.yaml"],
)

# Redis
helm_release(
    name="redis",
    chart="oci://registry-1.docker.io/bitnamicharts/redis",
    namespace="ttai",
    values=["helm/redis-dev.yaml"],
)

# Temporal
helm_release(
    name="temporal",
    chart="temporal",
    repo_url="https://temporalio.github.io/helm-charts",
    namespace="ttai",
    values=["helm/temporal-dev.yaml"],
    resource_deps=["postgresql"],
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
    resource_deps=["redis", "temporal"],
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
    resource_deps=["redis", "postgresql", "temporal"],
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
    resource_deps=["redis"],
    labels=["app"],
)

# =============================================================================
# Port Forwards for Dependencies
# =============================================================================

# Temporal UI
k8s_resource(
    "temporal-web",
    port_forwards=["8080:8080"],
    labels=["deps"],
)

# PostgreSQL (for direct access/debugging)
k8s_resource(
    "postgresql",
    port_forwards=["5432:5432"],
    labels=["deps"],
)

# Redis (for direct access/debugging)
k8s_resource(
    "redis-master",
    port_forwards=["6379:6379"],
    labels=["deps"],
)

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
```

## Development Dockerfiles

### MCP Server (TypeScript)

```dockerfile
# mcp-server/Dockerfile.dev
FROM node:20-slim

WORKDIR /app

# Install dependencies first (for caching)
COPY package*.json ./
RUN npm install

# Copy source
COPY . .

# Use ts-node-dev for hot reloading
RUN npm install -g ts-node-dev

# Expose port
EXPOSE 3000

# Start with hot reload
CMD ["ts-node-dev", "--respawn", "--transpile-only", "src/index.ts"]
```

### Python Worker

```dockerfile
# workers/Dockerfile.dev
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY pyproject.toml ./
RUN pip install -e .

# Install development dependencies
RUN pip install watchdog[watchmedo]

# Copy source
COPY . .

# Use watchmedo for hot reloading
CMD ["watchmedo", "auto-restart", \
     "--directory=.", \
     "--pattern=*.py", \
     "--recursive", \
     "--", \
     "python", "worker.py"]
```

### Streaming Worker

```dockerfile
# workers/Dockerfile.streaming.dev
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install -e .
RUN pip install watchdog[watchmedo]

COPY . .

CMD ["watchmedo", "auto-restart", \
     "--directory=.", \
     "--pattern=*.py", \
     "--recursive", \
     "--", \
     "python", "streaming_worker.py"]
```

## Kubernetes Manifests (Development)

### Namespace

```yaml
# k8s/dev/namespace.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: ttai
  labels:
    environment: development
```

### MCP Server

```yaml
# k8s/dev/mcp-server.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mcp-server
  namespace: ttai
spec:
  replicas: 1
  selector:
    matchLabels:
      app: mcp-server
  template:
    metadata:
      labels:
        app: mcp-server
    spec:
      containers:
        - name: mcp-server
          image: mcp-server
          ports:
            - containerPort: 3000
          env:
            - name: NODE_ENV
              value: development
            - name: REDIS_URL
              value: redis://:devpassword@redis-master:6379
            - name: TEMPORAL_ADDRESS
              value: temporal-frontend:7233
            - name: DATABASE_URL
              value: postgresql://ttai:devpassword@postgresql:5432/ttai
            - name: ANTHROPIC_API_KEY
              valueFrom:
                secretKeyRef:
                  name: dev-secrets
                  key: anthropic-api-key
          resources:
            requests:
              memory: "256Mi"
              cpu: "100m"
            limits:
              memory: "512Mi"
              cpu: "500m"
---
apiVersion: v1
kind: Service
metadata:
  name: mcp-server
  namespace: ttai
spec:
  selector:
    app: mcp-server
  ports:
    - port: 3000
      targetPort: 3000
```

### Python Worker

```yaml
# k8s/dev/python-worker.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: python-worker
  namespace: ttai
spec:
  replicas: 1
  selector:
    matchLabels:
      app: python-worker
  template:
    metadata:
      labels:
        app: python-worker
    spec:
      containers:
        - name: worker
          image: python-worker
          env:
            - name: TEMPORAL_ADDRESS
              value: temporal-frontend:7233
            - name: TEMPORAL_NAMESPACE
              value: default
            - name: TEMPORAL_TASK_QUEUE
              value: ttai-queue
            - name: REDIS_URL
              value: redis://:devpassword@redis-master:6379
            - name: DATABASE_URL
              value: postgresql://ttai:devpassword@postgresql:5432/ttai
            - name: ANTHROPIC_API_KEY
              valueFrom:
                secretKeyRef:
                  name: dev-secrets
                  key: anthropic-api-key
            - name: TT_CLIENT_SECRET
              valueFrom:
                secretKeyRef:
                  name: dev-secrets
                  key: tt-client-secret
            - name: TT_REFRESH_TOKEN
              valueFrom:
                secretKeyRef:
                  name: dev-secrets
                  key: tt-refresh-token
          resources:
            requests:
              memory: "512Mi"
              cpu: "250m"
            limits:
              memory: "2Gi"
              cpu: "1000m"
```

## Helm Value Overrides (Development)

### PostgreSQL

```yaml
# helm/postgresql-dev.yaml
primary:
  persistence:
    enabled: true
    size: 5Gi

auth:
  postgresPassword: devpassword
  database: ttai
  username: ttai
  password: devpassword

resources:
  requests:
    memory: 256Mi
    cpu: 100m
  limits:
    memory: 512Mi
    cpu: 500m
```

### Redis

```yaml
# helm/redis-dev.yaml
architecture: standalone

auth:
  enabled: true
  password: devpassword

master:
  persistence:
    enabled: true
    size: 1Gi

  resources:
    requests:
      memory: 64Mi
      cpu: 50m
    limits:
      memory: 256Mi
      cpu: 250m
```

### Temporal

```yaml
# helm/temporal-dev.yaml
server:
  replicaCount: 1

  config:
    persistence:
      default:
        driver: sql
        sql:
          driver: postgres
          host: postgresql
          port: 5432
          database: temporal
          user: ttai
          password: devpassword

cassandra:
  enabled: false

postgresql:
  enabled: false  # Use our own PostgreSQL

web:
  enabled: true
  replicaCount: 1

prometheus:
  enabled: false

grafana:
  enabled: false
```

## Environment Variables

### Local .env File

LiteLLM automatically reads API keys from standard environment variables. You only need to set the variables for the provider(s) you want to use.

```bash
# .env.local (gitignored)

# LLM Provider API Keys (LiteLLM reads these automatically)
# Set the key(s) for the provider(s) you want to use:

# Anthropic (for anthropic/claude-* models)
ANTHROPIC_API_KEY=sk-ant-...

# OpenAI (for openai/gpt-* models)
# OPENAI_API_KEY=sk-...

# Google (for gemini/* models)
# GOOGLE_API_KEY=...

# AWS Bedrock (for bedrock/* models)
# AWS_ACCESS_KEY_ID=...
# AWS_SECRET_ACCESS_KEY=...
# AWS_REGION_NAME=us-east-1

# Azure OpenAI (for azure/* models)
# AZURE_API_KEY=...
# AZURE_API_BASE=https://your-resource.openai.azure.com/
# AZURE_API_VERSION=2024-02-15-preview

# TastyTrade
TT_CLIENT_SECRET=your-client-secret
TT_REFRESH_TOKEN=your-refresh-token

# Discord (optional)
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

**Note:** The AI agents use LiteLLM for provider-agnostic LLM access. By default, agents use `anthropic/claude-sonnet-4-20250514`, but you can configure them to use any supported provider by passing a different model string (e.g., `openai/gpt-4o`).

### Create Kubernetes Secret

```bash
# Create secret from .env.local
kubectl create secret generic dev-secrets \
  --namespace=ttai \
  --from-env-file=.env.local
```

## Running Tilt

### Start Development Environment

```bash
# Start Tilt
tilt up

# Open Tilt UI in browser
tilt up --web-mode=local

# Or just view the URL
# http://localhost:10350
```

### Tilt UI Features

- **Resource Status**: See all resources and their current state
- **Logs**: Stream logs from all services
- **Rebuild Triggers**: Manually trigger rebuilds
- **Errors**: Highlighted errors and failures

### Common Commands

```bash
# Start Tilt
tilt up

# Start in CI mode (no interactive UI)
tilt ci

# Stop all resources
tilt down

# View logs for a specific resource
tilt logs mcp-server

# Trigger a rebuild
tilt trigger mcp-server
```

## Port Forwarding

Tilt automatically sets up port forwards, but you can also do it manually:

```bash
# MCP Server
kubectl port-forward -n ttai svc/mcp-server 3000:3000

# Temporal UI
kubectl port-forward -n ttai svc/temporal-web 8080:8080

# PostgreSQL
kubectl port-forward -n ttai svc/postgresql 5432:5432

# Redis
kubectl port-forward -n ttai svc/redis-master 6379:6379
```

## Debugging

### View Logs

```bash
# All logs
kubectl logs -n ttai -l app=mcp-server -f

# Python worker logs
kubectl logs -n ttai -l app=python-worker -f

# Temporal logs
kubectl logs -n ttai -l app.kubernetes.io/component=frontend -f
```

### Shell Access

```bash
# MCP Server
kubectl exec -it -n ttai deployment/mcp-server -- sh

# Python Worker
kubectl exec -it -n ttai deployment/python-worker -- bash

# PostgreSQL
kubectl exec -it -n ttai postgresql-0 -- psql -U ttai -d ttai

# Redis
kubectl exec -it -n ttai redis-master-0 -- redis-cli -a devpassword
```

### Temporal CLI

```bash
# Install temporal CLI
brew install temporal

# Connect to local Temporal
temporal --address localhost:7233 workflow list

# View workflow details
temporal --address localhost:7233 workflow show -w <workflow-id>

# Terminate a workflow
temporal --address localhost:7233 workflow terminate -w <workflow-id>
```

## Testing Locally

### Run MCP Server Tests

```bash
cd mcp-server
npm test

# Or via Tilt
tilt trigger test-mcp-server
```

### Run Python Tests

```bash
cd workers
pytest

# With coverage
pytest --cov=.

# Or via Tilt
tilt trigger test-workers
```

### Test MCP Connection

```bash
# Test MCP server directly
curl http://localhost:3000/health

# Test via Claude Code config
# Add to ~/.claude/claude_desktop_config.json:
{
  "mcpServers": {
    "tastytrade-ai-dev": {
      "command": "curl",
      "args": ["http://localhost:3000/sse"]
    }
  }
}
```

## Database Management

### Run Migrations

```bash
# Via Tilt
tilt trigger run-migrations

# Manually
cd workers
DATABASE_URL=postgresql://ttai:devpassword@localhost:5432/ttai alembic upgrade head
```

### Seed Data

```bash
# Via Tilt
tilt trigger seed-playbook

# Manually
cd workers
python scripts/seed_playbook.py
```

### Connect to Database

```bash
# Via kubectl
kubectl exec -it -n ttai postgresql-0 -- psql -U ttai -d ttai

# Via local psql (with port-forward)
psql postgresql://ttai:devpassword@localhost:5432/ttai
```

## Troubleshooting

### Minikube Issues

```bash
# Check status
minikube status

# Restart
minikube stop && minikube start

# Delete and recreate
minikube delete
minikube start --cpus=4 --memory=8192

# Check resources
kubectl top nodes
```

### Tilt Issues

```bash
# Reset Tilt state
tilt down
rm -rf .tilt-dev
tilt up

# Check Tilt logs
tilt logs

# Verbose mode
tilt up --debug
```

### Pod Issues

```bash
# Check pod status
kubectl get pods -n ttai

# Describe failing pod
kubectl describe pod -n ttai <pod-name>

# Check events
kubectl get events -n ttai --sort-by='.lastTimestamp'
```

### Common Issues

1. **Pods stuck in Pending**: Check resources with `kubectl describe pod`
2. **Image pull errors**: Ensure Minikube can access the image registry
3. **Connection refused**: Check service endpoints and port forwards
4. **Out of memory**: Increase Minikube memory or reduce replica counts
