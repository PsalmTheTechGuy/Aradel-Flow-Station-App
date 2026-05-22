import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask
from extensions import db
import datetime

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///well_test.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'connect_args': {'check_same_thread': False}}

db.init_app(app)

with app.app_context():
    conn = db.engine.connect()
    
    # Add columns if they don't exist
    try:
        conn.execute(db.text('ALTER TABLE well_tests ADD COLUMN avg_gross_rate FLOAT'))
        print("Added avg_gross_rate column")
    except Exception as e:
        print(f"avg_gross_rate: {e}")
    
    try:
        conn.execute(db.text('ALTER TABLE well_tests ADD COLUMN avg_bsw FLOAT'))
        print("Added avg_bsw column")
    except Exception as e:
        print(f"avg_bsw: {e}")
    
    try:
        conn.execute(db.text('ALTER TABLE well_tests ADD COLUMN net_prod FLOAT'))
        print("Added net_prod column")
    except Exception as e:
        print(f"net_prod: {e}")
    
    try:
        conn.execute(db.text('ALTER TABLE well_tests ADD COLUMN gross_bsw FLOAT'))
        print("Added gross_bsw column")
    except Exception as e:
        print(f"gross_bsw: {e}")

    try:
        conn.execute(db.text("ALTER TABLE well_tests ADD COLUMN status VARCHAR(20) DEFAULT 'submitted'"))
        print("Added status column")
    except Exception as e:
        print(f"status: {e}")
    
    conn.commit()
    print("\nMigration completed!")