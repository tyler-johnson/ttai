# Kubernetes & OpenTofu Deployment

## Overview

The TastyTrade AI system is deployed on DigitalOcean Kubernetes (DOKS) using OpenTofu for infrastructure as code. This document covers the cluster configuration, module structure, and deployment patterns.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    DigitalOcean Cloud                                │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │              Kubernetes Cluster (DOKS)                       │    │
│  │                                                              │    │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │    │
│  │  │  Namespace:  │  │  Namespace:  │  │  Namespace:  │       │    │
│  │  │    ttai      │  │   temporal   │  │  monitoring  │       │    │
│  │  └──────────────┘  └──────────────┘  └──────────────┘       │    │
│  │                                                              │    │
│  │  ┌──────────────────────────────────────────────────────┐   │    │
│  │  │                    Helm Charts                        │   │    │
│  │  │  ┌────────────┐ ┌────────────┐ ┌────────────┐        │   │    │
│  │  │  │ Temporal   │ │ PostgreSQL │ │   Redis    │        │   │    │
│  │  │  │ (official) │ │ (bitnami)  │ │ (bitnami)  │        │   │    │
│  │  │  └────────────┘ └────────────┘ └────────────┘        │   │    │
│  │  └──────────────────────────────────────────────────────┘   │    │
│  │                                                              │    │
│  │  ┌──────────────────────────────────────────────────────┐   │    │
│  │  │              Custom Deployments                       │   │    │
│  │  │  ┌────────────┐ ┌────────────┐ ┌────────────┐        │   │    │
│  │  │  │MCP Server  │ │  Python    │ │ Streaming  │        │   │    │
│  │  │  │(TypeScript)│ │  Worker    │ │  Worker    │        │   │    │
│  │  │  └────────────┘ └────────────┘ └────────────┘        │   │    │
│  │  └──────────────────────────────────────────────────────┘   │    │
│  │                                                              │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌─────────────────┐                                                │
│  │ DigitalOcean    │                                                │
│  │    Spaces       │  (Object storage for backups)                  │
│  └─────────────────┘                                                │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

## OpenTofu Module Structure

```
infra/
├── main.tf                    # Root module
├── variables.tf               # Input variables
├── outputs.tf                 # Output values
├── providers.tf               # Provider configuration
├── versions.tf                # Version constraints
│
├── modules/
│   ├── digitalocean/          # DO-specific resources
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   ├── outputs.tf
│   │   ├── kubernetes.tf      # DOKS cluster
│   │   └── spaces.tf          # Object storage
│   │
│   ├── kubernetes/            # K8s resources
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   ├── outputs.tf
│   │   ├── namespaces.tf
│   │   ├── rbac.tf
│   │   └── secrets.tf
│   │
│   └── apps/                  # Application deployments
│       ├── main.tf
│       ├── variables.tf
│       ├── mcp-server.tf
│       ├── python-worker.tf
│       └── streaming-worker.tf
│
├── helm/                      # Helm value overrides
│   ├── temporal.yaml
│   ├── postgresql.yaml
│   └── redis.yaml
│
└── environments/
    ├── staging/
    │   ├── main.tf
    │   ├── terraform.tfvars
    │   └── backend.tf
    │
    └── production/
        ├── main.tf
        ├── terraform.tfvars
        └── backend.tf
```

## Provider Configuration

```hcl
# providers.tf
terraform {
  required_providers {
    digitalocean = {
      source  = "digitalocean/digitalocean"
      version = "~> 2.34"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.25"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.12"
    }
  }
}

provider "digitalocean" {
  token = var.do_token
}

provider "kubernetes" {
  host                   = module.digitalocean.kubernetes_host
  token                  = module.digitalocean.kubernetes_token
  cluster_ca_certificate = base64decode(module.digitalocean.kubernetes_ca_certificate)
}

provider "helm" {
  kubernetes {
    host                   = module.digitalocean.kubernetes_host
    token                  = module.digitalocean.kubernetes_token
    cluster_ca_certificate = base64decode(module.digitalocean.kubernetes_ca_certificate)
  }
}
```

## DigitalOcean Resources

### Kubernetes Cluster

