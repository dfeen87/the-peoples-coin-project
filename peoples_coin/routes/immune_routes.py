from flask import Blueprint, jsonify, request
import immune_system  # assuming immune_system.py is in your PYTHONPATH or package

immune_bp = Blueprint("immune_bp", __name__, url_prefix="/immune")


@immune_bp.route("/health", methods=["GET"])
def health_check():
    """
    Return immune system health & stats.
    """
    stats = {
        "redis_enabled": immune_system.redis_enabled,
        "blacklist_count": len(immune_system.get_blacklist()),
    }
    return jsonify({"status": "ok", "immune_system": stats}), 200


@immune_bp.route("/blacklist", methods=["GET"])
def get_blacklist():
    """
    Retrieve current blacklist.
    """
    bl = immune_system.get_blacklist()
    return jsonify({"status": "ok", "blacklist": bl, "count": len(bl)}), 200


@immune_bp.route("/blacklist/reset", methods=["POST"])
def reset_blacklist():
    """
    Reset the immune system state (blacklist, greylist, ratelimits).
    """
    immune_system.reset_immune_system()
    return jsonify({"status": "reset", "message": "Immune system state reset."}), 200


@immune_bp.route("/blacklist/remove", methods=["POST"])
def remove_from_blacklist():
    """
    Remove an identifier from the blacklist.
    """
    data = request.get_json(silent=True) or {}
    identifier = data.get("identifier")

    if not identifier:
        return jsonify({"status": "error", "error": "Missing 'identifier'"}), 400

    removed = False
    if immune_system.redis_enabled:
        removed = bool(immune_system._redis.srem("blacklist", identifier))
    else:
        with immune_system._lock:
            if identifier in immune_system._blacklist:
                immune_system._blacklist.remove(identifier)
                removed = True

    if removed:
        return jsonify({"status": "ok", "message": f"Identifier '{identifier}' removed from blacklist."}), 200
    else:
        return jsonify({"status": "not_found", "message": f"Identifier '{identifier}' was not in blacklist."}), 404


@immune_bp.route("/auto-heal", methods=["POST"])
def auto_heal():
    """
    Trigger auto-heal on submitted data entries (placeholder).
    """
    data = request.get_json(silent=True) or []
    if not isinstance(data, list):
        return jsonify({"status": "error", "error": "Expected a JSON array of data entries"}), 400

    healed_count = immune_system.auto_heal_entries(data)

    return jsonify({
        "status": "ok",
        "message": "Auto-heal completed.",
        "healed_entries": healed_count,
        "submitted_entries": len(data)
    }), 200
<<<<<<< HEAD

=======
>>>>>>> 36760cc (Initial commit of local project to new repository)
