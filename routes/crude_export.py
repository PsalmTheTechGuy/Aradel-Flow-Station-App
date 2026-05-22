from flask import Blueprint, request, jsonify, render_template
from extensions import db
from models import CrudeExport
from .auth import token_required
from datetime import datetime, timedelta
from sqlalchemy import func

crude_export_bp = Blueprint('crude_export', __name__)

@crude_export_bp.route('/crude-export')
def dashboard():
    return render_template('crude_export/dashboard.html')

@crude_export_bp.route('/crude-export/entry')
def entry():
    return render_template('crude_export/entry.html')

@crude_export_bp.route('/crude-export/print')
def print_report():
    return render_template('crude_export/print_report.html')

@crude_export_bp.route('/crude-export/manage')
def manage():
    return render_template('crude_export/manage.html')

# --- API ENDPOINTS ---

@crude_export_bp.route('/api/crude-export/list', methods=['GET'])
@token_required
def get_export_list(current_user):
    month = request.args.get('month', datetime.now().month, type=int)
    year = request.args.get('year', datetime.now().year, type=int)
    destination = request.args.get('destination', 'ALL')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    
    query = CrudeExport.query.filter(
        func.extract('month', CrudeExport.date) == month,
        func.extract('year', CrudeExport.date) == year
    )
    
    if destination != 'ALL':
        query = query.filter(CrudeExport.destination == destination)
        
    pagination = query.order_by(CrudeExport.date.desc()).paginate(page=page, per_page=per_page, error_out=False)
    
    response = jsonify({
        'items': [e.to_dict() for e in pagination.items],
        'total': pagination.total,
        'pages': pagination.pages,
        'current_page': pagination.page,
        'per_page': per_page
    })
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    return response, 200

@crude_export_bp.route('/api/crude-export/summary', methods=['GET'])
@token_required
def get_export_summary(current_user):
    month = request.args.get('month', datetime.now().month, type=int)
    year = request.args.get('year', datetime.now().year, type=int)
    
    # Calculate statistics for the month
    exports = CrudeExport.query.filter(
        func.extract('month', CrudeExport.date) == month,
        func.extract('year', CrudeExport.date) == year
    ).all()
    
    total_volume = sum(e.volume for e in exports)
    avg_daily = total_volume / 30 if exports else 0 # Simple avg
    
    dest_totals = {}
    for dest in ['TNP', 'INGENTIA', 'ACE', 'INTESSA', 'REFINERY']:
        dest_totals[dest] = sum(e.volume for e in exports if e.destination == dest)
        
    peak_day = None
    if exports:
        peak_entry = max(exports, key=lambda x: x.volume)
        peak_day = {'date': peak_entry.date.isoformat(), 'volume': peak_entry.volume, 'dest': peak_entry.destination}

    response = jsonify({
        'total_monthly': total_volume,
        'avg_daily': avg_daily,
        'destinations': dest_totals,
        'peak_day': peak_day,
        'count': len(exports)
    })
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    return response, 200

@crude_export_bp.route('/api/crude-export/chart', methods=['GET'])
@token_required
def get_chart_data(current_user):
    month = request.args.get('month', datetime.now().month, type=int)
    year = request.args.get('year', datetime.now().year, type=int)
    
    exports = CrudeExport.query.filter(
        func.extract('month', CrudeExport.date) == month,
        func.extract('year', CrudeExport.date) == year
    ).all()
    
    # Structure for ApexCharts multi-line
    data = {
        'TNP': [0] * 31,
        'INGENTIA': [0] * 31,
        'ACE': [0] * 31,
        'INTESSA': [0] * 31,
        'REFINERY': [0] * 31
    }
    
    for e in exports:
        day = e.date.day
        if day <= 31:
            data[e.destination][day-1] = e.volume
            
    response = jsonify(data)
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    return response, 200

@crude_export_bp.route('/api/crude-export/add', methods=['POST'])
@token_required
def add_export(current_user):
    data = request.get_json()
    try:
        new_export = CrudeExport(
            date=datetime.strptime(data['date'], '%Y-%m-%d').date(),
            destination=data['destination'],
            volume=float(data['volume']),
            remarks=data.get('remarks', '')
        )
        db.session.add(new_export)
        db.session.commit()
        return jsonify(new_export.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400

@crude_export_bp.route('/api/crude-export/<int:id>', methods=['DELETE'])
@token_required
def delete_export(current_user, id):
    item = CrudeExport.query.get_or_404(id)
    db.session.delete(item)
    db.session.commit()
    return jsonify({'message': 'Deleted successfully'}), 200

@crude_export_bp.route('/api/crude-export/<int:id>', methods=['PUT'])
@token_required
def update_export(current_user, id):
    item = CrudeExport.query.get_or_404(id)
    data = request.get_json()
    try:
        item.date = datetime.strptime(data['date'], '%Y-%m-%d').date()
        item.destination = data['destination']
        item.volume = float(data['volume'])
        item.remarks = data.get('remarks', '')
        db.session.commit()
        return jsonify(item.to_dict()), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400

@crude_export_bp.route('/api/crude-export/bulk-delete', methods=['POST'])
@token_required
def bulk_delete_export(current_user):
    data = request.get_json()
    ids = data.get('ids', [])
    if not ids:
        return jsonify({'error': 'No IDs provided'}), 400
    
    try:
        CrudeExport.query.filter(CrudeExport.id.in_(ids)).delete(synchronize_session=False)
        db.session.commit()
        return jsonify({'message': f'Deleted {len(ids)} records'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400
