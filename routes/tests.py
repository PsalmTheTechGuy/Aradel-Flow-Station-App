from flask import Blueprint, request, jsonify, render_template
from extensions import db
from models import WellTest, TestReading, Well
from datetime import datetime
from functools import wraps
from .auth import token_required

tests_bp = Blueprint('tests', __name__)

@tests_bp.route('/api/tests', methods=['POST'])
@token_required
def create_test(current_user):
    data = request.get_json()
    if not data or 'well_id' not in data or 'test_id' not in data or 'date' not in data:
        return jsonify({'error': 'Required fields missing'}), 400
    
    well = Well.query.get(data['well_id'])
    if not well:
        return jsonify({'error': 'Well not found'}), 404
    
    if WellTest.query.filter_by(test_id=data['test_id']).first():
        return jsonify({'error': 'Test ID exists'}), 400
    
    readings = data.get('readings', [])
    gross_rates = [r.get('gross_rate', 0) for r in readings if r.get('gross_rate', 0) > 0]
    # Average BS&W only for flowing hours
    bsw_values = [r.get('bsw', 0) for r in readings if r.get('gross_rate', 0) > 0]
    
    avg_gross_rate = sum(gross_rates) / len(gross_rates) if gross_rates else 0
    avg_bsw = sum(bsw_values) / len(bsw_values) if bsw_values else 0
    net_prod = avg_gross_rate - (avg_bsw / 100 * avg_gross_rate)
    gross_bsw = (avg_bsw / 100) * avg_gross_rate
    
    test = WellTest(
        test_id=data['test_id'],
        well_id=data['well_id'],
        date=datetime.strptime(data['date'], '%Y-%m-%d').date(),
        remarks=data.get('remarks', ''),
        status=data.get('status', 'submitted'),
        avg_gross_rate=avg_gross_rate,
        avg_bsw=avg_bsw,
        net_prod=net_prod,
        gross_bsw=gross_bsw
    )
    db.session.add(test)
    db.session.flush()
    
    if 'readings' in data:
        readings = []
        for r in data['readings']:
            reading = TestReading(
                test_id=test.id,
                time=datetime.strptime(r['time'], '%H:%M:%S').time(),
                bean_size=r.get('bean_size', 0),
                inlet_pressure=r.get('inlet_pressure', 0),
                separator_pressure=r.get('separator_pressure', 0),
                temperature=r.get('temperature', 0),
                liquid_rate=r.get('liquid_rate', 0),
                rate_diff=r.get('rate_diff', 0),
                gross_rate=r.get('gross_rate', 0),
                bsw=r.get('bsw', 0)
            )
            readings.append(reading)
        db.session.add_all(readings)
    
    db.session.commit()
    return jsonify({'message': 'Test created', 'test': test.to_dict()}), 201

@tests_bp.route('/api/tests', methods=['GET'])
def get_tests():
    well_id = request.args.get('well_id', type=int)
    status = request.args.get('status')
    search = request.args.get('search', '').strip()
    query = WellTest.query
    if well_id:
        query = query.filter_by(well_id=well_id)
    if status:
        query = query.filter_by(status=status)
    if search:
        query = query.filter(WellTest.test_id.ilike(f'%{search}%'))
    tests = query.order_by(WellTest.date.desc()).all()
    return jsonify([t.to_dict() for t in tests]), 200

@tests_bp.route('/api/tests/drafts', methods=['GET'])
@token_required
def get_drafts(current_user):
    drafts = WellTest.query.filter_by(status='draft').order_by(WellTest.date.desc()).all()
    return jsonify([t.to_dict() for t in drafts]), 200

@tests_bp.route('/api/tests/drafts', methods=['DELETE'])
@token_required
def delete_all_drafts(current_user):
    WellTest.query.filter_by(status='draft').delete()
    db.session.commit()
    return jsonify({'message': 'All drafts deleted'}), 200

@tests_bp.route('/api/tests/<int:id>', methods=['GET'])
@token_required
def get_test(current_user, id):
    test = WellTest.query.get_or_404(id)
    return jsonify(test.to_dict()), 200