```hcl
# modules/digitalocean/kubernetes.tf
resource "digitalocean_kubernetes_cluster" "ttai" {
  name    = "${var.project_name}-${var.environment}"
  region  = var.region
  version = var.kubernetes_version

  # Node pool for general workloads
  node_pool {
    name       = "default"
    size       = var.node_size
    node_count = var.node_count
    auto_scale = true
    min_nodes  = var.min_nodes
    max_nodes  = var.max_nodes

    labels = {
      workload = "general"
    }
  }

  maintenance_policy {
    start_time = "04:00"
    day        = "sunday"
  }

  tags = [var.project_name, var.environment]
}

# Dedicated node pool for workers (optional)
resource "digitalocean_kubernetes_node_pool" "workers" {
  count = var.enable_worker_pool ? 1 : 0

  cluster_id = digitalocean_kubernetes_cluster.ttai.id
  name       = "workers"
  size       = var.worker_node_size
  node_count = var.worker_node_count
  auto_scale = true
  min_nodes  = var.worker_min_nodes
  max_nodes  = var.worker_max_nodes

  labels = {
    workload = "worker"
  }

  taint {
    key    = "workload"
    value  = "worker"
    effect = "NoSchedule"
  }
}

output "kubernetes_host" {
  value = digitalocean_kubernetes_cluster.ttai.endpoint
}

output "kubernetes_token" {
  value     = digitalocean_kubernetes_cluster.ttai.kube_config[0].token
  sensitive = true
}

output "kubernetes_ca_certificate" {
  value     = digitalocean_kubernetes_cluster.ttai.kube_config[0].cluster_ca_certificate
  sensitive = true
}
```

### DigitalOcean Spaces (Object Storage)

```hcl
# modules/digitalocean/spaces.tf
resource "digitalocean_spaces_bucket" "backups" {
  name   = "${var.project_name}-${var.environment}-backups"
  region = var.spaces_region

  lifecycle_rule {
    id      = "expire-old-backups"
    enabled = true

    expiration {
      days = 30
    }
  }
}

resource "digitalocean_spaces_bucket" "artifacts" {
  name   = "${var.project_name}-${var.environment}-artifacts"
  region = var.spaces_region
}
```

## Kubernetes Resources

### Namespaces and RBAC

```hcl
# modules/kubernetes/namespaces.tf
resource "kubernetes_namespace" "ttai" {
  metadata {
    name = "ttai"

    labels = {
      "app.kubernetes.io/managed-by" = "terraform"
      environment                     = var.environment
    }
  }
}

resource "kubernetes_namespace" "temporal" {
  metadata {
    name = "temporal"

    labels = {
      "app.kubernetes.io/managed-by" = "terraform"
    }
  }
}

resource "kubernetes_namespace" "monitoring" {
  metadata {
    name = "monitoring"

    labels = {
      "app.kubernetes.io/managed-by" = "terraform"
    }
  }
}
```

```hcl
# modules/kubernetes/rbac.tf
resource "kubernetes_service_account" "ttai_app" {
  metadata {
    name      = "ttai-app"
    namespace = kubernetes_namespace.ttai.metadata[0].name
  }
}

resource "kubernetes_role" "ttai_app" {
  metadata {
    name      = "ttai-app"
    namespace = kubernetes_namespace.ttai.metadata[0].name
  }

  rule {
    api_groups = [""]
    resources  = ["configmaps", "secrets"]
    verbs      = ["get", "list", "watch"]
  }
}

resource "kubernetes_role_binding" "ttai_app" {
  metadata {
    name      = "ttai-app"
    namespace = kubernetes_namespace.ttai.metadata[0].name
  }

  role_ref {
    api_group = "rbac.authorization.k8s.io"
    kind      = "Role"
    name      = kubernetes_role.ttai_app.metadata[0].name
  }

  subject {
    kind      = "ServiceAccount"
    name      = kubernetes_service_account.ttai_app.metadata[0].name
    namespace = kubernetes_namespace.ttai.metadata[0].name
  }
}
```

### Secrets Management

LiteLLM reads API keys from standard environment variables automatically. Add secrets for whichever LLM provider(s) you want to use.

