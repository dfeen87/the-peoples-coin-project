import os
import requests
from flask import Blueprint, jsonify

monitor_bp = Blueprint('monitor_bp', __name__)

# Define subsystems and their status endpoints
SUBSYSTEMS = {
    "cognitive_system": f"http://localhost:{os.getenv('COGNITIVE_PORT', 5003)}/cognitive/status",
    "skeleton_system": f"http://localhost:{os.getenv('SKELETON_PORT', 5002)}/status",
    "nervous_system": f"http://localhost:{os.getenv('NERVOUS_PORT', 5001)}/status",
    "immune_system": f"http://localhost:{os.getenv('IMMUNE_PORT', 5004)}/status",  # New immune system
    # Future systems can be added here
    # "future_system": f"http://localhost:{os.getenv('FUTURE_PORT', 5005)}/status",
}

@monitor_bp.route("/health", methods=["GET"])
def health_check():
    results = {}
    for name, url in SUBSYSTEMS.items():
        try:
            resp = requests.get(url, timeout=2)
            if resp.status_code == 200:
                try:
                    detail = resp.json()
                except Exception:
                    detail = resp.text
                results[name] = {"status": "ok", "detail": detail}
            else:
                results[name] = {"status": "error", "detail": f"HTTP {resp.status_code}"}
        except Exception as e:
            results[name] = {"status": "unreachable", "detail": str(e)}

    return jsonify(results)

