# peoples_coin/db_types.py

from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy import JSON as SA_JSON, String
from sqlalchemy.types import Enum as SA_Enum

# JSON handling — PostgreSQL JSONB if available, fallback to generic JSON
JSONType = SA_JSON().with_variant(JSONB, "postgresql")

# UUID handling — PostgreSQL UUID if available, fallback to String
UUIDType = PG_UUID(as_uuid=True).with_variant(String(36), "sqlite")

# Enum handling — SQLAlchemy Enum type (works for all backends)
EnumType = SA_Enum

__all__ = ["JSONType", "UUIDType", "EnumType"]

