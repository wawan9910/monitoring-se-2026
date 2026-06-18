"""Run once on first deploy to create tables and load Excel data."""
from app import app, db, BlokSensus, load_excel_data

with app.app_context():
    db.create_all()
    if BlokSensus.query.count() == 0:
        print("Loading data from Excel...")
        load_excel_data()
        print(f"Done! {BlokSensus.query.count()} records loaded.")
    else:
        print(f"Database already has {BlokSensus.query.count()} records.")
