import os
import time
import json
import logging
from datetime import datetime, timedelta, timezone
import psutil
from sqlalchemy import create_engine, text
from apscheduler.schedulers.blocking import BlockingScheduler
from kubernetes import client, config

# --- Configuration ---
DB_URI = os.environ.get("DB_URI", "sqlite:///instance/peoples_coin.db")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/1")
KUBE_DEPLOYMENT_NAME = os.environ.get("KUBE_DEPLOYMENT_NAME", "your-app-deployment")
KUBE_NAMESPACE = os.environ.get("KUBE_NAMESPACE", "default")
KUBE_MAX_REPLICAS = int(os.environ.get("KUBE_MAX_REPLICAS", 10))
KUBE_MIN_REPLICAS = int(os.environ.get("KUBE_MIN_REPLICAS", 1))
CONTROLLER_COOLDOWN_MINUTES = int(os.environ.get("CONTROLLER_COOLDOWN_MINUTES", 10))


# --- Setup ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("controller")

try:
    from redis import Redis
except ImportError:
    Redis = None

class SystemController:
    """
    An intelligent controller that monitors system health, analyzes trends,
    and applies adjustments to Kubernetes deployments.
    """

    def __init__(self, db_uri: str, redis_url: str = None):
        self.db_engine = create_engine(db_uri)
        self.redis = Redis.from_url(redis_url) if Redis and redis_url else None
        self.k8s_apps_v1 = self._init_kube_client()
        
        # State for cooldown logic
        self.last_action_time: datetime = None
        self.cooldown_period = timedelta(minutes=CONTROLLER_COOLDOWN_MINUTES)
        
        logger.info("🎮 Controller initialized.")

    def _init_kube_client(self):
        """Initializes the Kubernetes AppsV1Api client."""
        try:
            config.load_incluster_config() # For running inside a K8s cluster
            logger.info("✅ Kubernetes in-cluster config loaded.")
        except config.ConfigException:
            try:
                config.load_kube_config() # Fallback for local development
                logger.info("✅ Kubernetes kube-config loaded.")
            except config.ConfigException as e:
                logger.error(f"🔥 Could not load any Kubernetes config: {e}")
                return None
        return client.AppsV1Api()

    def analyze(self) -> dict:
        """Analyzes historical and business metrics to produce actionable recommendations."""
        logger.info("🔍 [Analyzer] Running analysis...")
        recommendations = {}
        
        try:
            with self.db_engine.connect() as conn:
                # Business Metric: Check the backlog of pending goodwill actions
                pending_actions_query = text("SELECT COUNT(*) FROM goodwill_actions WHERE status = 'PENDING_VERIFICATION'")
                pending_actions = conn.execute(pending_actions_query).scalar_one_or_none() or 0
                logger.info(f"📊 [Analyzer] Business Metric: {pending_actions} pending goodwill actions.")

                if pending_actions > 100:
                    recommendations["adjust_worker_count"] = 1
                    logger.warning(f"📈 [Analyzer] Recommendation: High action backlog ({pending_actions}), scaling up.")
                
                # System Metrics: Analyze historical CPU usage for trends
                one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
                ten_mins_ago = datetime.now(timezone.utc) - timedelta(minutes=10)

                # Assuming a `system_metrics` table with `timestamp` (datetime) and `cpu_load` (float)
                hourly_avg_query = text("SELECT AVG(cpu_load) FROM system_metrics WHERE timestamp > :since")
                hourly_avg_cpu = conn.execute(hourly_avg_query, {"since": one_hour_ago}).scalar_one_or_none() or 0.0

                recent_avg_cpu = conn.execute(hourly_avg_query, {"since": ten_mins_ago}).scalar_one_or_none() or 0.0
                
                logger.info(f"📊 [Analyzer] System Metric: 1h avg CPU: {hourly_avg_cpu:.2f}%, 10m avg CPU: {recent_avg_cpu:.2f}%")

                # Reactive scaling for sustained high load
                if hourly_avg_cpu > 80:
                    recommendations["adjust_worker_count"] = 1
                    logger.warning(f"📈 [Analyzer] Recommendation: Sustained high CPU ({hourly_avg_cpu:.2f}%), scaling up.")
                
                # Predictive scaling for sharp upward trends
                elif recent_avg_cpu > 60 and recent_avg_cpu > hourly_avg_cpu * 1.5:
                     recommendations["adjust_worker_count"] = 1
                     logger.warning(f"📈 [Analyzer] Recommendation: Sharp CPU trend detected, scaling up proactively.")

                # Scale down if load is consistently low and backlog is clear
                elif hourly_avg_cpu < 30 and pending_actions < 10:
                    recommendations["adjust_worker_count"] = -1
                    logger.info(f"📉 [Analyzer] Recommendation: Sustained low load and clear backlog, scaling down.")

        except Exception as e:
            logger.error(f"[Analyzer] DB error: {e}", exc_info=True)

        logger.info(f"💾 [Analyzer] Recommendations produced: {recommendations}")
        return recommendations

    def manage(self, recommendations: dict) -> list:
        """Applies adjustments to the Kubernetes deployment, respecting cooldowns."""
        # **COOLDOWN LOGIC**: Prevent flapping by waiting after an action
        if self.last_action_time and (datetime.now(timezone.utc) - self.last_action_time < self.cooldown_period):
            logger.info(f"❄️ [Manager] In cooldown period. No action will be taken.")
            return []

        logger.info(f"🛠️ [Manager] Running with recommendations: {recommendations}")
        actions_taken = []
        if not self.k8s_apps_v1 or not recommendations:
            return actions_taken

        if "adjust_worker_count" in recommendations:
            adjustment = recommendations["adjust_worker_count"]
            try:
                deployment = self.k8s_apps_v1.read_namespaced_deployment(name=KUBE_DEPLOYMENT_NAME, namespace=KUBE_NAMESPACE)
                current_replicas = deployment.spec.replicas
                desired_replicas = max(KUBE_MIN_REPLICAS, min(current_replicas + adjustment, KUBE_MAX_REPLICAS))

                if desired_replicas != current_replicas:
                    logger.info(f"🚀 [K8s] Scaling deployment '{KUBE_DEPLOYMENT_NAME}' from {current_replicas} to {desired_replicas} replicas.")
                    body = {"spec": {"replicas": desired_replicas}}
                    self.k8s_apps_v1.patch_namespaced_deployment_scale(name=KUBE_DEPLOYMENT_NAME, namespace=KUBE_NAMESPACE, body=body)
                    action = f"Scaled Kubernetes deployment to {desired_replicas} replicas."
                    actions_taken.append(action)
                else:
                    logger.info(f"✅ [K8s] Desired replica count ({desired_replicas}) already at limit. No action taken.")
            except Exception as e:
                error_msg = f"🔥 [K8s] Failed to scale deployment: {e}"
                logger.error(error_msg)
                actions_taken.append(error_msg)
        
        # If any action was successfully taken, update the cooldown timer
        if actions_taken and "Failed" not in actions_taken[0]:
            self.last_action_time = datetime.now(timezone.utc)
            logger.info(f"⏱️ [Manager] Action taken. Cooldown timer started for {self.cooldown_period.total_seconds() / 60} minutes.")

        return actions_taken

    def _log_action_to_db(self, recommendations: dict, actions_taken: list):
        """Logs recommendations and actions to the database for historical analysis."""
        if not recommendations and not actions_taken:
            return

        try:
            with self.db_engine.connect() as conn:
                stmt = text("INSERT INTO controller_actions (timestamp, recommendations, actions_taken) VALUES (:ts, :rec, :act)")
                conn.execute(stmt, {"ts": datetime.now(timezone.utc), "rec": json.dumps(recommendations), "act": json.dumps(actions_taken)})
                conn.commit()
                logger.info("✍️  [Logger] Stored action history to database.")
        except Exception as e:
            logger.error(f"[Logger] Failed to log actions to DB: {e}")
            
    def run_cycle(self):
        """A single, complete cycle of analysis, management, and logging."""
        recommendations = self.analyze()
        actions_taken = self.manage(recommendations)
        self._log_action_to_db(recommendations, actions_taken)

if __name__ == "__main__":
    controller = SystemController(db_uri=DB_URI, redis_url=REDIS_URL)
    scheduler = BlockingScheduler(timezone="UTC")

    # Run the main analysis and management cycle every 5 minutes
    scheduler.add_job(controller.run_cycle, 'interval', minutes=5, id='management_cycle_job')

    logger.info("🚀 Starting Controller scheduler. Press Ctrl+C to exit.")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("🛑 Shutting down controller.")
        scheduler.shutdown()
