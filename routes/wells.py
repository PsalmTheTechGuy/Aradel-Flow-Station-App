from flask import Blueprint, request, jsonify, render_template
from extensions import db
from models import Well
from .auth import token_required

wells_bp = Blueprint('wells', __name__)

@wells_bp.route('/api/wells', methods=['GET'])
def get_wells():
    search = request.args.get('search', '').strip()
    query = Well.query
    if search:
        query = query.filter(Well.name.ilike(f'%{search}%'))
    wells = query.all()
    return jsonify([well.to_dict() for well in wells]), 200

@wells_bp.route('/api/wells/<int:id>', methods=['GET'])
def get_well(id):
    well = Well.query.get_or_404(id)
    return jsonify(well.to_dict()), 200

@wells_bp.route('/api/wells', methods=['POST'])
@token_required
def create_well(current_user):
    data = request.get_json()
    if not data or 'name' not in data:
        return jsonify({'error': 'Well name required'}), 400
    if Well.query.filter_by(name=data['name']).first():
        return jsonify({'error': 'Well name exists'}), 400
    well = Well(name=data['name'], location=data.get('location', ''))
    db.session.add(well)
    db.session.commit()
    return jsonify(well.to_dict()), 201

@wells_bp.route('/api/wells/<int:id>', methods=['PUT'])
@token_required
def update_well(current_user, id):
    well = Well.query.get_or_404(id)
    data = request.get_json()
    if 'name' in data:
        well.name = data['name']
    if 'location' in data:
        well.location = data['location']
    db.session.commit()
    return jsonify(well.to_dict()), 200

@wells_bp.route('/api/wells/<int:id>', methods=['DELETE'])
@token_required
def delete_well(current_user, id):
    well = Well.query.get_or_404(id)
    db.session.delete(well)
    db.session.commit()
    return jsonify({'message': 'Well deleted'}), 200