from flask import Blueprint, request, jsonify, render_template, session
from extensions import db
from models import Well, WellTest, TestReading
from datetime import datetime
import csv
import io

data_bp = Blueprint('data', __name__)

def require_auth(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('user_id'):
            from flask import redirect, url_for
            return redirect(url_for('dashboard.login'))
        return f(*args, **kwargs)
    return decorated

@data_bp.route('/import', methods=['GET', 'POST'])
@require_auth
def import_data():
    if request.method == 'GET':
        wells = Well.query.all()
        return render_template('import.html', wells=wells)
    
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not file.filename.endswith('.csv'):
        return jsonify({'error': 'File must be CSV format'}), 400
    
    try:
        content = file.read().decode('utf-8')
        reader = csv.DictReader(io.StringIO(content))
        
        imported = 0
        for row in reader:
            well_name = row.get('well', '').strip()
            test_date = row.get('date', '').strip()
            
            if not well_name or not test_date:
                continue
            
            well = Well.query.filter_by(name=well_name).first()
            if not well:
                well = Well(name=well_name)
                db.session.add(well)
                db.session.flush()
            
            test_id = f"TEST-{datetime.now().strftime('%Y%m%d')}-{imported+1:03d}"
            test = WellTest(
                test_id=test_id,
                well_id=well.id,
                date=datetime.strptime(test_date, '%Y-%m-%d').date(),
                remarks=row.get('remarks', '')
            )
            db.session.add(test)
            db.session.flush()
            
            reading = TestReading(
                test_id=test.id,
                time=datetime.strptime(row.get('time', '10:00:00'), '%H:%M:%S').time(),
                bean_size=float(row.get('bean_size', 20)),
                inlet_pressure=float(row.get('inlet_pressure', 500)),
                separator_pressure=float(row.get('separator_pressure', 200)),
                temperature=float(row.get('temperature', 150)),
                liquid_rate=float(row.get('liquid_rate', 100)),
                rate_diff=float(row.get('rate_diff', 10)),
                gross_rate=float(row.get('gross_rate', 90)),
                bsw=float(row.get('bsw', 30))
            )
            db.session.add(reading)
            imported += 1
        
        db.session.commit()
        return jsonify({'message': f'Successfully imported {imported} records'}), 200
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500