@tests_bp.route('/api/tests/<int:id>', methods=['PUT'])
@token_required
def update_test(current_user, id):
    test = WellTest.query.get_or_404(id)
    data = request.get_json()
    
    if 'well_id' in data:
        test.well_id = data['well_id']
    if 'date' in data:
        test.date = datetime.strptime(data['date'], '%Y-%m-%d').date()
    if 'remarks' in data:
        test.remarks = data['remarks']
    if 'status' in data:
        test.status = data['status']
    
    if 'readings' in data:
        TestReading.query.filter_by(test_id=id).delete()
        for r in data['readings']:
            reading = TestReading(
                test_id=test.id,
                time=datetime.strptime(r['time'], '%H:%M:%S').time(),
                bean_size=r.get('bean_size', 0),
                inlet_pressure=r.get('inlet_pressure', 0),
                separator_pressure=r.get('separator_pressure', 0),
                temperature=r.get('temperature', 0),
                liquid_rate=r.get('liquid_rate', 0),
                rate_diff=r.get('rate_diff', 0),
                gross_rate=r.get('gross_rate', 0),
                bsw=r.get('bsw', 0)
            )
            db.session.add(reading)
        db.session.flush() # Flush to make readings available for summary calculation
    
    # Recalculate summary
    readings = TestReading.query.filter_by(test_id=id).all()
    gross_rates = [r.gross_rate or 0 for r in readings if (r.gross_rate or 0) > 0]
    # Average BS&W only for flowing hours
    bsw_values = [r.bsw or 0 for r in readings if (r.gross_rate or 0) > 0]
    
    test.avg_gross_rate = sum(gross_rates) / len(gross_rates) if gross_rates else 0
    test.avg_bsw = sum(bsw_values) / len(bsw_values) if bsw_values else 0
    test.net_prod = test.avg_gross_rate - (test.avg_bsw / 100 * test.avg_gross_rate)
    test.gross_bsw = (test.avg_bsw / 100) * test.avg_gross_rate
    
    db.session.commit()
    return jsonify(test.to_dict()), 200

@tests_bp.route('/api/tests/<int:id>', methods=['DELETE'])
@token_required
def delete_test(current_user, id):
    test = WellTest.query.get_or_404(id)
    db.session.delete(test)
    db.session.commit()
    return jsonify({'message': 'Test deleted'}), 200

@tests_bp.route('/api/tests/<int:id>/readings', methods=['GET'])
def get_test_readings(id):
    test = WellTest.query.get_or_404(id)
    readings = TestReading.query.filter_by(test_id=id).order_by(TestReading.time).all()
    return jsonify({'test_id': test.test_id, 'readings': [r.to_dict() for r in readings]}), 200

@tests_bp.route('/api/readings', methods=['POST'])
@token_required
def bulk_insert_readings(current_user):
    data = request.get_json()
    if not data or 'test_id' not in data or 'readings' not in data:
        return jsonify({'error': 'Required fields missing'}), 400
    
    test = WellTest.query.get(data['test_id'])
    if not test:
        return jsonify({'error': 'Test not found'}), 404
    
    TestReading.query.filter_by(test_id=data['test_id']).delete()
    
    readings = []
    for r in data['readings']:
        reading = TestReading(
            test_id=data['test_id'],
            time=datetime.strptime(r['time'], '%H:%M:%S').time(),
            bean_size=r.get('bean_size', 0),
            inlet_pressure=r.get('inlet_pressure', 0),
            separator_pressure=r.get('separator_pressure', 0),
            temperature=r.get('temperature', 0),
            liquid_rate=r.get('liquid_rate', 0),
            rate_diff=r.get('rate_diff', 0),
            gross_rate=r.get('gross_rate', 0),
            bsw=r.get('bsw', 0)
        )
        readings.append(reading)
    
    db.session.add_all(readings)
    db.session.commit()
    return jsonify({'message': f'{len(readings)} inserted'}), 201