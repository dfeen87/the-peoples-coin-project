import os
import time
import json
import logging
from datetime import datetime, timedelta
import psutil
from sqlalchemy import create_engine, text
from apscheduler.schedulers.blocking import BlockingScheduler
from kubernetes import client, config

# --- Configuration ---
# Load from environment variables, with defaults for local development
DB_URI = os.environ.get("DB_URI", "sqlite:///instance/peoples_coin.models")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/1")
KUBE_DEPLOYMENT_NAME = os.environ.get("KUBE_DEPLOYMENT_NAME", "your-app-deployment")
KUBE_NAMESPACE = os.environ.get("KUBE_NAMESPACE", "default")
KUBE_MAX_REPLICAS = int(os.environ.get("KUBE_MAX_REPLICAS", 10))
KUBE_MIN_REPLICAS = int(os.environ.get("KUBE_MIN_REPLICAS", 1))


# --- Setup ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("controller")

# --- Database Schema for Action Logging ---
# You would need to create this table in your database for history to work.
#
# For PostgreSQL:
# CREATE TABLE IF NOT EXISTS controller_actions (
#     id SERIAL PRIMARY KEY,
#     timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
#     user_id UUID NULL REFERENCES user_accounts(id) ON DELETE SET NULL,
#     recommendations JSONB,
#     actions_taken JSONB
# );
# CREATE INDEX IF NOT EXISTS idx_controller_actions_timestamp ON controller_actions(timestamp);
#
# For SQLite:
# CREATE TABLE IF NOT EXISTS controller_actions (
#     id INTEGER PRIMARY KEY AUTOINCREMENT,
#     timestamp TIMESTAMP NOT NULL,
#     user_id TEXT NULL,
#     recommendations TEXT,
#     actions_taken TEXT
# );


