from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from peoples_coin.models import Base, DataEntry
from datetime import datetime

engine = create_engine('sqlite:///instance/peoples_coin.db')
Session = sessionmaker(bind=engine)
session = Session()

# Create a new unprocessed DataEntry
entry = DataEntry(value="Test data", processed=False, created_at=datetime.utcnow(), updated_at=datetime.utcnow())

session.add(entry)
session.commit()
print(f"Inserted DataEntry with id: {entry.id}")