```hcl
# modules/kubernetes/secrets.tf
resource "kubernetes_secret" "ttai_secrets" {
  metadata {
    name      = "ttai-secrets"
    namespace = kubernetes_namespace.ttai.metadata[0].name
  }

  data = {
    # LLM Provider API Keys (LiteLLM reads from standard env vars)
    # Add keys for the provider(s) you want to use:
    "anthropic-api-key" = var.anthropic_api_key  # For anthropic/* models
    # "openai-api-key"  = var.openai_api_key     # For openai/* models (optional)
    # "google-api-key"  = var.google_api_key     # For gemini/* models (optional)

    # TastyTrade credentials
    "tt-client-secret"  = var.tastytrade_client_secret
    "tt-refresh-token"  = var.tastytrade_refresh_token
  }

  type = "Opaque"
}

resource "kubernetes_secret" "discord_webhook" {
  count = var.discord_webhook_url != "" ? 1 : 0

  metadata {
    name      = "discord-webhook"
    namespace = kubernetes_namespace.ttai.metadata[0].name
  }

  data = {
    "webhook-url" = var.discord_webhook_url
  }

  type = "Opaque"
}
```

## Helm Charts

### Temporal

```hcl
# main.tf (root)
resource "helm_release" "temporal" {
  name       = "temporal"
  repository = "https://temporalio.github.io/helm-charts"
  chart      = "temporal"
  version    = var.temporal_chart_version
  namespace  = kubernetes_namespace.temporal.metadata[0].name

  values = [file("${path.module}/helm/temporal.yaml")]

  set {
    name  = "server.replicaCount"
    value = var.environment == "production" ? "3" : "1"
  }

  set {
    name  = "cassandra.enabled"
    value = "false"
  }

  set {
    name  = "postgresql.enabled"
    value = "true"
  }

  depends_on = [helm_release.postgresql]
}
```

```yaml
# helm/temporal.yaml
server:
  config:
    persistence:
      default:
        driver: sql
        sql:
          driver: postgres
          host: postgresql.temporal.svc.cluster.local
          port: 5432
          database: temporal
          user: temporal
          existingSecret: temporal-postgres-secret

web:
  enabled: true
  service:
    type: ClusterIP

prometheus:
  enabled: true

grafana:
  enabled: false  # We'll use our own monitoring stack
```

### PostgreSQL

```hcl
resource "helm_release" "postgresql" {
  name       = "postgresql"
  repository = "https://charts.bitnami.com/bitnami"
  chart      = "postgresql"
  version    = var.postgresql_chart_version
  namespace  = kubernetes_namespace.temporal.metadata[0].name

  values = [file("${path.module}/helm/postgresql.yaml")]

  set_sensitive {
    name  = "auth.postgresPassword"
    value = var.postgres_password
  }
}
```

```yaml
# helm/postgresql.yaml
primary:
  persistence:
    enabled: true
    size: 20Gi

  resources:
    requests:
      memory: 256Mi
      cpu: 250m
    limits:
      memory: 1Gi
      cpu: 1000m

auth:
  database: temporal

metrics:
  enabled: true

# For TTAI app database
initdbScripts:
  init-ttai-db.sql: |
    CREATE DATABASE ttai;
    CREATE USER ttai WITH PASSWORD '${TTAI_DB_PASSWORD}';
    GRANT ALL PRIVILEGES ON DATABASE ttai TO ttai;
```

### Redis

```hcl
resource "helm_release" "redis" {
  name       = "redis"
  repository = "https://charts.bitnami.com/bitnami"
  chart      = "redis"
  version    = var.redis_chart_version
  namespace  = kubernetes_namespace.ttai.metadata[0].name

  values = [file("${path.module}/helm/redis.yaml")]

  set_sensitive {
    name  = "auth.password"
    value = var.redis_password
  }
}
```

```yaml
# helm/redis.yaml
architecture: standalone

master:
  persistence:
    enabled: true
    size: 5Gi

  resources:
    requests:
      memory: 128Mi
      cpu: 100m
    limits:
      memory: 512Mi
      cpu: 500m

auth:
  enabled: true

metrics:
  enabled: true
```

## Application Deployments

### MCP Server

