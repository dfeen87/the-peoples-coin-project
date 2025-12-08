The People’s Coin — Backend & System Controller

Disclaimer: The live site is non-functional. Some keys and credentials are included for illustrative purposes only—do not rely on them for operational use.

Project Overview
The People’s Coin backend forms the resilient heart of the platform, designed to reliably record and process acts of goodwill contributed by users worldwide. Its architecture is built on PostgreSQL 15 for durable, scalable data storage, combined with a RESTful Flask API to expose endpoints for managing user accounts, wallets, goodwill actions, proposals, and governance features like council members. This backend system ensures that every user interaction is securely recorded, validated, and available for auditing, while maintaining high performance even as traffic grows.

Central to this system is the System Controller, an intelligent orchestration layer that continuously monitors system health indicators such as CPU load, memory usage, disk space, and task queue lengths. It analyzes this data both in real-time and historically by querying the database, making data-driven recommendations to optimize the backend’s performance. This includes dynamically adjusting the number of background workers or Kubernetes pods to handle workload fluctuations, ensuring efficient use of resources and consistent responsiveness.

Architecture and Components
The backend is organized around a modular design: SQLAlchemy ORM maps database tables with UUID keys, ENUM types for statuses, JSONB columns for flexible contextual data, and triggers to maintain updated timestamps. Background workers process asynchronous tasks, and the system controller orchestrates these workers based on monitored system load and queue backlog.

When deployed on cloud infrastructure, the backend can integrate with Kubernetes clusters. This allows the system controller to programmatically scale the deployment’s replicas up or down based on analyzed workload patterns, maintaining an ideal balance between performance and cost.

All decisions made by the controller are logged into a dedicated controller_actions database table, capturing timestamps, recommendations, and actions taken. This audit trail supports transparency and future analysis of system behavior.

Inspired by Biological Systems
The architecture of The People’s Coin backend and its System Controller draws inspiration from complex biological systems, such as the human nervous, immune, and endocrine systems. Just as these natural systems continuously monitor, adapt, and maintain homeostasis in the body, our backend continuously observes system health, adapts resource allocation, and maintains performance equilibrium across distributed services.

This biomimetic approach helps ensure resilience, scalability, and efficient self-regulation in a dynamic environment. The System Controller acts like the body’s central nervous system, processing real-time signals and historical data to make informed decisions that keep the platform healthy and responsive. This philosophy guides both design and implementation, enabling the platform to grow organically and maintain stability under varying workloads.

Kubernetes Integration
For environments leveraging Kubernetes, the controller interacts directly with the cluster’s API to adjust the backend deployment’s replica count within configured minimum and maximum bounds. This integration requires the Kubernetes configuration to be accessible to the controller application, enabling secure, authorized scaling operations. Environment variables control the deployment name, namespace, and scaling limits, allowing seamless adaptation across different cloud setups or environments.

Monitoring and Logging
The system controller uses psutil to capture instantaneous system metrics such as CPU usage, memory consumption, and disk utilization. It also queries the database to understand workload trends over the past hour, and optionally checks Redis queues to measure task backlog. Based on this rich dataset, it makes intelligent scaling recommendations.

Every cycle, the controller logs both the recommendations and the actual scaling actions taken into the database and system logs, fostering accountability and enabling historical analysis to improve future decisions. The system is designed to gracefully handle the absence of optional components like Redis or Kubernetes, continuing to monitor without automated scaling if necessary.

Technologies and Tools
The backend leverages mature, production-ready technologies to ensure robustness and maintainability. It uses Flask for the web framework, SQLAlchemy for ORM capabilities, and PostgreSQL 15 as the primary database. Optional components include Redis for queue management, psutil for system monitoring, APScheduler for periodic job scheduling, and the Kubernetes Python client for orchestrating cloud deployments.

Getting Started
To get the backend running, first clone the repository and create a Python virtual environment. Install all dependencies listed in the requirements.txt file. Set up the PostgreSQL database by running the provided SQL schema file, which creates all necessary tables and types. Then start the Flask API server. Separately, launch the system controller script which will begin monitoring and managing the backend resources in a scheduled, automated manner.

Development and Production Readiness
The system is built for fault tolerance and modularity. It operates with or without Redis and Kubernetes integrations, adjusting behavior based on the available infrastructure. Scaling actions respect configured minimum and maximum replica counts to prevent resource thrashing. Logging and database auditing ensure all automated decisions are traceable. This design promotes a solid foundation for growth and provides maintainers with clear insight into system health and scaling history.

Closing
The People’s Coin backend represents a forward-thinking approach to combining blockchain-inspired public ledgers with intelligent resource orchestration, designed to foster and reward acts of goodwill globally. This detailed backend architecture and its intelligent controller enable a resilient, scalable, and transparent platform, ready to support users today and evolve as the community grows.
