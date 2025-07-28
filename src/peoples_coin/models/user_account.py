import uuid
from peoples_coin.extensions import db
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.orm import relationship  # make sure this is imported

class UserAccount(db.Model):
    __tablename__ = 'user_accounts'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    firebase_uid = db.Column(db.String(128), unique=True, nullable=False)
    email = db.Column(db.String(256), unique=True, nullable=True)
    username = db.Column(db.String(64), nullable=True)
    balance = db.Column(db.Numeric(20, 4), nullable=False, default=0.0)
    goodwill_coins = db.Column(db.Integer, nullable=False, default=0)
    bio = db.Column(db.Text, nullable=True)
    profile_image_url = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), server_default=db.func.now())
    updated_at = db.Column(db.DateTime(timezone=True), server_default=db.func.now(), onupdate=db.func.now())

    # Password hash column
    password_hash = db.Column(db.Text, nullable=False, default='')

    # Relationships
    user_wallets = relationship("UserWallet", back_populates="user", cascade="all, delete-orphan")

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

