from peoples_coin.run import create_app
from peoples_coin.extensions import db
from peoples_coin.db.models import GoodwillAction

app = create_app()

with app.app_context():
    actions = db.session.query(GoodwillAction).all()
    if not actions:
        print("❌ No GoodwillAction records found.")
    else:
        for a in actions:
            print(
                f"✅ ID: {a.id} | User: {a.user_id} | Type: {a.action_type} | "
                f"Description: {a.description} | Status: {a.status} | Timestamp: {a.timestamp}"
            )

