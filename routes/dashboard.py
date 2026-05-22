from flask import Blueprint, request, jsonify, render_template
from extensions import db
from models import WellTest, TestReading, Well
from datetime import datetime

dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route('/')
def index():
    # Render dashboard directly - auth check moved to client-side only for the navbar
    wells = Well.query.all()
    tests = WellTest.query.order_by(WellTest.date.desc()).limit(10).all()
    
    well_data_list = [{'id': w.id, 'name': w.name} for w in wells]
    
    test_data_list = []
    for t in tests:
        # Use stored values which already follow the "flowing hour" logic
        test_data_list.append({
            'id': t.id, 
            'test_id': t.test_id,
            'well_name': t.well.name, 
            'date': str(t.date),
            'gross': t.avg_gross_rate or 0, 
            'net': t.net_prod or 0, 
            'avg_bsw': t.avg_bsw or 0
        })
    
    latest_gross = test_data_list[0]['gross'] if test_data_list else 0
    avg_bsw = test_data_list[0]['avg_bsw'] if test_data_list else 0
    
    return render_template('dashboard.html', 
        wells=well_data_list, test_data=test_data_list, 
        latest_gross_production=latest_gross, avg_bsw=round(avg_bsw, 2))

@dashboard_bp.route('/tests')
def list_tests():
    well_id = request.args.get('well_id', type=int)
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    search = request.args.get('search', '').strip()
    
    query = WellTest.query
    if well_id:
        query = query.filter_by(well_id=well_id)
    if start_date:
        query = query.filter(WellTest.date >= datetime.strptime(start_date, '%Y-%m-%d').date())
    if end_date:
        query = query.filter(WellTest.date <= datetime.strptime(end_date, '%Y-%m-%d').date())
    if search:
        query = query.filter(WellTest.test_id.ilike(f'%{search}%'))
    
    tests = query.order_by(WellTest.date.desc()).all()
    wells = Well.query.all()
    
    test_data = []
    for t in tests:
        # Use stored values for consistency
        test_data.append({
            'id': t.id, 
            'test_id': t.test_id, 
            'well_name': t.well.name,
            'date': str(t.date), 
            'well_id': t.well_id, 
            'gross': t.avg_gross_rate or 0, 
            'net': t.net_prod or 0,
            'avg_bsw': t.avg_bsw or 0, 
            'readings_count': TestReading.query.filter_by(test_id=t.id).count()
        })
    
    return render_template('tests_list.html', 
        tests=test_data, wells=wells, selected_well_id=well_id, 
        start_date=start_date, end_date=end_date, search=search)

@dashboard_bp.route('/test/<int:id>')
def view_test(id):
    test = WellTest.query.get_or_404(id)
    readings = TestReading.query.filter_by(test_id=id).order_by(TestReading.time).all()
    readings_data = [{
        'id': r.id, 'time': str(r.time), 'bean_size': r.bean_size,
        'inlet_pressure': r.inlet_pressure, 'separator_pressure': r.separator_pressure,
        'temperature': r.temperature, 'liquid_rate': r.liquid_rate,
        'rate_diff': r.rate_diff, 'gross_rate': r.gross_rate,
        'bsw': r.bsw, 'net_production': r.net_production
    } for r in readings]
    return render_template('test_detail.html', test=test, readings_data=readings_data)

@dashboard_bp.route('/new-test')
def new_test():
    wells = Well.query.all()
    return render_template('new_test.html', wells=[{'id': w.id, 'name': w.name} for w in wells])

@dashboard_bp.route('/wells')
def list_wells():
    wells = Well.query.all()
    wells_data = []
    for w in wells:
        tests = WellTest.query.filter_by(well_id=w.id).all()
        wells_data.append({
            'id': w.id, 'name': w.name, 'location': w.location, 
            'test_count': len(tests), 'last_test': tests[0].date.isoformat() if tests else None
        })
    return render_template('wells_list.html', wells_data=wells_data)

@dashboard_bp.route('/wells/new')
def new_well():
    return render_template('new_well.html')

@dashboard_bp.route('/login')
def login_page():
    return render_template('login.html')

@dashboard_bp.route('/logout')
def logout():
    return render_template('login.html')

@dashboard_bp.route('/analytics')
def analytics():
    wells = Well.query.all()
    return render_template('analytics.html', wells=[{'id': w.id, 'name': w.name} for w in wells])

@dashboard_bp.route('/analytics/well/<int:well_id>/history')
def well_history(well_id):
    well = Well.query.get_or_404(well_id)
    return render_template('well_history.html', well=well)