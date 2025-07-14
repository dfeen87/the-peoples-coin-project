import logging
import time
import random
import os
import sys
from datetime import datetime, timezone
from typing import Optional

from flask import current_app
from sqlalchemy.exc import SQLAlchemyError

# Only needed if running directly for local test/demo
if __name__ == "__main__":
    current_file_dir = os.path.dirname(os.path.abspath(__file__))
    src_dir = os.path.dirname(os.path.dirname(current_file_dir))
    sys.path.insert(0, src_dir)

from peoples_coin.db.db_utils import get_session_scope
from peoples_coin.db.models import GoodwillAction
from peoples_coin.ailee.ailee_monitor import AILEE_Monitor
from peoples_coin.config import Config

logger = logging.getLogger(__name__)

# --- Celery Setup ---
from celery import Celery
from celery.utils.log import get_task_logger

celery_logger = get_task_logger(__name__)

def make_celery(app: 'flask.Flask') -> Celery:
    """Create and configure a Celery instance with Flask context support."""
    celery = Celery(
        app.import_name,
        broker=app.config.get("CELERY_BROKER_URL", "redis://localhost:6379/0"),
        backend=app.config.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")
    )
    celery.conf.update(app.config)
    
    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    celery.Task = ContextTask
    return celery

# --- Configuration Validation ---
def validate_config():
    """Ensures all required config keys are set in Flask app."""
    required_keys = [
        "AILEE_ISP", "AILEE_ETA", "AILEE_ALPHA", "AILEE_V0", "L_ETA_L",
        "CELERY_BROKER_URL", "CELERY_RESULT_BACKEND"
    ]
    missing = [key for key in required_keys if current_app.config.get(key) is None]
    if missing:
        raise RuntimeError(f"Missing required config keys: {missing}")

# --- Love Resonance Calculation ---
def _calculate_love_resonance_score(
    coherence: float,
    mutual_information: float,
    spiritual_potential: float,
    wave_function_psi: float,
    eta_L: float
) -> float:
    """Calculates a composite love resonance score based on inputs."""
    # Ensure inputs are non-negative
    coherence = max(0.0, coherence)
    mutual_information = max(0.0, mutual_information)
    spiritual_potential = max(0.0, spiritual_potential)
    wave_function_psi = max(0.0, wave_function_psi)
    eta_L = max(0.0, eta_L)

    love_resonance_component = coherence * mutual_information * spiritual_potential * wave_function_psi
    return eta_L * love_resonance_component

# --- Initialize celery variable to avoid NameError ---
celery = None  # Will be assigned when app is created (in main/demo or elsewhere)