```hcl
# modules/apps/mcp-server.tf
resource "kubernetes_deployment" "mcp_server" {
  metadata {
    name      = "mcp-server"
    namespace = var.namespace

    labels = {
      app = "mcp-server"
    }
  }

  spec {
    replicas = var.mcp_server_replicas

    selector {
      match_labels = {
        app = "mcp-server"
      }
    }

    template {
      metadata {
        labels = {
          app = "mcp-server"
        }
      }

      spec {
        service_account_name = var.service_account_name

        container {
          name  = "mcp-server"
          image = "${var.container_registry}/mcp-server:${var.mcp_server_version}"

          port {
            container_port = 3000
            name           = "http"
          }

          env {
            name  = "NODE_ENV"
            value = var.environment
          }

          env {
            name  = "REDIS_URL"
            value = "redis://:${var.redis_password}@redis-master.${var.namespace}.svc.cluster.local:6379"
          }

          env {
            name  = "TEMPORAL_ADDRESS"
            value = "temporal-frontend.temporal.svc.cluster.local:7233"
          }

          env {
            name  = "DATABASE_URL"
            value = "postgresql://ttai:${var.db_password}@postgresql.temporal.svc.cluster.local:5432/ttai"
          }

          # LLM Provider API Key (LiteLLM reads from standard env vars)
          env {
            name = "ANTHROPIC_API_KEY"
            value_from {
              secret_key_ref {
                name = "ttai-secrets"
                key  = "anthropic-api-key"
              }
            }
          }

          # Add additional provider keys if using other LLM providers:
          # env {
          #   name = "OPENAI_API_KEY"
          #   value_from {
          #     secret_key_ref {
          #       name = "ttai-secrets"
          #       key  = "openai-api-key"
          #     }
          #   }
          # }

          resources {
            requests = {
              memory = "256Mi"
              cpu    = "100m"
            }
            limits = {
              memory = "512Mi"
              cpu    = "500m"
            }
          }

          liveness_probe {
            http_get {
              path = "/health"
              port = 3000
            }
            initial_delay_seconds = 10
            period_seconds        = 30
          }

          readiness_probe {
            http_get {
              path = "/ready"
              port = 3000
            }
            initial_delay_seconds = 5
            period_seconds        = 10
          }
        }
      }
    }
  }
}

resource "kubernetes_service" "mcp_server" {
  metadata {
    name      = "mcp-server"
    namespace = var.namespace
  }

  spec {
    selector = {
      app = "mcp-server"
    }

    port {
      port        = 80
      target_port = 3000
    }

    type = "ClusterIP"
  }
}
```

### Python Worker

```hcl
# modules/apps/python-worker.tf
resource "kubernetes_deployment" "python_worker" {
  metadata {
    name      = "python-worker"
    namespace = var.namespace

    labels = {
      app = "python-worker"
    }
  }

  spec {
    replicas = var.python_worker_replicas

    selector {
      match_labels = {
        app = "python-worker"
      }
    }

    template {
      metadata {
        labels = {
          app = "python-worker"
        }
      }

      spec {
        service_account_name = var.service_account_name

        # Optional: schedule on worker nodes
        dynamic "toleration" {
          for_each = var.use_worker_nodes ? [1] : []
          content {
            key      = "workload"
            operator = "Equal"
            value    = "worker"
            effect   = "NoSchedule"
          }
        }

        dynamic "node_selector" {
          for_each = var.use_worker_nodes ? [1] : []
          content {
            workload = "worker"
          }
        }

        container {
          name  = "worker"
          image = "${var.container_registry}/python-worker:${var.python_worker_version}"

          env {
            name  = "TEMPORAL_ADDRESS"
            value = "temporal-frontend.temporal.svc.cluster.local:7233"
          }

          env {
            name  = "TEMPORAL_NAMESPACE"
            value = "default"
          }

          env {
            name  = "TEMPORAL_TASK_QUEUE"
            value = "ttai-queue"
          }

          env {
            name  = "REDIS_URL"
            value = "redis://:${var.redis_password}@redis-master.${var.namespace}.svc.cluster.local:6379"
          }

          env {
            name  = "DATABASE_URL"
            value = "postgresql://ttai:${var.db_password}@postgresql.temporal.svc.cluster.local:5432/ttai"
          }

          # LLM Provider API Key (LiteLLM reads from standard env vars)
          env {
            name = "ANTHROPIC_API_KEY"
            value_from {
              secret_key_ref {
                name = "ttai-secrets"
                key  = "anthropic-api-key"
              }
            }
          }

          # Add additional provider keys if using other LLM providers:
          # env {
          #   name = "OPENAI_API_KEY"
          #   value_from {
          #     secret_key_ref {
          #       name = "ttai-secrets"
          #       key  = "openai-api-key"
          #     }
          #   }
          # }

          env {
            name = "TT_CLIENT_SECRET"
            value_from {
              secret_key_ref {
                name = "ttai-secrets"
                key  = "tt-client-secret"
              }
            }
          }

          env {
            name = "TT_REFRESH_TOKEN"
            value_from {
              secret_key_ref {
                name = "ttai-secrets"
                key  = "tt-refresh-token"
              }
            }
          }

          resources {
            requests = {
              memory = "512Mi"
              cpu    = "250m"
            }
            limits = {
              memory = "2Gi"
              cpu    = "1000m"
            }
          }
        }
      }
    }
  }
}
```