class SystemController:
    """
    A final, robust controller that monitors system health, analyzes trends,
    and applies adjustments to Kubernetes deployments in a scheduled, fault-tolerant manner.
    """

    def __init__(self, db_uri: str, redis_url: str = None):
        self.db_engine = create_engine(db_uri)
        try:
            self.redis = Redis.from_url(redis_url) if redis_url else None
        except ImportError:
            self.redis = None
        
        self.k8s_apps_v1 = self._init_kube_client()
        logger.info("🎮 Controller initialized.")

    def _init_kube_client(self):
        """Initializes and returns the Kubernetes AppsV1Api client."""
        try:
            config.load_kube_config()
            logger.info("✅ Kubernetes config loaded successfully.")
            return client.AppsV1Api()
        except Exception as e:
            logger.error(f"🔥 Failed to initialize Kubernetes client: {e}")
            return None

    def monitor(self):
        """Monitors instantaneous system metrics like CPU, memory, and queue lengths."""
        cpu = psutil.cpu_percent()
        mem = psutil.virtual_memory().percent
        disk = psutil.disk_usage("/").percent
        logger.info(f"📈 [Monitor] CPU: {cpu}%, Memory: {mem}%, Disk: {disk}%")

        if cpu > 95:
            logger.warning("🚨 [Monitor] High CPU detected!")
        if mem > 90:
            logger.warning("🚨 [Monitor] High Memory detected!")
        if disk > 90:
            logger.warning("🚨 [Monitor] Disk almost full!")

    def analyze(self) -> dict:
        """Analyzes historical metrics to produce actionable recommendations."""
        logger.info("🔍 [Analyzer] Running analysis...")
        recommendations = {}
        
        queue_len = 0
        if self.redis:
            try:
                queue_len = self.redis.llen("task_queue") or 0
            except Exception as e:
                logger.error(f"[Analyzer] Could not check Redis queue length: {e}")

        try:
            with self.db_engine.connect() as conn:
                since_time = datetime.utcnow() - timedelta(hours=1)
                
                result = conn.execute(
                    text("SELECT AVG(cpu_load), AVG(mem_usage), COUNT(*) FROM system_metrics WHERE timestamp > :since"),
                    {"since": since_time.timestamp()}
                ).fetchone()

                if result and result[0] is not None:
                    avg_cpu, avg_mem, count = result
                    logger.info(f"📊 [Analyzer] 1h avg CPU: {avg_cpu:.2f}%, Mem: {avg_mem:.2f}%, Samples: {count}")

                    if avg_cpu > 80:
                        recommendations["adjust_worker_count"] = -1
                    elif avg_cpu < 40 and queue_len > 100:
                        recommendations["adjust_worker_count"] = 1
                    
                    if avg_mem > 85:
                        recommendations["increase_memory_limit"] = True
                    if count < 10:
                        recommendations["increase_metrics_frequency"] = True
                else:
                    logger.warning("[Analyzer] No recent metrics found in the database.")
        
        except Exception as e:
            logger.error(f"[Analyzer] DB error: {e}", exc_info=True)

        logger.info(f"💾 [Analyzer] Recommendations produced: {recommendations}")
        return recommendations

    def manage(self, recommendations: dict) -> list:
        """Applies adjustments to the Kubernetes deployment."""
        logger.info(f"🛠️ [Manager] Running with recommendations: {recommendations}")
        actions_taken = []
        if not self.k8s_apps_v1:
            logger.warning("[Manager] Kubernetes client not available. Skipping management actions.")
            return actions_taken
        if not recommendations:
            return actions_taken

        if "adjust_worker_count" in recommendations:
            adjustment = recommendations["adjust_worker_count"]
            try:
                deployment = self.k8s_apps_v1.read_namespaced_deployment(name=KUBE_DEPLOYMENT_NAME, namespace=KUBE_NAMESPACE)
                current_replicas = deployment.spec.replicas
                desired_replicas = current_replicas + adjustment
                
                # Clamp the desired count between min and max bounds
                desired_replicas = max(KUBE_MIN_REPLICAS, min(desired_replicas, KUBE_MAX_REPLICAS))

                if desired_replicas != current_replicas:
                    logger.info(f"🚀 [K8s] Scaling deployment '{KUBE_DEPLOYMENT_NAME}' from {current_replicas} to {desired_replicas} replicas.")
                    body = {"spec": {"replicas": desired_replicas}}
                    self.k8s_apps_v1.patch_namespaced_deployment_scale(
                        name=KUBE_DEPLOYMENT_NAME,
                        namespace=KUBE_NAMESPACE,
                        body=body
                    )
                    action = f"Scaled Kubernetes deployment to {desired_replicas} replicas."
                    actions_taken.append(action)
                else:
                    logger.info(f"✅ [K8s] Desired replica count ({desired_replicas}) already matches current state. No action needed.")

            except Exception as e:
                error_msg = f"🔥 [K8s] Failed to scale deployment: {e}"
                logger.error(error_msg)
                actions_taken.append(error_msg)
        
        logger.info("✅ [Manager] Actions completed.")
        return actions_taken

    def _log_action_to_db(self, recommendations: dict, actions_taken: list):
        """Logs recommendations and actions to the database for historical analysis."""
        if not recommendations:
            return

        logger.info("✍️  [Logger] Storing action history to database.")
        try:
            with self.db_engine.connect() as conn:
                stmt = text(
                    "INSERT INTO controller_actions (timestamp, recommendations, actions_taken) VALUES (:ts, :rec, :act)"
                )
                conn.execute(stmt, {
                    "ts": datetime.utcnow(),
                    "rec": json.dumps(recommendations),
                    "act": json.dumps(actions_taken)
                })
                conn.commit()
        except Exception as e:
            logger.error(f"[Logger] Failed to log actions to DB: {e}")
            
    def analysis_and_management_cycle(self):
        """A single, complete cycle of analysis, management, and logging."""
        recommendations = self.analyze()
        actions_taken = self.manage(recommendations)
        self._log_action_to_db(recommendations, actions_taken)

if __name__ == "__main__":
    # Ensure you have the required libraries installed:
    # pip install sqlalchemy psutil apscheduler redis kubernetes
    
    controller = SystemController(db_uri=DB_URI, redis_url=REDIS_URL)
    scheduler = BlockingScheduler(timezone="UTC")

    scheduler.add_job(controller.monitor, 'interval', minutes=1, id='monitor_job')
    scheduler.add_job(controller.analysis_and_management_cycle, 'interval', minutes=10, id='analysis_management_job')

    logger.info("🚀 Starting Controller scheduler. Press Ctrl+C to exit.")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("🛑 Shutting down controller.")
        scheduler.shutdown()
