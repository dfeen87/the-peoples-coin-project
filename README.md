# The People's Coin — Backend & System Controller

**License:** MIT  
**Stack:** Python (Flask), PostgreSQL 15, SQLAlchemy, Docker  
**Status:** Working backend · Structure stabilized · Live site currently non-functional

## ⚠️ Disclaimer

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

## Closing

The People's Coin backend represents a forward-looking approach to combining public-ledger principles with intelligent system orchestration. By pairing transparent data handling with adaptive resource management, the platform is designed to remain resilient, scalable, and accountable as it grows.

## About

The People's Coin backend is a Flask- and PostgreSQL-based system that securely records goodwill actions, manages user and governance data, and dynamically monitors system health. Its System Controller enables adaptive behavior inspired by biological systems, providing a transparent and scalable foundation for community-driven platforms.
