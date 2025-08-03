import os
import json
import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy import create_engine, text

# --- Configuration ---
DB_URI = os.environ.get(
    "DB_URI",
    "postgresql+psycopg2://user:password@/peoples-coin-cluster-final"  # Replace with actual connection string if needed
)
REDIS_URL = os.environ.get("REDIS_URL", "redis://10.128.0.12:6379/0")  # Updated Redis IP here
CONTROLLER_COOLDOWN_MINUTES = int(os.environ.get("CONTROLLER_COOLDOWN_MINUTES", 10))

# --- Setup ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("controller")

try:
    from redis import Redis
except ImportError:
    Redis = None

class SystemController:
    def __init__(self, db_uri: str, redis_url: str = None):
        self.db_engine = create_engine(db_uri)
        self.redis = Redis.from_url(redis_url) if Redis and redis_url else None
        self.last_action_time = None
        self.cooldown_period = timedelta(minutes=CONTROLLER_COOLDOWN_MINUTES)
        logger.info("🎮 Controller initialized without Kubernetes.")

    def analyze(self) -> dict:
        logger.info("🔍 Running analysis...")
        recommendations = {}

        try:
            with self.db_engine.connect() as conn:
                pending_actions_query = text(
                    "SELECT COUNT(*) FROM goodwill_actions WHERE status = 'PENDING_VERIFICATION'"
                )
                pending_actions = conn.execute(pending_actions_query).scalar() or 0
                logger.info(f"📊 Pending goodwill actions: {pending_actions}")

                if pending_actions > 100:
                    recommendations["scale_up"] = True
                    logger.warning("📈 High backlog detected, recommend scaling up.")

                one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
                ten_mins_ago = datetime.now(timezone.utc) - timedelta(minutes=10)

                avg_cpu_query = text(
                    "SELECT AVG(cpu_load) FROM system_metrics WHERE timestamp > :since"
                )
                hourly_avg_cpu = conn.execute(avg_cpu_query, {"since": one_hour_ago}).scalar() or 0.0
                recent_avg_cpu = conn.execute(avg_cpu_query, {"since": ten_mins_ago}).scalar() or 0.0

                logger.info(f"📊 1h avg CPU: {hourly_avg_cpu:.2f}%, 10m avg CPU: {recent_avg_cpu:.2f}%")

                if hourly_avg_cpu > 80:
                    recommendations["scale_up"] = True
                    logger.warning("📈 Sustained high CPU, recommend scaling up.")
                elif recent_avg_cpu > 60 and recent_avg_cpu > hourly_avg_cpu * 1.5:
                    recommendations["scale_up"] = True
                    logger.warning("📈 Sharp CPU increase detected, recommend scaling up.")
                elif hourly_avg_cpu < 30 and pending_actions < 10:
                    recommendations["scale_down"] = True
                    logger.info("📉 Low load and clear backlog, recommend scaling down.")

        except Exception as e:
            logger.error(f"DB analysis error: {e}", exc_info=True)

        logger.info(f"Recommendations: {recommendations}")
        return recommendations

    def manage(self, recommendations: dict) -> list:
        if self.last_action_time and (datetime.now(timezone.utc) - self.last_action_time < self.cooldown_period):
            logger.info("❄️ In cooldown period, skipping management actions.")
            return []

        actions_taken = []

        if recommendations.get("scale_up"):
            logger.info("🔼 Triggering scale-up action (placeholder).")
            actions_taken.append("Scale-up action triggered.")
        elif recommendations.get("scale_down"):
            logger.info("🔽 Triggering scale-down action (placeholder).")
            actions_taken.append("Scale-down action triggered.")
        else:
            logger.info("No scaling actions required.")

        if actions_taken:
            self.last_action_time = datetime.now(timezone.utc)
            logger.info(f"⏱️ Cooldown started for {self.cooldown_period.total_seconds()/60} minutes.")

        return actions_taken

    def _log_action_to_db(self, recommendations: dict, actions_taken: list):
        if not recommendations and not actions_taken:
            return
        try:
            with self.db_engine.connect() as conn:
                stmt = text(
                    "INSERT INTO controller_actions (timestamp, recommendations, actions_taken) VALUES (:ts, :rec, :act)"
                )
                conn.execute(
                    stmt,
                    {
                        "ts": datetime.now(timezone.utc),
                        "rec": json.dumps(recommendations),
                        "act": json.dumps(actions_taken),
                    },
                )
                conn.commit()
                logger.info("Logged actions to DB.")
        except Exception as e:
            logger.error(f"Failed to log actions to DB: {e}")

    def run_cycle(self):
        recommendations = self.analyze()
        actions_taken = self.manage(recommendations)
        self._log_action_to_db(recommendations, actions_taken)


# Uncomment and adapt to run as a script or schedule with an external tool
# if __name__ == "__main__":
#     controller = SystemController(db_uri=DB_URI, redis_url=REDIS_URL)
#     # e.g., run every 5 minutes with a scheduler or cron
#     import time
#     while True:
#         controller.run_cycle()
#         time.sleep(300)

