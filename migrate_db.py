from app import app
from models import CrudeExport
from extensions import db

with app.app_context():
    count = CrudeExport.query.filter_by(destination='INTENTAL').update({CrudeExport.destination: 'INTESSA'}, synchronize_session=False)
    db.session.commit()
    print(f"Updated {count} records from INTENTAL to INTESSA")
