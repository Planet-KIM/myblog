#!/usr/bin/env python3
"""
Database migration script to add new tables for blog features
"""

from app.database import engine, Base
from app import models

def migrate():
    """Create new tables if they don't exist"""
    print("Starting database migration...")

    # Create all tables (will skip existing ones)
    Base.metadata.create_all(bind=engine)

    print("✅ Migration completed successfully!")
    print("New tables created (if not existed):")
    print("  - tags")
    print("  - post_tags")
    print("  - post_stats")
    print("  - drafts")

if __name__ == "__main__":
    migrate()