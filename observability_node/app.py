"""
Global Observability Node - Flask Application

A lightweight, read-only REST API that exposes internal system state
without modifying any data or triggering controller actions.

All endpoints are GET-only and designed for safe monitoring.
"""
import os
import logging
from datetime import datetime, timezone
from flask import Flask, jsonify, request
from sqlalchemy import text

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# We'll import these lazily to avoid circular dependencies
db = None
redis_client = None


def create_observability_app(db_uri=None, redis_url=None):
    """
    Create and configure the observability Flask application.
    
    Args:
        db_uri: Database connection string (optional, will use env var if not provided)
        redis_url: Redis connection string (optional)
        
    Returns:
        Flask application instance
    """
    from flask_sqlalchemy import SQLAlchemy
    from flask_redis import FlaskRedis
    from observability_node import __version__
    from observability_node.metrics import (
        get_system_metrics,
        get_redis_queue_depth,
        get_db_activity,
        is_kubernetes_enabled
    )
    
    app = Flask(__name__)
    
    # Configuration
    if not db_uri:
        # Try to detect if running on Google Cloud Run
        if os.environ.get("K_SERVICE"):
            db_user = os.environ.get("DB_USER")
            db_pass = os.environ.get("DB_PASS")
            db_name = os.environ.get("DB_NAME")
            instance_connection_name = os.environ.get("INSTANCE_CONNECTION_NAME")
            db_uri = (
                f"postgresql+pg8000://{db_user}:{db_pass}@/{db_name}"
                f"?unix_sock=/cloudsql/{instance_connection_name}/.s.PGSQL.5432"
            )
        else:
            db_uri = os.environ.get("DATABASE_URL")
    
    app.config.update(
        SQLALCHEMY_DATABASE_URI=db_uri,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        REDIS_URL=redis_url or os.environ.get("CELERY_BROKER_URL"),
        SECRET_KEY=os.environ.get("SECRET_KEY", "observability-secret")
    )
    
    # Initialize extensions
    global db, redis_client
    db = SQLAlchemy()
    db.init_app(app)
    
    redis_client = FlaskRedis()
    redis_client.init_app(app)
    
    # Store startup time for uptime calculation
    app.startup_time = datetime.now(timezone.utc)
    
    # Middleware to reject non-GET requests
    @app.before_request
    def reject_non_get_requests():
        """Reject all non-GET requests with 405 Method Not Allowed."""
        if request.method != 'GET':
            return jsonify({
                "error": "Method Not Allowed",
                "message": "This observability node is read-only. Only GET requests are accepted."
            }), 405
    
    # Endpoint 1: Health check
    @app.route('/health', methods=['GET'])
    def health():
        """
        Health check endpoint.
        
        Returns:
            JSON response with uptime, version, and service liveness
        """
        uptime_seconds = (datetime.now(timezone.utc) - app.startup_time).total_seconds()
        
        return jsonify({
            "status": "ok",
            "service": "Global Observability Node",
            "version": __version__,
            "uptime_seconds": uptime_seconds,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }), 200
    
    # Endpoint 2: System state
    @app.route('/api/system_state', methods=['GET'])
    def system_state():
        """
        System state endpoint.
        
        Returns:
            JSON response with CPU, memory, disk, load averages,
            database activity, Redis queue depth, and Kubernetes status
        """
        with app.app_context():
            # Get system metrics
            metrics = get_system_metrics()
            
            # Get database activity
            try:
                db_metrics = get_db_activity(db.session)
            except Exception as e:
                logger.error(f"Error getting DB activity: {e}")
                db_metrics = {"error": str(e)}
            
            # Get Redis queue depth
            redis_depth = get_redis_queue_depth(redis_client)
            
            # Get Kubernetes status
            k8s_enabled = is_kubernetes_enabled()
            
            # Get last controller evaluation timestamp
            try:
                from peoples_coin.models.controller_action import ControllerAction
                last_controller_action = db.session.query(ControllerAction).order_by(
                    ControllerAction.timestamp.desc()
                ).first()
                
                last_controller_eval = (
                    last_controller_action.timestamp.isoformat()
                    if last_controller_action else None
                )
            except Exception as e:
                logger.error(f"Error getting last controller action: {e}")
                last_controller_eval = None
            
            return jsonify({
                "system_metrics": metrics,
                "database_activity": db_metrics,
                "redis_queue_depth": redis_depth,
                "kubernetes_enabled": k8s_enabled,
                "last_controller_evaluation": last_controller_eval,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }), 200
    
    # Endpoint 3: Controller decisions
    @app.route('/api/controller_decisions', methods=['GET'])
    def controller_decisions():
        """
        Controller decisions endpoint.
        
        Query parameters:
            limit: Number of recent decisions to return (default: 10, max: 100)
        
        Returns:
            JSON response with recent controller decisions
        """
        limit = request.args.get('limit', default=10, type=int)
        limit = min(limit, 100)  # Cap at 100
        
        with app.app_context():
            try:
                from peoples_coin.models.controller_action import ControllerAction
                
                decisions = db.session.query(ControllerAction).order_by(
                    ControllerAction.timestamp.desc()
                ).limit(limit).all()
                
                return jsonify({
                    "count": len(decisions),
                    "limit": limit,
                    "decisions": [decision.to_dict() for decision in decisions],
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }), 200
                
            except Exception as e:
                logger.error(f"Error getting controller decisions: {e}", exc_info=True)
                return jsonify({
                    "error": "Failed to retrieve controller decisions",
                    "details": str(e)
                }), 500
    
    # Endpoint 4: Governance state
    @app.route('/api/governance_state', methods=['GET'])
    def governance_state():
        """
        Governance state endpoint.
        
        Returns:
            JSON response with summary of proposals, votes, and council membership
        """
        with app.app_context():
            try:
                from peoples_coin.models.proposal import Proposal
                from peoples_coin.models.vote import Vote
                from peoples_coin.models.council_member import CouncilMember
                
                # Count proposals by status
                proposal_counts = {}
                for status in ['DRAFT', 'ACTIVE', 'CLOSED', 'REJECTED']:
                    count = db.session.query(Proposal).filter(
                        Proposal.status == status
                    ).count()
                    proposal_counts[status.lower()] = count
                
                # Count total votes
                total_votes = db.session.query(Vote).count()
                
                # Count active council members
                active_council_members = db.session.query(CouncilMember).filter(
                    CouncilMember.end_date.is_(None)
                ).count()
                
                # Get recent proposals (last 5)
                recent_proposals = db.session.query(Proposal).order_by(
                    Proposal.created_at.desc()
                ).limit(5).all()
                
                return jsonify({
                    "proposal_summary": {
                        "total": sum(proposal_counts.values()),
                        "by_status": proposal_counts
                    },
                    "vote_summary": {
                        "total_votes": total_votes
                    },
                    "council_summary": {
                        "active_members": active_council_members
                    },
                    "recent_proposals": [
                        {
                            "id": str(p.id),
                            "title": p.title,
                            "status": p.status,
                            "created_at": p.created_at.isoformat() if p.created_at else None
                        }
                        for p in recent_proposals
                    ],
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }), 200
                
            except Exception as e:
                logger.error(f"Error getting governance state: {e}", exc_info=True)
                return jsonify({
                    "error": "Failed to retrieve governance state",
                    "details": str(e)
                }), 500
    
    # Endpoint 5: Audit summary
    @app.route('/api/audit_summary', methods=['GET'])
    def audit_summary():
        """
        Audit summary endpoint.
        
        Query parameters:
            limit: Number of recent audit entries to return (default: 10, max: 100)
        
        Returns:
            JSON response with recent audit log entries
        """
        limit = request.args.get('limit', default=10, type=int)
        limit = min(limit, 100)  # Cap at 100
        
        with app.app_context():
            try:
                from peoples_coin.models.audit_log import AuditLog
                
                audit_entries = db.session.query(AuditLog).order_by(
                    AuditLog.created_at.desc()
                ).limit(limit).all()
                
                return jsonify({
                    "count": len(audit_entries),
                    "limit": limit,
                    "audit_entries": [entry.to_dict() for entry in audit_entries],
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }), 200
                
            except Exception as e:
                logger.error(f"Error getting audit summary: {e}", exc_info=True)
                return jsonify({
                    "error": "Failed to retrieve audit summary",
                    "details": str(e)
                }), 500
    
    logger.info("✅ Global Observability Node created successfully!")
    return app


if __name__ == '__main__':
    # For standalone execution
    app = create_observability_app()
    port = int(os.environ.get('OBSERVABILITY_PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
