import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# ⚠️ Remember to change this password later if you push this to a public GitHub!
load_dotenv()

# Grab the database URL securely
DATABASE_URL = os.getenv("DATABASE_URL")

print("🔗 Attempting to connect to the NEW database...")

# 🚀 THE FIX: Added pool_pre_ping=True right here!
engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=300)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()