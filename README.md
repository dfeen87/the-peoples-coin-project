# The People's Coin — Backend & System Controller

**License:** MIT  
**Stack:** Python (Flask), PostgreSQL 15, SQLAlchemy, Docker  
**Status:** Working backend · Structure stabilized · Live site currently non-functional

## Disclaimer
> IMPORTANT NOTE: NOT AFFILIATED WITH ANY CRYPTO COINS. This project does not mind coins that are sold.

The live site is currently non-functional.

Any keys, credentials, or configuration values present in this repository are illustrative only and must not be used for operational or production purposes.

## Project Overview

The People's Coin backend serves as the resilient core of the platform, responsible for securely recording, validating, and managing acts of goodwill contributed by users across a global network.

The system is built on PostgreSQL 15 for durable, scalable data storage and exposes a RESTful Flask API for managing:

- User accounts and wallets
- Goodwill actions and balances
- Proposals and governance workflows
- Council membership and oversight structures

Every interaction is validated, persistently stored, and made available for auditing, ensuring transparency, integrity, and long-term reliability as system load increases.

## System Controller

At the center of the backend is the System Controller, an intelligent orchestration layer designed to monitor and adapt backend behavior based on real-world conditions.

The controller continuously observes:

- CPU utilization
- Memory usage
- Disk availability
- Task queue depth (when available)

It analyzes both real-time metrics and historical workload data stored in the database to generate data-driven recommendations. These recommendations may include adjusting background worker counts or scaling deployment replicas when running in a containerized environment.

All recommendations and actions are recorded, enabling traceability and post-hoc analysis.

## Architecture & Components

The backend follows a modular, fault-tolerant design:

### SQLAlchemy ORM

- UUID primary keys
- ENUM-based status modeling
- JSONB fields for flexible contextual data
- Timestamp triggers for reliable audit metadata

### Flask REST API

- Clear separation between application bootstrapping and domain logic
- Modular routes and services for extensibility

### Asynchronous Processing

- Background workers for non-blocking task execution
- Optional Redis integration for queue management

### Auditing & Observability

- Controller decisions are logged to a dedicated database table
- System logs complement persistent audit records

## Kubernetes Integration

When deployed in a Kubernetes environment, the System Controller can integrate directly with the cluster API to manage replica scaling.

Key characteristics:

- Scaling operates within configured minimum and maximum bounds
- Deployment name, namespace, and limits are environment-driven
- Secure, authorized API access is required

If Kubernetes is not present, the controller continues monitoring without attempting automated scaling.

## Monitoring & Logging

System health data is collected using psutil, providing visibility into:

- CPU load
- Memory consumption
- Disk utilization

The controller supplements these metrics by querying recent database activity and, when available, Redis queue backlogs. Each evaluation cycle logs:

- Observed system state
- Scaling recommendations
- Actions taken (or intentionally skipped)

This design supports transparency, accountability, and continuous improvement of scaling heuristics.

## Biological Inspiration

The People's Coin backend is intentionally inspired by biological systems, particularly the human nervous, immune, and endocrine systems.

- Continuous sensing of internal state
- Adaptive responses to environmental stressors
- Maintenance of equilibrium under variable load

In this analogy, the System Controller functions as a central nervous system, interpreting signals and coordinating responses to maintain system health. This biomimetic approach informs both architectural decisions and long-term evolution of the platform.

## Technologies & Tools

- **Flask** — Web framework
- **PostgreSQL 15** — Primary datastore
- **SQLAlchemy** — ORM and schema management
- **Docker / Docker Compose** — Containerization
- **Redis (optional)** — Queue management
- **psutil** — System monitoring
- **APScheduler** — Periodic job scheduling
- **Kubernetes Python Client (optional)** — Deployment orchestration

All optional components degrade gracefully when unavailable.

## What You Can Build With This Backend Today

This backend is intentionally generic and modular. It can be used immediately as:

- A governance and voting backend for communities, DAOs, or cooperatives (proposals, councils, decision tracking).

- A contribution or reputation ledger to record, score, and audit non-financial actions (volunteer work, moderation, civic engagement).

- A backend template for civic or nonprofit platforms requiring transparency, auditability, and long-term data integrity.

- A system orchestration experiment demonstrating intelligent resource monitoring and adaptive scaling via a centralized controller.

- A research platform for studying incentive alignment, governance dynamics, and system resilience under load.

