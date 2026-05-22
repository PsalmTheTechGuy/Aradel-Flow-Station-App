from flask import Blueprint, request, jsonify, render_template
from extensions import db
from models import DailyProduction
from .auth import token_required
from datetime import datetime
from sqlalchemy import func

production_bp = Blueprint('production', __name__)

@production_bp.route('/production/entry')
def entry():
    return render_template('crude_export/production_entry.html')

@production_bp.route('/production/print')
def print_report():
    return render_template('crude_export/production_report.html')

@production_bp.route('/production/manage')
def manage():
    return render_template('crude_export/production_manage.html')

# --- API ENDPOINTS ---

@production_bp.route('/api/production/list', methods=['GET'])
@token_required
def get_production_list(current_user):
    month = request.args.get('month', datetime.now().month, type=int)
    year = request.args.get('year', datetime.now().year, type=int)
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    
    query = DailyProduction.query.filter(
        func.extract('month', DailyProduction.date) == month,
        func.extract('year', DailyProduction.date) == year
    )
    
    pagination = query.order_by(DailyProduction.date.desc()).paginate(page=page, per_page=per_page, error_out=False)
    
    return jsonify({
        'items': [p.to_dict() for p in pagination.items],
        'total': pagination.total,
        'pages': pagination.pages,
        'current_page': pagination.page,
        'per_page': per_page
    }), 200

@production_bp.route('/api/production/add', methods=['POST'])
@token_required
def add_production(current_user):
    data = request.get_json()
    try:
        new_prod = DailyProduction(
            date=datetime.strptime(data['date'], '%Y-%m-%d').date(),
            oil_volume=float(data['oil_volume']),
            gas_volume=float(data.get('gas_volume', 0)),
            water_volume=float(data.get('water_volume', 0)),
            remarks=data.get('remarks', '')
        )
        db.session.add(new_prod)
        db.session.commit()
        return jsonify(new_prod.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400

@production_bp.route('/api/production/<int:id>', methods=['DELETE'])
@token_required
def delete_production(current_user, id):
    item = DailyProduction.query.get_or_404(id)
    db.session.delete(item)
    db.session.commit()
    return jsonify({'message': 'Deleted successfully'}), 200

@production_bp.route('/api/production/<int:id>', methods=['PUT'])
@token_required
def update_production(current_user, id):
    item = DailyProduction.query.get_or_404(id)
    data = request.get_json()
    try:
        item.date = datetime.strptime(data['date'], '%Y-%m-%d').date()
        item.oil_volume = float(data['oil_volume'])
        item.gas_volume = float(data.get('gas_volume', 0))
        item.water_volume = float(data.get('water_volume', 0))
        item.remarks = data.get('remarks', '')
        db.session.commit()
        return jsonify(item.to_dict()), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400

@production_bp.route('/api/production/chart', methods=['GET'])
@token_required
def get_production_chart(current_user):
    month = request.args.get('month', datetime.now().month, type=int)
    year = request.args.get('year', datetime.now().year, type=int)
    
    productions = DailyProduction.query.filter(
        func.extract('month', DailyProduction.date) == month,
        func.extract('year', DailyProduction.date) == year
    ).all()
    
    oil_data = [0] * 31
    water_data = [0] * 31
    for p in productions:
        day = p.date.day
        if day <= 31:
            oil_data[day-1] = p.oil_volume
            water_data[day-1] = p.water_volume
            
    return jsonify({
        'oil': oil_data,
        'water': water_data
    }), 200

@production_bp.route('/api/production/bulk-delete', methods=['POST'])
@token_required
def bulk_delete_production(current_user):
    data = request.get_json()
    ids = data.get('ids', [])
    if not ids:
        return jsonify({'error': 'No IDs provided'}), 400
    
    try:
        DailyProduction.query.filter(DailyProduction.id.in_(ids)).delete(synchronize_session=False)
        db.session.commit()
        return jsonify({'message': f'Deleted {len(ids)} records'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400
