# peoples_coin/systems/controller.py

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from flask import Flask
from sqlalchemy import text

from peoples_coin.extensions import db
from peoples_coin.models import ControllerAction # Import the correct model

logger = logging.getLogger("controller")

class SystemController:
    """Analyzes system metrics and makes scaling or management recommendations."""
    def __init__(self):
        self.app: Optional[Flask] = None
        self.last_action_time: Optional[datetime] = None
        self._initialized = False
        logger.info("🎮 Controller instance created.")

    def init_app(self, app: Flask):
        """Initializes the controller with the Flask app context."""
        if self._initialized:
            return
        self.app = app
        self.cooldown_period = timedelta(
            minutes=self.app.config.get("CONTROLLER_COOLDOWN_MINUTES", 10)
        )
        self._initialized = True
        logger.info("🎮 Controller initialized.")

    def analyze(self) -> dict:
        """Analyzes database metrics to generate recommendations."""
        logger.info("🔍 Running analysis...")
        recommendations = {}
        if not self.app:
            return recommendations

        with self.app.app_context():
            try:
                with db.engine.connect() as conn:
                    # Check for a backlog of goodwill actions
                    pending_actions_query = text(
                        "SELECT COUNT(*) FROM goodwill_actions WHERE status = 'PENDING_VERIFICATION'"
                    )
                    pending_actions = conn.execute(pending_actions_query).scalar() or 0
                    logger.info(f"📊 Pending goodwill actions: {pending_actions}")

                    if pending_actions > self.app.config.get("CONTROLLER_BACKLOG_THRESHOLD", 100):
                        recommendations["scale_up"] = "High backlog of goodwill actions."
                        logger.warning("📈 High backlog detected, recommend scaling up.")
                    
                    # TODO: Implement a real metrics source (e.g., Prometheus, Cloud Monitoring)
                    # The 'system_metrics' table does not exist in the schema.
                    # The following is an example of how you would use it if it existed.
                    # elif hourly_avg_cpu < 30 and pending_actions < 10:
                    #     recommendations["scale_down"] = "Low load and clear backlog."
                    #     logger.info("📉 Low load and clear backlog, recommend scaling down.")

            except Exception as e:
                logger.error(f"DB analysis error: {e}", exc_info=True)

        logger.info(f"Recommendations: {recommendations}")
        return recommendations

    def manage(self, recommendations: dict) -> list:
        """Acts on recommendations, respecting a cooldown period."""
        if self.last_action_time and (datetime.now(timezone.utc) - self.last_action_time < self.cooldown_period):
            logger.info("❄️ In cooldown period, skipping management actions.")
            return []

        actions_taken = []
        if recommendations.get("scale_up"):
            logger.info(f"🔼 Triggering scale-up action (placeholder). Reason: {recommendations['scale_up']}")
            actions_taken.append("Scale-up triggered.")
        if recommendations.get("scale_down"):
            logger.info(f"🔽 Triggering scale-down action (placeholder). Reason: {recommendations['scale_down']}")
            actions_taken.append("Scale-down triggered.")
        
        if actions_taken:
            self.last_action_time = datetime.now(timezone.utc)
        
        return actions_taken

    def _log_action_to_db(self, recommendations: dict, actions_taken: list):
        """Logs the analysis and actions to the database."""
        if not recommendations and not actions_taken:
            return
        if not self.app:
            return
            
        with self.app.app_context():
            try:
                db.session.add(
                    ControllerAction(
                        recommendations=recommendations,
                        actions_taken=actions_taken,
                    )
                )
                db.session.commit()
                logger.info("Logged actions to DB.")
            except Exception as e:
                db.session.rollback()
                logger.error(f"Failed to log actions to DB: {e}", exc_info=True)

    def run_cycle(self):
        """Runs one full analyze-manage-log cycle."""
        recommendations = self.analyze()
        actions_taken = self.manage(recommendations)
        self._log_action_to_db(recommendations, actions_taken)

# Singleton instance
controller_system = SystemController()

# --- Function for status page ---
def get_controller_status():
    """Health check for the Controller System."""
    if controller_system._initialized:
        return {"active": True, "healthy": True, "info": "Controller operational"}
    else:
        return {"active": False, "healthy": False, "info": "Controller not initialized"}