- A foundation for tokenized or non-tokenized reward systems, independent of any specific blockchain or frontend.

The system is designed to run locally, in containers, or in cloud environments, with optional Redis and Kubernetes integration depending on deployment needs.

## Benefits of Cloning This Repository

Cloning this repository gives you a practical, inspectable backend foundation that you can run and adapt quickly:

- Full access to a modular Flask + SQLAlchemy architecture you can reuse for governance, reputation, or civic platforms.
- A ready-to-evolve data model covering accounts, wallets, goodwill actions, proposals, votes, and audit logs.
- Built-in observability and adaptive system-controller logic to experiment with workload-aware backend behavior.
- Container and infrastructure manifests (Docker, Docker Compose, Kubernetes) to test locally and transition to cloud deployments.
- Migration scripts and tests that make iterative development and schema evolution easier to manage.
- Optional integrations (Redis, Kubernetes) that degrade gracefully, allowing development without a full production stack.



## Benefits of Cloning This Repository

Cloning this repository gives you a practical, inspectable backend foundation that you can run and adapt quickly:

- Full access to a modular Flask + SQLAlchemy architecture you can reuse for governance, reputation, or civic platforms.
- A ready-to-evolve data model covering accounts, wallets, goodwill actions, proposals, votes, and audit logs.
- Built-in observability and adaptive system-controller logic to experiment with workload-aware backend behavior.
- Container and infrastructure manifests (Docker, Docker Compose, Kubernetes) to test locally and transition to cloud deployments.
- Migration scripts and tests that make iterative development and schema evolution easier to manage.
- Optional integrations (Redis, Kubernetes) that degrade gracefully, allowing development without a full production stack.

## Supporting the Project

This project is MIT-licensed because I want people to learn from it, build with it, and carry it forward.

At the same time, this code reflects a lot of personal effort and care. If you find it useful, please consider supporting the work in one or more of these ways:

- Star and share the repository so more builders can discover it.
- Keep attribution in place and reference this project in derivative work.
- Open issues, suggest improvements, or contribute pull requests.
- Reach out if you want to collaborate, sponsor maintenance, or fund roadmap work.

## Getting Started

1. Clone the repository
2. Create and activate a Python virtual environment
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Initialize the PostgreSQL database using the provided schema/migrations
5. Start the Flask API server
6. Launch the System Controller process to begin monitoring and orchestration

The API and controller may be run independently during development.

## Development & Production Readiness

The backend is designed with operational resilience in mind:

- Works with or without Redis and Kubernetes
- Scaling actions are bounded to prevent resource thrashing
- All automated decisions are logged and auditable
- Modular structure supports incremental extension

This provides a stable foundation for continued development and future production hardening.

## Global Observability Node

The Global Observability Node is a lightweight, read-only REST API that provides safe, non-intrusive access to internal system state. This observability layer follows the same pattern used across the HLV ecosystem, enabling external monitoring without affecting system behavior.

### Key Features

- **Read-Only Access**: All endpoints are GET-only. POST, PUT, PATCH, and DELETE requests are rejected with 405 Method Not Allowed.
- **Safe Monitoring**: No write operations, no database modifications, no controller actions triggered.
- **Independent Operation**: Runs on port 8080 by default, separate from the main API.
- **Thread-Safe**: Uses read-only database queries and snapshot-based metrics.

### Endpoints

#### 1. GET /health

Returns basic service liveness, uptime, and version information.

**Example Response:**
```json
{
  "status": "ok",
  "service": "Global Observability Node",
  "version": "1.0.0",
  "uptime_seconds": 3600.5,
  "timestamp": "2026-02-14T12:00:00.000000+00:00"
}
```

#### 2. GET /api/system_state

Returns comprehensive system metrics including CPU, memory, disk, database activity, Redis queue depth, Kubernetes status, and last controller evaluation.

**Example Response:**
```json
{
  "system_metrics": {
    "cpu_percent": 15.2,
    "memory": {
      "total_mb": 8192.0,
      "available_mb": 4096.0,
      "used_mb": 4096.0,
      "percent": 50.0
    },
    "disk": {
      "total_gb": 100.0,
      "used_gb": 45.0,
      "free_gb": 55.0,
      "percent": 45.0
    },
    "load_averages": {
      "1min": 0.5,
      "5min": 0.6,
      "15min": 0.7
    }
  },
  "database_activity": {
    "active_connections": 5,
    "transactions_committed": 12345,
    "cache_hit_ratio": 98.5
  },
  "redis_queue_depth": 3,
  "kubernetes_enabled": false,
  "last_controller_evaluation": "2026-02-14T11:55:00.000000+00:00",
  "timestamp": "2026-02-14T12:00:00.000000+00:00"
}
```