# --- Celery Task ---
@celery.task(bind=True, max_retries=3, default_retry_delay=10)
def process_goodwill_action_task(self, action_id: int):
    """Asynchronous task to process a GoodwillAction by running AI and resonance calculations."""
    celery_logger.info(f"🚀 Starting async AI processing for GoodwillAction ID: {action_id}")
    try:
        validate_config()
        
        ailee_isp = current_app.config["AILEE_ISP"]
        ailee_eta = current_app.config["AILEE_ETA"]
        ailee_alpha = current_app.config["AILEE_ALPHA"]
        ailee_v0_default = current_app.config["AILEE_V0"]
        l_eta_l = current_app.config["L_ETA_L"]

        ailee_monitor = AILEE_Monitor(
            Isp=ailee_isp, eta=ailee_eta, alpha=ailee_alpha, v0=ailee_v0_default
        )

        db_instance = current_app.extensions['sqlalchemy'].db

        with get_session_scope(db_instance) as session:
            goodwill_action = session.query(GoodwillAction).filter_by(id=action_id).first()
            if not goodwill_action:
                celery_logger.error(f"GoodwillAction with ID {action_id} not found.")
                return

            if goodwill_action.status != 'pending':
                celery_logger.warning(
                    f"GoodwillAction ID {action_id} status is '{goodwill_action.status}', skipping processing."
                )
                return

            celery_logger.debug(f"Processing GoodwillAction: '{goodwill_action.description}' (Type: {goodwill_action.action_type})")

            # Simulate sampling metrics over a duration with intervals
            operation_duration_seconds = random.uniform(5, 20)
            sampling_interval_seconds = 1.0
            num_samples = int(operation_duration_seconds / sampling_interval_seconds)
            start_time = datetime.now(timezone.utc)

            current_v0 = goodwill_action.contextual_data.get('initial_model_state_v0', ailee_v0_default)
            ailee_monitor.v0 = current_v0

            for _ in range(num_samples):
                current_time = datetime.now(timezone.utc)
                P_input_t = goodwill_action.contextual_data.get('client_compute_estimate', 5.0) * random.uniform(0.8, 1.2)
                P_input_t = max(0.1, P_input_t)
                w_t = goodwill_action.contextual_data.get('expected_workload_intensity_w0', 2.0) * random.uniform(0.7, 1.3)
                w_t = max(0.1, w_t)
                v_t = random.uniform(0.001, 0.1)
                M_t = 100.0 + random.uniform(-10, 10)
                M_t = max(1.0, M_t)

                ailee_monitor.record_metrics(current_time, P_input_t, w_t, v_t, M_t)
                celery_logger.debug(
                    f"  Recorded metrics at {current_time.strftime('%H:%M:%S')}: P={P_input_t:.2f}, w={w_t:.2f}, v={v_t:.3f}, M={M_t:.1f}"
                )
                time.sleep(sampling_interval_seconds)

            ailee_delta_v = ailee_monitor.calculate_delta_v()
            celery_logger.info(f"✅ AILEE Delta V calculated for GoodwillAction ID {action_id}: {ailee_delta_v:.4f}")

            # Love resonance sample params based on action_type
            coherence_val = 0.5
            mutual_info_val = 0.5
            spiritual_potential_val = 0.5
            wave_function_psi_val = 1.0

            if goodwill_action.action_type == 'federated_learning_update':
                coherence_val = random.uniform(0.7, 0.9)
                mutual_info_val = random.uniform(0.6, 0.8)
                spiritual_potential_val = random.uniform(0.6, 0.7)
            elif goodwill_action.action_type == 'anomaly_detection_inference':
                coherence_val = random.uniform(0.4, 0.6)
                mutual_info_val = random.uniform(0.7, 0.9)
                spiritual_potential_val = random.uniform(0.7, 0.8)

            love_resonance_score = _calculate_love_resonance_score(
                coherence=coherence_val,
                mutual_information=mutual_info_val,
                spiritual_potential=spiritual_potential_val,
                wave_function_psi=wave_function_psi_val,
                eta_L=l_eta_l
            )
            celery_logger.info(f"💖 Love Resonance Score for GoodwillAction ID {action_id}: {love_resonance_score:.4f}")

            final_resonance_score = ailee_delta_v + (love_resonance_score * 0.1)
            final_resonance_score = max(0.0, final_resonance_score)
            celery_logger.info(f"✨ Final Composite Resonance Score for GoodwillAction ID {action_id}: {final_resonance_score:.4f}")

            goodwill_action.resonance_score = final_resonance_score
            goodwill_action.status = 'processed'
            goodwill_action.processed_at = datetime.now(timezone.utc)

            session.add(goodwill_action)
            session.flush()

            celery_logger.info(f"💾 GoodwillAction ID {action_id} updated with resonance_score: {final_resonance_score:.4f} and status 'processed'.")

    except SQLAlchemyError as e:
        celery_logger.error(f"Database error processing GoodwillAction ID {action_id}: {e}", exc_info=True)
        raise self.retry(exc=e, countdown=2 ** self.request.retries)
    except Exception as e:
        celery_logger.error(f"Unexpected error in GoodwillAction ID {action_id} processing: {e}", exc_info=True)
        raise self.retry(exc=e, countdown=2 ** self.request.retries)


# --- Local Testing / Demo ---
if __name__ == "__main__":
    import flask
    from peoples_coin.extensions import db

    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

    app = flask.Flask(__name__)

    # Setup config and DB URI (adjust paths if needed)
    project_root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    db_path = os.path.join(project_root_dir, 'instance', 'peoples_coin.db')
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config.from_object(Config)

    # Add Celery config for local testing (optional)
    app.config["CELERY_BROKER_URL"] = "redis://localhost:6379/0"
    app.config["CELERY_RESULT_BACKEND"] = "redis://localhost:6379/0"

    # Create Celery instance after app config is ready
    celery = make_celery(app)

    db.init_app(app)

    with app.app_context():
        # Prepare DB tables if not exist
        if not os.path.exists(db_path):
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
            db.create_all()

        test_action_id: Optional[int] = None

        with get_session_scope(db) as session:
            existing_action = session.query(GoodwillAction).filter_by(
                user_id="test_user_123", status='pending'
            ).first()

            if not existing_action:
                new_action = GoodwillAction(
                    user_id="test_user_123",
                    action_type="federated_learning_update",
                    description="Simulated FL update for test",
                    timestamp=datetime.now(timezone.utc),
                    contextual_data={
                        'initial_model_state_v0': 0.2,
                        'expected_workload_intensity_w0': 3.5,
                        'client_compute_estimate': 7.0
                    },
                    status='pending',
                    correlation_id=f"test_corr_{int(time.time())}"
                )
                session.add(new_action)
                session.flush()
                test_action_id = new_action.id
                logger.info(f"Created test GoodwillAction with ID: {test_action_id}")
            else:
                test_action_id = existing_action.id
                logger.info(f"Found existing pending GoodwillAction with ID: {test_action_id}")

        if test_action_id:
            celery_logger.info(f"Triggering Celery task for GoodwillAction ID {test_action_id}")
            process_goodwill_action_task.delay(test_action_id)
        else:
            logger.error("Failed to obtain a test GoodwillAction ID.")

    logger.info("Demonstration complete. Run a Celery worker to process tasks.")

