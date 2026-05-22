from flask import Blueprint, request, jsonify
from extensions import db
from models import WellTest, TestReading, Well
from datetime import datetime, timedelta
from sqlalchemy import func, desc
import numpy as np

analytics_bp = Blueprint('analytics', __name__)

def get_test_filter(period, start_date=None, end_date=None, well_id=None):
    """Build query filter based on time period"""
    query = WellTest.query
    
    if well_id:
        query = query.filter(WellTest.well_id == well_id)
    
    now = datetime.now().date()
    
    if period == 'all':
        pass
    elif period == 'last5':
        pass
    elif period == 'last3m':
        query = query.filter(WellTest.date >= (now - timedelta(days=90)))
    elif period == 'last6m':
        query = query.filter(WellTest.date >= (now - timedelta(days=180)))
    elif period == 'last12m':
        query = query.filter(WellTest.date >= (now - timedelta(days=365)))
    elif period == 'last24m':
        query = query.filter(WellTest.date >= (now - timedelta(days=730)))
    elif period == 'custom' and start_date and end_date:
        query = query.filter(
            WellTest.date >= datetime.strptime(start_date, '%Y-%m-%d').date(),
            WellTest.date <= datetime.strptime(end_date, '%Y-%m-%d').date()
        )
    
    return query

def calculate_trend(values):
    """Calculate trend direction: 1=up, -1=down, 0=stable"""
    if len(values) < 2:
        return 0
    
    recent = values[0] if values else 0
    older = values[-1] if values else 0
    
    if older == 0:
        return 0
    
    change_pct = ((recent - older) / older) * 100
    
    if change_pct > 5:
        return 1  # trending up
    elif change_pct < -5:
        return -1  # trending down
    else:
        return 0  # stable

def fit_decline_curve(dates, rates):
    """Fit simple decline curve - exponential decline"""
    if len(dates) < 2:
        return None
    
    try:
        x = np.array([(d - dates[0]).days for d in dates], dtype=float)
        y = np.array(rates, dtype=float)
        
        if any(y <= 0):
            return None
        
        log_y = np.log(y)
        
        coeffs = np.polyfit(x, log_y, 1)
        decline_rate = -coeffs[0]
        initial_rate = np.exp(coeffs[1])
        
        return {
            'initial_rate': float(initial_rate),
            'decline_rate': float(decline_rate),
            'half_life': float(np.log(2) / decline_rate) if decline_rate > 0 else None
        }
    except:
        return None

@analytics_bp.route('/api/analytics/summary')
def get_summary():
    """Overall system summary"""
    total_wells = Well.query.count()
    total_tests = WellTest.query.count()
    active_wells = Well.query.filter(Well.tests.any()).count()
    
    latest_tests = db.session.query(
        WellTest.well_id,
        func.max(WellTest.date).label('last_test')
    ).group_by(WellTest.well_id).subquery()
    
    recent_wells = db.session.query(Well).join(
        latest_tests, Well.id == latest_tests.c.well_id
    ).filter(
        latest_tests.c.last_test >= (datetime.now().date() - timedelta(days=90))
    ).count()
    
    return jsonify({
        'total_wells': total_wells,
        'active_wells': active_wells,
        'wells_needing_test': total_wells - recent_wells,
        'total_tests': total_tests,
        'avg_tests_per_well': round(total_tests / total_wells, 1) if total_wells > 0 else 0
    })

@analytics_bp.route('/api/analytics/wells/performance')
def get_wells_performance():
    """Well performance data with trends"""
    period = request.args.get('period', 'all')
    well_id = request.args.get('well_id', type=int)
    
    wells = Well.query.all()
    performance = []
    
    for well in wells:
        # Get ALL tests for this well to find the absolute most recent one
        all_tests = WellTest.query.filter_by(well_id=well.id).order_by(WellTest.date.desc()).all()
        
        if not all_tests:
            continue
            
        # The absolute source of truth for "current" data is the latest test
        latest_test = all_tests[0]
        
        # Apply period filtering only for trend/historical aggregation
        filtered_tests = all_tests
        if period == 'last5':
            filtered_tests = all_tests[:5]
        elif period == 'last3m':
            cutoff = datetime.now().date() - timedelta(days=90)
            filtered_tests = [t for t in all_tests if t.date >= cutoff]
        elif period == 'last12m':
            cutoff = datetime.now().date() - timedelta(days=365)
            filtered_tests = [t for t in all_tests if t.date >= cutoff]
        
        # Collect rates from filtered tests for trend calculation
        gross_rates = [t.avg_gross_rate for t in filtered_tests if t.avg_gross_rate]
        bsws = [t.avg_bsw for t in filtered_tests if t.avg_bsw is not None]
        
        performance.append({
            'well_id': well.id,
            'well_name': well.name,
            'location': well.location,
            'last_test_date': latest_test.date.isoformat(),
            'test_count': len(all_tests),
            'current_gross_rate': round(latest_test.avg_gross_rate or 0, 3),
            'avg_gross_rate': round(sum(gross_rates) / len(gross_rates), 3) if gross_rates else 0,
            'gross_trend': calculate_trend(gross_rates),
            'current_bsw': round(latest_test.avg_bsw or 0, 2),
            'avg_bsw': round(sum(bsws) / len(bsws), 2) if bsws else 0,
            'bsw_trend': calculate_trend(bsws),
            'net_prod': round(latest_test.net_prod or 0, 3),
            'gross_bsw': round(latest_test.gross_bsw or 0, 3)
        })
    
    performance.sort(key=lambda x: x['last_test_date'] or '', reverse=True)
    return jsonify(performance)