### Streaming Worker

```hcl
# modules/apps/streaming-worker.tf
resource "kubernetes_deployment" "streaming_worker" {
  metadata {
    name      = "streaming-worker"
    namespace = var.namespace

    labels = {
      app = "streaming-worker"
    }
  }

  spec {
    # Streaming worker should be singleton
    replicas = 1

    strategy {
      type = "Recreate"  # Ensure only one instance
    }

    selector {
      match_labels = {
        app = "streaming-worker"
      }
    }

    template {
      metadata {
        labels = {
          app = "streaming-worker"
        }
      }

      spec {
        service_account_name = var.service_account_name

        container {
          name  = "streaming"
          image = "${var.container_registry}/streaming-worker:${var.streaming_worker_version}"

          env {
            name  = "REDIS_URL"
            value = "redis://:${var.redis_password}@redis-master.${var.namespace}.svc.cluster.local:6379"
          }

          env {
            name = "TT_CLIENT_SECRET"
            value_from {
              secret_key_ref {
                name = "ttai-secrets"
                key  = "tt-client-secret"
              }
            }
          }

          env {
            name = "TT_REFRESH_TOKEN"
            value_from {
              secret_key_ref {
                name = "ttai-secrets"
                key  = "tt-refresh-token"
              }
            }
          }

          resources {
            requests = {
              memory = "256Mi"
              cpu    = "100m"
            }
            limits = {
              memory = "512Mi"
              cpu    = "500m"
            }
          }
        }
      }
    }
  }
}
```

## Ingress and TLS

### Ingress Controller

```hcl
resource "helm_release" "nginx_ingress" {
  name       = "nginx-ingress"
  repository = "https://kubernetes.github.io/ingress-nginx"
  chart      = "ingress-nginx"
  version    = var.nginx_ingress_version
  namespace  = "ingress-nginx"
  create_namespace = true

  set {
    name  = "controller.service.type"
    value = "LoadBalancer"
  }

  set {
    name  = "controller.service.annotations.service\\.beta\\.kubernetes\\.io/do-loadbalancer-name"
    value = "${var.project_name}-${var.environment}-lb"
  }
}
```

### TLS with Let's Encrypt

```hcl
resource "helm_release" "cert_manager" {
  name       = "cert-manager"
  repository = "https://charts.jetstack.io"
  chart      = "cert-manager"
  version    = var.cert_manager_version
  namespace  = "cert-manager"
  create_namespace = true

  set {
    name  = "installCRDs"
    value = "true"
  }
}

resource "kubernetes_manifest" "letsencrypt_issuer" {
  depends_on = [helm_release.cert_manager]

  manifest = {
    apiVersion = "cert-manager.io/v1"
    kind       = "ClusterIssuer"
    metadata = {
      name = "letsencrypt-prod"
    }
    spec = {
      acme = {
        server = "https://acme-v02.api.letsencrypt.org/directory"
        email  = var.letsencrypt_email
        privateKeySecretRef = {
          name = "letsencrypt-prod"
        }
        solvers = [{
          http01 = {
            ingress = {
              class = "nginx"
            }
          }
        }]
      }
    }
  }
}
```

### Ingress for SSE Access

