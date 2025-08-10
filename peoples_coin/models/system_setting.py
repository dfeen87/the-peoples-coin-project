# peoples_coin/models/system_setting.py

from sqlalchemy import (
    Column, String, Text, DateTime, func
)
from sqlalchemy.dialects.postgresql import JSONB
from peoples_coin.extensions import db

class SystemSetting(db.Model):
    __tablename__ = "system_settings"

    key = Column(String(100), primary_key=True)
    value = Column(JSONB, nullable=False)
    description = Column(Text, nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    def to_dict(self):
        """Serializes the SystemSetting object to a dictionary."""
        return {
            "key": self.key,
            "value": self.value,
            "description": self.description,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