@analytics_bp.route('/api/analytics/well/<int:well_id>/history')
def get_well_history(well_id):
    """Get test history for a specific well"""
    well = Well.query.get_or_404(well_id)
    tests = WellTest.query.filter_by(well_id=well_id).order_by(WellTest.date.asc()).all()
    
    history = []
    rates = []
    dates = []
    bsws = []
    
    for t in tests:
        history.append({
            'test_id': t.test_id,
            'date': t.date.isoformat(),
            'avg_gross_rate': t.avg_gross_rate or 0,
            'avg_bsw': t.avg_bsw or 0,
            'net_prod': t.net_prod or 0,
            'gross_bsw': t.gross_bsw or 0
        })
        if t.avg_gross_rate:
            rates.append(t.avg_gross_rate)
            dates.append(t.date)
        if t.avg_bsw is not None:
            bsws.append(t.avg_bsw)
    
    decline = fit_decline_curve(dates, rates) if len(rates) >= 2 else None
    
    return jsonify({
        'well': {'id': well.id, 'name': well.name, 'location': well.location},
        'history': history,
        'decline_analysis': decline
    })

@analytics_bp.route('/api/analytics/alerts')
def get_alerts():
    """Generate alerts based on thresholds"""
    bsw_threshold = request.args.get('bsw_threshold', 50, type=float)
    pressure_threshold = request.args.get('pressure_threshold', 200, type=float)
    decline_threshold = request.args.get('decline_threshold', 20, type=float)
    days_threshold = request.args.get('days_threshold', 90, type=int)
    
    alerts = []
    now = datetime.now().date()
    
    wells = Well.query.all()
    for well in wells:
        tests = WellTest.query.filter_by(well_id=well.id).order_by(WellTest.date.desc()).all()
        
        if not tests:
            alerts.append({
                'type': 'no_tests',
                'severity': 'warning',
                'well_id': well.id,
                'well_name': well.name,
                'message': f'{well.name} has no test data'
            })
            continue
        
        latest = tests[0]
        days_since_test = (now - latest.date).days
        
        if days_since_test > days_threshold:
            alerts.append({
                'type': 'overdue',
                'severity': 'warning',
                'well_id': well.id,
                'well_name': well.name,
                'message': f'{well.name} has not been tested in {days_since_test} days',
                'days_since_test': days_since_test
            })
        
        if latest.avg_bsw and latest.avg_bsw > bsw_threshold:
            alerts.append({
                'type': 'high_bsw',
                'severity': 'critical' if latest.avg_bsw > 70 else 'warning',
                'well_id': well.id,
                'well_name': well.name,
                'message': f'{well.name} has high water cut: {latest.avg_bsw}%',
                'value': latest.avg_bsw
            })
        
        if len(tests) >= 2:
            prev_gross = tests[1].avg_gross_rate or 0
            curr_gross = latest.avg_gross_rate or 0
            
            if prev_gross > 0:
                decline_pct = ((prev_gross - curr_gross) / prev_gross) * 100
                
                if decline_pct > decline_threshold:
                    alerts.append({
                        'type': 'production_drop',
                        'severity': 'warning',
                        'well_id': well.id,
                        'well_name': well.name,
                        'message': f'{well.name} production dropped {decline_pct:.1f}%',
                        'value': round(decline_pct, 1),
                        'prev_rate': prev_gross,
                        'curr_rate': curr_gross
                    })
    
    alerts.sort(key=lambda x: {'critical': 0, 'warning': 1, 'info': 2}.get(x['severity'], 3))
    
    return jsonify({
        'alerts': alerts,
        'summary': {
            'total': len(alerts),
            'critical': len([a for a in alerts if a['severity'] == 'critical']),
            'warning': len([a for a in alerts if a['severity'] == 'warning'])
        }
    })

