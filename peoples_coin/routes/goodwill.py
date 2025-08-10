import http
import logging
from flask import Blueprint, request, jsonify, g, current_app
from peoples_coin.extensions import db
from peoples_coin.utils.auth import require_firebase_token, require_api_key
from peoples_coin.utils.validation import validate_with
from peoples_coin.services.goodwill_service import goodwill_service, GoodwillSubmissionError
from peoples_coin.validate.schemas import GoodwillActionSchema

logger = logging.getLogger(__name__)

goodwill_bp = Blueprint("goodwill", __name__, url_prefix="/api/goodwill")

@goodwill_bp.route("/actions", methods=["POST"])
@require_firebase_token  # User must be authenticated via Firebase
@validate_with(GoodwillActionSchema)  # Validate input with Pydantic schema
def submit_goodwill():
    """
    Accepts a goodwill action from an authenticated user, validates it,
    delegates to the service layer, and returns status.
    """
    try:
        # Combine user ID with validated input data for service
        data = g.validated_data.model_dump() if hasattr(g.validated_data, 'model_dump') else dict(g.validated_data)
        data["user_id"] = g.user.id

        logger.info(f"Received goodwill action submission from user_id={g.user.id}")

        # Call the goodwill service with combined data dict
        result = goodwill_service.submit_and_queue_goodwill_action(data)

        return jsonify({
            "message": "Goodwill action accepted and queued for processing.",
            "action_id": result.get("action_id")
        }), http.HTTPStatus.ACCEPTED

    except GoodwillError as err:
        logger.warning(f"GoodwillError while processing submission: {err}")
        return jsonify({"error": str(err)}), http.HTTPStatus.BAD_REQUEST

    except Exception as err:
        logger.exception(f"Unexpected error in goodwill submission: {err}")
        return jsonify({"error": "Internal server error occurred"}), http.HTTPStatus.INTERNAL_SERVER_ERROR


@goodwill_bp.route("/actions/<string:action_id>/status", methods=["GET"])
@require_firebase_token
def get_goodwill_status(action_id):
    """
    Returns the status of a specific goodwill action for the authenticated user.
    """
    user_id = g.user.id

    try:
        # Query the goodwill service for this action's status
        status = goodwill_service.get_action_status(user_id=user_id, action_id=action_id)
        if status is None:
            return jsonify({"error": "Goodwill action not found"}), http.HTTPStatus.NOT_FOUND

        return jsonify({"status": status}), http.HTTPStatus.OK

    except Exception as err:
        logger.exception(f"Failed to retrieve status for goodwill action {action_id}: {err}")
        return jsonify({"error": "Internal server error occurred"}), http.HTTPStatus.INTERNAL_SERVER_ERROR


@goodwill_bp.route("/summary", methods=["GET"])
@require_api_key  # Require API key for admin/internal use
def goodwill_summary():
    """
    Returns a summary of total goodwill actions and resonance score for a user.
    Expects a 'user_id' query parameter.
    """
    user_id = request.args.get("user_id")
    if not user_id:
        return jsonify({"error": "Missing required user_id parameter"}), http.HTTPStatus.BAD_REQUEST

    try:
        summary = goodwill_service.get_user_summary(user_id)
        return jsonify({
            "user_id": user_id,
            "total_resonance_score": summary.get("total_score", 0),
            "total_actions": summary.get("action_count", 0)
        }), http.HTTPStatus.OK

    except Exception as err:
        logger.exception(f"Failed to retrieve goodwill summary for user_id={user_id}: {err}")
        return jsonify({"error": "Internal server error occurred"}), http.HTTPStatus.INTERNAL_SERVER_ERROR


@goodwill_bp.route("/history", methods=["GET"])
@require_api_key  # Require API key for admin/internal use
def goodwill_history():
    """
    Retrieves paginated goodwill action history for a user.
    Expects 'user_id' query parameter, optional pagination params.
    """
    user_id = request.args.get("user_id")
    if not user_id:
        return jsonify({"error": "Missing required user_id parameter"}), http.HTTPStatus.BAD_REQUEST

    try:
        page = request.args.get('page', default=1, type=int)
        per_page = request.args.get('per_page', default=20, type=int)
        per_page = min(per_page, 100)  # Limit max per page to 100

        paginated_result = goodwill_service.get_user_history(user_id, page=page, per_page=per_page)

        return jsonify(paginated_result), http.HTTPStatus.OK

    except ValueError:
        logger.warning(f"Invalid pagination parameters: page={request.args.get('page')}, per_page={request.args.get('per_page')}")
        return jsonify({"error": "Invalid pagination parameters"}), http.HTTPStatus.BAD_REQUEST

    except Exception as err:
        logger.exception(f"Failed to retrieve goodwill history for user_id={user_id}: {err}")
        return jsonify({"error": "Internal server error occurred"}), http.HTTPStatus.INTERNAL_SERVER_ERROR