```hcl
resource "kubernetes_ingress_v1" "mcp_server" {
  metadata {
    name      = "mcp-server"
    namespace = var.namespace

    annotations = {
      "kubernetes.io/ingress.class"                    = "nginx"
      "cert-manager.io/cluster-issuer"                 = "letsencrypt-prod"
      "nginx.ingress.kubernetes.io/proxy-read-timeout" = "3600"
      "nginx.ingress.kubernetes.io/proxy-send-timeout" = "3600"
    }
  }

  spec {
    tls {
      hosts       = [var.mcp_server_domain]
      secret_name = "mcp-server-tls"
    }

    rule {
      host = var.mcp_server_domain

      http {
        path {
          path      = "/"
          path_type = "Prefix"

          backend {
            service {
              name = "mcp-server"
              port {
                number = 80
              }
            }
          }
        }
      }
    }
  }
}
```

## Environment Configuration

### Staging

```hcl
# environments/staging/main.tf
module "ttai" {
  source = "../../"

  environment  = "staging"
  project_name = "ttai"
  region       = "nyc3"

  # Cluster sizing
  node_size  = "s-2vcpu-4gb"
  node_count = 2
  min_nodes  = 1
  max_nodes  = 3

  # Application replicas
  mcp_server_replicas    = 1
  python_worker_replicas = 1

  # Versions
  mcp_server_version     = var.mcp_server_version
  python_worker_version  = var.python_worker_version

  # Secrets
  do_token                   = var.do_token
  anthropic_api_key          = var.anthropic_api_key
  tastytrade_client_secret   = var.tastytrade_client_secret
  tastytrade_refresh_token   = var.tastytrade_refresh_token
}
```

```hcl
# environments/staging/terraform.tfvars
environment = "staging"
region      = "nyc3"

kubernetes_version = "1.29"
node_size          = "s-2vcpu-4gb"
node_count         = 2

mcp_server_domain = "mcp-staging.ttai.example.com"
```

### Production

```hcl
# environments/production/main.tf
module "ttai" {
  source = "../../"

  environment  = "production"
  project_name = "ttai"
  region       = "nyc3"

  # Larger cluster for production
  node_size  = "s-4vcpu-8gb"
  node_count = 3
  min_nodes  = 2
  max_nodes  = 5

  # Enable dedicated worker pool
  enable_worker_pool  = true
  worker_node_size    = "s-4vcpu-8gb"
  worker_node_count   = 2
  worker_min_nodes    = 1
  worker_max_nodes    = 4

  # More replicas for production
  mcp_server_replicas    = 2
  python_worker_replicas = 3

  # Versions
  mcp_server_version     = var.mcp_server_version
  python_worker_version  = var.python_worker_version

  # Secrets
  do_token                   = var.do_token
  anthropic_api_key          = var.anthropic_api_key
  tastytrade_client_secret   = var.tastytrade_client_secret
  tastytrade_refresh_token   = var.tastytrade_refresh_token
}
```

```hcl
# environments/production/terraform.tfvars
environment = "production"
region      = "nyc3"

kubernetes_version = "1.29"
node_size          = "s-4vcpu-8gb"
node_count         = 3

mcp_server_domain = "mcp.ttai.example.com"
```

## Deployment Commands

```bash
# Initialize (staging)
cd infra/environments/staging
tofu init

# Plan changes
tofu plan -var-file=terraform.tfvars

# Apply changes
tofu apply -var-file=terraform.tfvars

# Destroy (be careful!)
tofu destroy -var-file=terraform.tfvars
```

## CI/CD Integration

```yaml
# .github/workflows/deploy.yml
name: Deploy

on:
  push:
    branches: [main]
  workflow_dispatch:
    inputs:
      environment:
        description: 'Environment to deploy to'
        required: true
        default: 'staging'
        type: choice
        options:
          - staging
          - production

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: ${{ github.event.inputs.environment || 'staging' }}

    steps:
      - uses: actions/checkout@v4

      - name: Setup OpenTofu
        uses: opentofu/setup-opentofu@v1

      - name: Deploy Infrastructure
        run: |
          cd infra/environments/${{ github.event.inputs.environment || 'staging' }}
          tofu init
          tofu apply -auto-approve
        env:
          TF_VAR_do_token: ${{ secrets.DO_TOKEN }}
          TF_VAR_anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY }}
          TF_VAR_tastytrade_client_secret: ${{ secrets.TT_CLIENT_SECRET }}
          TF_VAR_tastytrade_refresh_token: ${{ secrets.TT_REFRESH_TOKEN }}
```