#### 3. GET /api/controller_decisions

Returns recent controller decisions, scaling recommendations, and actions taken.

**Query Parameters:**
- `limit`: Number of decisions to return (default: 10, max: 100)

**Example Response:**
```json
{
  "count": 10,
  "limit": 10,
  "decisions": [
    {
      "id": 123,
      "timestamp": "2026-02-14T11:55:00.000000+00:00",
      "recommendations": {
        "scale_up": "High backlog of goodwill actions"
      },
      "actions_taken": ["Scale-up triggered"]
    }
  ],
  "timestamp": "2026-02-14T12:00:00.000000+00:00"
}
```

#### 4. GET /api/governance_state

Returns high-level governance metadata including proposal counts, vote totals, and council membership.

**Example Response:**
```json
{
  "proposal_summary": {
    "total": 42,
    "by_status": {
      "draft": 5,
      "active": 3,
      "closed": 30,
      "rejected": 4
    }
  },
  "vote_summary": {
    "total_votes": 1250
  },
  "council_summary": {
    "active_members": 7
  },
  "recent_proposals": [
    {
      "id": "uuid-here",
      "title": "Proposal Title",
      "status": "ACTIVE",
      "created_at": "2026-02-14T10:00:00.000000+00:00"
    }
  ],
  "timestamp": "2026-02-14T12:00:00.000000+00:00"
}
```

#### 5. GET /api/audit_summary

Returns recent audit log entries including event types, timestamps, and context.

**Query Parameters:**
- `limit`: Number of audit entries to return (default: 10, max: 100)

**Example Response:**
```json
{
  "count": 10,
  "limit": 10,
  "audit_entries": [
    {
      "id": "uuid-here",
      "action_type": "USER_LOGIN",
      "timestamp": "2026-02-14T11:30:00.000000+00:00",
      "details": {
        "ip_address": "192.168.1.1"
      }
    }
  ],
  "timestamp": "2026-02-14T12:00:00.000000+00:00"
}
```

### Running the Observability Node

The observability node can run independently from the main API:

```bash
# Install dependencies
pip install -r requirements.txt

# Set required environment variables
export DATABASE_URL="postgresql://user:pass@localhost/dbname"
export OBSERVABILITY_PORT=8080  # Optional, defaults to 8080

# Run the observability node
python -m observability_node.run
```

Or run using Python directly:

```bash
cd observability_node
python app.py
```

### Configuration

The observability node respects the following environment variables:

- `DATABASE_URL`: PostgreSQL connection string (required)
- `OBSERVABILITY_PORT`: Port to bind to (default: 8080)
- `OBSERVABILITY_HOST`: Host to bind to (default: 0.0.0.0)
- `CELERY_BROKER_URL`: Redis connection string (optional, for queue metrics)
- `DB_USER`, `DB_PASS`, `DB_NAME`, `INSTANCE_CONNECTION_NAME`: Google Cloud Run configuration (auto-detected)

### Security & Safety

- **No Authentication Required**: The node is read-only and exposes only non-sensitive system state.
- **No Secrets Exposed**: No credentials, keys, or user data are included in responses.
- **No Write Operations**: All endpoints are read-only snapshots.
- **JSON Only**: All responses are in JSON format for easy parsing.
- **Rate Limiting**: Consider adding rate limiting in production deployments.

### Architecture

The observability node is built as a separate Flask application with:

- `observability_node/app.py`: Main Flask application with endpoint definitions
- `observability_node/metrics.py`: System metrics collection using psutil
- `observability_node/run.py`: Standalone runner script

This separation ensures the observability layer can run independently from the main API and provides a clean interface for monitoring system health.

## Closing

The People's Coin backend represents a forward-looking approach to combining public-ledger principles with intelligent system orchestration. By pairing transparent data handling with adaptive resource management, the platform is designed to remain resilient, scalable, and accountable as it grows.

## About

The People's Coin backend is a Flask- and PostgreSQL-based system that securely records goodwill actions, manages user and governance data, and dynamically monitors system health. Its System Controller enables adaptive behavior inspired by biological systems, providing a transparent and scalable foundation for community-driven platforms.
