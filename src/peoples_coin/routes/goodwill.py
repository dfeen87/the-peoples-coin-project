import http
from flask import Blueprint, request, jsonify, g
from sqlalchemy import func

# Use our established patterns
from peoples_coin.extensions import db
from peoples_coin.utils.auth import require_firebase_token, require_api_key
from peoples_coin.utils.validation import validate_with
from peoples_coin.services.goodwill_service import goodwill_service, GoodwillError

# Pydantic schema for input validation
from peoples_coin.validate.schemas import GoodwillActionSchema

goodwill_bp = Blueprint("goodwill", __name__, url_prefix="/api/goodwill")

@goodwill_bp.route("/actions", methods=["POST"])
@require_firebase_token # Secure with user authentication
@validate_with(GoodwillActionSchema)
def submit_goodwill():
    """
    Accepts a goodwill action, validates it, and delegates to the service layer for processing.
    """
    action_data: GoodwillActionSchema = g.validated_data
    
    # The decorator provides g.user, ensuring the action is submitted by the authenticated user.
    # The service layer will handle the validation and creation logic.
    try:
        result = goodwill_service.submit_action(
            user_id=g.user.id,
            action_data=action_data.model_dump()
        )
        return jsonify({
            "message": "Goodwill action accepted and queued for processing.",
            "action_id": result.get("action_id")
        }), http.HTTPStatus.ACCEPTED
    except GoodwillError as e:
        return jsonify({"error": str(e)}), http.HTTPStatus.BAD_REQUEST
    except Exception as e:
        # Log the full exception
        current_app.logger.exception(f"Unexpected error in submit_goodwill: {e}")
        return jsonify({"error": "An internal server error occurred"}), http.HTTPStatus.INTERNAL_SERVER_ERROR

@goodwill_bp.route("/summary", methods=["GET"])
@require_api_key # Use API key for internal/admin data retrieval
def goodwill_summary():
    """Retrieves a summary of a user's goodwill actions."""
    user_id = request.args.get("user_id")
    if not user_id:
        return jsonify({"error": "Missing user_id parameter"}), http.HTTPStatus.BAD_REQUEST

    # The service layer will contain the optimized query
    summary = goodwill_service.get_user_summary(user_id)
    
    return jsonify({
        "user_id": user_id,
        "total_resonance_score": summary.get("total_score"),
        "total_actions": summary.get("action_count")
    }), http.HTTPStatus.OK

@goodwill_bp.route("/history", methods=["GET"])
@require_api_key # Use API key for internal/admin data retrieval
def goodwill_history():
    """Retrieves a paginated history of a user's goodwill actions."""
    user_id = request.args.get("user_id")
    if not user_id:
        return jsonify({"error": "Missing user_id parameter"}), http.HTTPStatus.BAD_REQUEST

    try:
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 20, type=int), 100) # Enforce a max page size
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid pagination parameters"}), http.HTTPStatus.BAD_REQUEST

    # The service layer handles pagination and serialization
    paginated_result = goodwill_service.get_user_history(
        user_id=user_id,
        page=page,
        per_page=per_page
    )

    return jsonify(paginated_result), http.HTTPStatus.OK