@analytics_bp.route('/api/analytics/comparison')
def get_comparison():
    """Compare multiple wells"""
    well_ids = request.args.getlist('well_ids', type=int)
    
    if not well_ids:
        wells = Well.query.limit(5).all()
        well_ids = [w.id for w in wells]
    
    comparison = []
    
    for well_id in well_ids:
        well = Well.query.get(well_id)
        if not well:
            continue
            
        tests = WellTest.query.filter_by(well_id=well_id).order_by(WellTest.date.desc()).limit(3).all()
        
        if not tests:
            continue
        
        # Use the stored values for the latest test (tests[0] is the most recent)
        latest_test = tests[0]
        latest_gross = latest_test.avg_gross_rate or 0
        latest_bsw = latest_test.avg_bsw or 0
        latest_net = latest_test.net_prod or 0
        
        # Historical averages for this well (using the up to 3 tests loaded)
        avg_gross = sum(t.avg_gross_rate or 0 for t in tests) / len(tests)
        avg_bsw = sum(t.avg_bsw or 0 for t in tests) / len(tests)
        
        comparison.append({
            'well_id': well.id,
            'well_name': well.name,
            'latest_gross': round(latest_gross, 3),
            'avg_gross': round(avg_gross, 3),
            'avg_bsw': round(latest_bsw, 2),
            'net_prod': round(latest_net, 3)
        })
    
    comparison.sort(key=lambda x: x['latest_gross'], reverse=True)
    
    return jsonify(comparison)

@analytics_bp.route('/api/analytics/decline/<int:well_id>')
def get_decline_analysis(well_id):
    """Detailed decline curve analysis"""
    well = Well.query.get_or_404(well_id)
    tests = WellTest.query.filter_by(well_id=well_id).order_by(WellTest.date.asc()).all()
    
    if len(tests) < 2:
        return jsonify({'error': 'Need at least 2 tests for decline analysis'}), 400
    
    rates = []
    dates = []
    bsws = []
    
    for t in tests:
        avg_rate = t.avg_gross_rate or 0
        avg_bsw = t.avg_bsw or 0
        
        if avg_rate > 0:
            rates.append(avg_rate)
            dates.append(t.date)
        
        if avg_bsw > 0:
            bsws.append(avg_bsw)
    
    decline = fit_decline_curve(dates, rates) if len(rates) >= 2 else None
    
    projected = []
    if decline:
        for i in range(1, 13):
            future_date = dates[-1] + timedelta(days=30 * i)
            days = (future_date - dates[0]).days
            projected_rate = decline['initial_rate'] * np.exp(-decline['decline_rate'] * days)
            projected.append({
                'date': future_date.isoformat(),
                'rate': float(projected_rate)
            })
    
    return jsonify({
        'well': {'id': well.id, 'name': well.name},
        'data_points': [{'date': d.isoformat(), 'rate': r} for d, r in zip(dates, rates)],
        'decline_parameters': decline,
        'projected_production': projected
    })

@analytics_bp.route('/api/analytics/trends')
def get_trends():
    """Overall production trends"""
    tests = WellTest.query.order_by(WellTest.date.desc()).limit(100).all()
    
    monthly = {}
    for t in tests:
        month = t.date.strftime('%Y-%m')
        if month not in monthly:
            monthly[month] = {'gross': [], 'bsw': [], 'net': [], 'count': 0}
        
        avg_gross = t.avg_gross_rate or 0
        avg_bsw = t.avg_bsw or 0
        net_prod = t.net_prod or 0
        
        if avg_gross > 0:
            monthly[month]['gross'].append(avg_gross)
            monthly[month]['bsw'].append(avg_bsw)
            monthly[month]['net'].append(net_prod)
        
        monthly[month]['count'] += 1
    
    result = []
    for month in sorted(monthly.keys(), reverse=True)[:24]:
        data = monthly[month]
        result.append({
            'month': month,
            'avg_gross_rate': round(sum(data['gross']) / len(data['gross']), 3) if data['gross'] else 0,
            'avg_bsw': round(sum(data['bsw']) / len(data['bsw']), 2) if data['bsw'] else 0,
            'avg_net_prod': round(sum(data['net']) / len(data['net']), 3) if data['net'] else 0,
            'test_count': data['count']
        })
    
    return jsonify(result)

@analytics_bp.route('/api/analytics/export/report')
def export_report():
    """Generate comprehensive report data"""
    period = request.args.get('period', 'last12m')
    well_ids = request.args.getlist('well_ids', type=int)
    
    wells = Well.query.all() if not well_ids else Well.query.filter(Well.id.in_(well_ids)).all()
    
    report = []
    for well in wells:
        tests = WellTest.query.filter_by(well_id=well.id).order_by(WellTest.date.desc()).all()
        
        if period == 'last5':
            tests = tests[:5]
        elif period == 'last3m':
            cutoff = datetime.now().date() - timedelta(days=90)
            tests = [t for t in tests if t.date >= cutoff]
        elif period == 'last12m':
            cutoff = datetime.now().date() - timedelta(days=365)
            tests = [t for t in tests if t.date >= cutoff]
        
        if not tests:
            continue
        
        report.append({
            'well_name': well.name,
            'location': well.location,
            'total_tests': len(tests),
            'latest_test': tests[0].date.isoformat(),
            'current_production': round(tests[0].avg_gross_rate or 0, 3),
            'avg_production': round(sum(t.avg_gross_rate or 0 for t in tests) / len(tests), 3),
            'avg_bsw': round(sum(t.avg_bsw or 0 for t in tests) / len(tests), 2),
            'net_prod': round(tests[0].net_prod or 0, 3),
            'trend': calculate_trend([t.avg_gross_rate for t in tests if t.avg_gross_rate])
        })
    
    return jsonify(report)