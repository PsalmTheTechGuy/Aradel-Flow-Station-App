from flask import Blueprint, request, jsonify, make_response, render_template, session
from extensions import db
from models import WellTest, TestReading, Well
import pandas as pd
import io
from datetime import datetime

export_bp = Blueprint('export', __name__)

def require_auth(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('user_id'):
            from flask import redirect, url_for
            return redirect(url_for('dashboard.login'))
        return f(*args, **kwargs)
    return decorated

@export_bp.route('/api/export/csv/<int:test_id>', methods=['GET'])
def export_csv(test_id):
    test = WellTest.query.get_or_404(test_id)
    readings = TestReading.query.filter_by(test_id=test_id).order_by(TestReading.time).all()
    
    data = []
    for r in readings:
        data.append({
            'Time': r.time,
            'Bean Size': r.bean_size,
            'Inlet Pressure': r.inlet_pressure,
            'Separator Pressure': r.separator_pressure,
            'Temperature': r.temperature,
            'Liquid Rate': r.liquid_rate,
            'Rate Diff': r.rate_diff,
            'Gross Rate': r.gross_rate,
            'BS&W': r.bsw,
            'Net Production': r.net_production
        })
    
    df = pd.DataFrame(data)
    output = io.StringIO()
    df.to_csv(output, index=False)
    
    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'text/csv'
    response.headers['Content-Disposition'] = f'attachment; filename={test.test_id}.csv'
    
    return response

@export_bp.route('/api/export/well/<int:well_id>/csv', methods=['GET'])
def export_well_csv(well_id):
    well = Well.query.get_or_404(well_id)
    tests = WellTest.query.filter_by(well_id=well_id).order_by(WellTest.date).all()
    
    data = []
    for test in tests:
        readings = TestReading.query.filter_by(test_id=test.id).all()
        for r in readings:
            data.append({
                'Test ID': test.test_id,
                'Date': test.date,
                'Time': r.time,
                'Bean Size': r.bean_size,
                'Inlet Pressure': r.inlet_pressure,
                'Separator Pressure': r.separator_pressure,
                'Temperature': r.temperature,
                'Liquid Rate': r.liquid_rate,
                'Rate Diff': r.rate_diff,
                'Gross Rate': r.gross_rate,
                'BS&W': r.bsw,
                'Net Production': r.net_production
            })
    
    df = pd.DataFrame(data)
    output = io.StringIO()
    df.to_csv(output, index=False)
    
    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'text/csv'
    response.headers['Content-Disposition'] = f'attachment; filename={well.name}_data.csv'
    
    return response

@export_bp.route('/api/export/pdf/<int:test_id>', methods=['GET'])
def export_pdf(test_id):
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib import colors
    
    test = WellTest.query.get_or_404(test_id)
    readings = TestReading.query.filter_by(test_id=test_id).order_by(TestReading.time).all()
    
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    elements = []
    
    elements.append(Paragraph(f"Well Test Report", styles['Title']))
    elements.append(Spacer(1, 12))
    
    summary_data = [
        ['Test ID', test.test_id],
        ['Well', test.well.name],
        ['Date', str(test.date)],
        ['Remarks', test.remarks or 'N/A']
    ]
    
    gross = sum(r.gross_rate or 0 for r in readings if r.gross_rate)
    net = sum(r.net_production or 0 for r in readings if r.net_production)
    avg_bsw = sum(r.bsw or 0 for r in readings if r.bsw) / len(readings) if readings else 0
    
    summary_data.extend([
        ['Total Gross Production', f'{gross:.2f} bbl'],
        ['Total Net Production', f'{net:.2f} bbl'],
        ['Average BS&W', f'{avg_bsw:.2f}%']
    ])
    
    t = Table(summary_data, colWidths=[200, 200])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('PADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 20))
    
    elements.append(Paragraph("Readings", styles['Heading2']))
    table_data = [['Time', 'Inlet P', 'Sep P', 'Liquid Rate', 'Gross Rate', 'BS&W', 'Net']]
    for r in readings:
        table_data.append([
            str(r.time),
            f'{r.inlet_pressure or 0}',
            f'{r.separator_pressure or 0}',
            f'{r.liquid_rate or 0}',
            f'{r.gross_rate or 0}',
            f'{r.bsw or 0}%',
            f'{r.net_production or 0:.2f}'
        ])
    
    t2 = Table(table_data, colWidths=[60, 60, 60, 70, 70, 50, 60])
    t2.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
    ]))
    elements.append(t2)
    
    doc.build(elements)
    buffer.seek(0)
    
    response = make_response(buffer.getvalue())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename={test.test_id}.pdf'
    
    return response

@export_bp.route('/api/export/report', methods=['GET'])
def export_report():
    from flask import request
    period = request.args.get('period', 'last12m')
    well_ids = request.args.getlist('well_ids', type=int)
    
    from datetime import timedelta
    now = datetime.now().date()
    
    wells_query = Well.query.all()
    if well_ids:
        wells_query = Well.query.filter(Well.id.in_(well_ids)).all()
    
    data = []
    for well in wells_query:
        query = WellTest.query.filter_by(well_id=well.id)
        
        if period == 'last5':
            tests = query.order_by(WellTest.date.desc()).limit(5).all()
        elif period == 'last3m':
            tests = query.filter(WellTest.date >= (now - timedelta(days=90))).order_by(WellTest.date.desc()).all()
        elif period == 'last12m':
            tests = query.filter(WellTest.date >= (now - timedelta(days=365))).order_by(WellTest.date.desc()).all()
        else:
            tests = query.order_by(WellTest.date.desc()).all()
        
        if not tests:
            continue
        
        data.append({
            'well_name': well.name,
            'location': well.location,
            'total_tests': len(tests),
            'latest_test': tests[0].date.isoformat(),
            'current_gross': tests[0].avg_gross_rate or 0,
            'avg_gross': sum(t.avg_gross_rate or 0 for t in tests) / len(tests),
            'avg_bsw': sum(t.avg_bsw or 0 for t in tests) / len(tests),
            'net_prod': tests[0].net_prod or 0,
            'gross_bsw': tests[0].gross_bsw or 0
        })
    
    output = io.StringIO()
    output.write('Well,Location,Total Tests,Latest Test,Current Gross Rate,Average Gross Rate,Average BS&W,Net Production,Gross BS&W\n')
    for row in data:
        output.write(f"{row['well_name']},{row['location'] or ''},{row['total_tests']},{row['latest_test']},{row['current_gross']:.3f},{row['avg_gross']:.3f},{row['avg_bsw']:.2f},{row['net_prod']:.3f},{row['gross_bsw']:.3f}\n")
    
    output.seek(0)
    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'text/csv'
    response.headers['Content-Disposition'] = f'attachment; filename=production_report_{datetime.now().strftime("%Y%m%d")}.csv'
    
    return response

@export_bp.route('/api/export/summary/pdf', methods=['GET'])
def export_summary_pdf():
    import os
    from reportlab.lib.pagesizes import letter, landscape
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    
    query = WellTest.query
    if start_date_str:
        query = query.filter(WellTest.date >= datetime.strptime(start_date_str, '%Y-%m-%d').date())
    if end_date_str:
        query = query.filter(WellTest.date <= datetime.strptime(end_date_str, '%Y-%m-%d').date())
    
    tests = query.order_by(WellTest.date.desc()).all()
    
    # Process data to get latest test per well in this range
    well_stats = {}
    for t in tests:
        if t.well_id not in well_stats:
            # Get average readings for flowing hours only
            readings = [r for r in t.readings if (r.gross_rate or 0) > 0]
            avg_bean = sum(r.bean_size or 0 for r in readings) / len(readings) if readings else 0
            avg_inlet = sum(r.inlet_pressure or 0 for r in readings) / len(readings) if readings else 0
            avg_sep = sum(r.separator_pressure or 0 for r in readings) / len(readings) if readings else 0
            
            well_stats[t.well_id] = {
                'name': t.well.name,
                'location': t.well.location,
                'date': t.date,
                'gross': t.avg_gross_rate or 0,
                'bsw': t.avg_bsw or 0,
                'net': t.net_prod or 0,
                'bean': avg_bean,
                'inlet': avg_inlet,
                'sep': avg_sep,
                'count': 1
            }
        else:
            well_stats[t.well_id]['count'] += 1

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(letter), topMargin=0.3*inch, bottomMargin=0.3*inch, leftMargin=0.5*inch, rightMargin=0.5*inch)
    styles = getSampleStyleSheet()
    
    # Ultra-Premium Custom Styles
    title_style = ParagraphStyle(
        'PremiumTitle',
        parent=styles['Title'],
        fontSize=28,
        textColor=colors.HexColor('#B2000F'), # Deep Red
        alignment=0,
        spaceAfter=8
    )
    
    subtitle_style = ParagraphStyle(
        'PremiumSubtitle',
        parent=styles['Normal'],
        fontSize=11,
        textColor=colors.HexColor('#64748b'),
        alignment=0,
        spaceAfter=15
    )
    
    card_label_style = ParagraphStyle('CardLabel', fontSize=8, textColor=colors.HexColor('#64748b'), alignment=1, spaceAfter=2, fontName='Helvetica-Bold')
    card_value_style = ParagraphStyle('CardValue', fontSize=15, textColor=colors.HexColor('#B2000F'), alignment=1, fontName='Helvetica-Bold')
    
    # Header column style
    th_style = ParagraphStyle('TableHeader', parent=styles['Normal'], fontSize=10, textColor=colors.white, alignment=1, fontName='Helvetica-Bold')

    elements = []
    
    # --- HEADER SECTION ---
    logo_path = r"C:\laragon\www\WELLTEST_APP\logo.png"
    
    report_title_block = [
        Paragraph("WELL TEST PRODUCTION REPORT", title_style),
        Paragraph(f"GENERATED PERIOD: {start_date_str or 'EARLIEST'} TO {end_date_str or 'LATEST'}", subtitle_style)
    ]
    
    logo_img = None
    if os.path.exists(logo_path):
        logo_img = Image(logo_path, width=2.0*inch, height=0.65*inch)
    
    header_table = Table([[logo_img, report_title_block]], colWidths=[2.5*inch, 7.5*inch])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (0, 0), (0, 0), 'LEFT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 15),
    ]))
    elements.append(header_table)
    
    # Gradient-like separator
    line_data = [['']]
    line_table = Table(line_data, colWidths=[10*inch], rowHeights=[3])
    line_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#B2000F')),
        ('ROUNDEDCORNERS', [2, 2, 2, 2]),
    ]))
    elements.append(line_table)
    elements.append(Spacer(1, 0.25*inch))
    
    # --- SUMMARY KPI CARDS ---
    total_wells = len(well_stats)
    total_gross = sum(s['gross'] for s in well_stats.values())
    total_net = sum(s['net'] for s in well_stats.values())
    avg_bsw = (sum(s['bsw'] for s in well_stats.values()) / total_wells) if total_wells else 0
    
    def make_kpi(label, val, color='#1e40af'):
        style = ParagraphStyle('KPIVal', parent=card_value_style, textColor=colors.HexColor(color))
        return [Paragraph(label.upper(), card_label_style), Paragraph(val, style)]

    kpi_table = Table([[
        make_kpi("Wells Analyzed", str(total_wells)),
        make_kpi("Field Gross Rate", f"{total_gross:,.1f}", '#ef4444'), # Red for gross
        make_kpi("Field Net Rate", f"{total_net:,.1f}", '#10b981'), # Green for net
        make_kpi("Avg Water Cut", f"{avg_bsw:.1f}%", '#0ea5e9') # Blue for water
    ]], colWidths=[2.5*inch]*4)
    
    kpi_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.white),
        ('BOX', (0, 0), (-1, -1), 1.5, colors.HexColor('#f1f5f9')),
        ('TOPPADDING', (0, 0), (-1, -1), 15),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 15),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
    ]))
    elements.append(kpi_table)
    elements.append(Spacer(1, 0.35*inch))
    
    # --- MAIN DATA TABLE ---
    table_header = [
        Paragraph("WELL NAME", th_style),
        Paragraph("DATE", th_style),
        Paragraph("BEAN<br/><small>(1/64\")</small>", th_style),
        Paragraph("INLET P<br/><small>(PSI)</small>", th_style),
        Paragraph("SEP P<br/><small>(PSI)</small>", th_style),
        Paragraph("GROSS<br/><small>(BBL/d)</small>", th_style),
        Paragraph("BS&W<br/><small>(%)</small>", th_style),
        Paragraph("NET OIL<br/><small>(BBL/d)</small>", th_style)
    ]
    
    table_data = [table_header]
    for wid in sorted(well_stats.keys(), key=lambda x: well_stats[x]['name']):
        s = well_stats[wid]
        table_data.append([
            s['name'],
            s['date'].strftime('%d-%b-%y'),
            f"{s['bean']:.1f}",
            f"{s['inlet']:.0f}",
            f"{s['sep']:.0f}",
            f"{s['gross']:,.1f}",
            f"{s['bsw']:.1f}%",
            f"{s['net']:,.1f}"
        ])
    
    # Modern Table Styling
    col_widths = [1.8*inch, 1.2*inch, 1.0*inch, 1.2*inch, 1.2*inch, 1.3*inch, 1.0*inch, 1.3*inch]
    t = Table(table_data, repeatRows=1, colWidths=col_widths)
    t.setStyle(TableStyle([
        # Header Styling
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#B2000F')), # Deep Red
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('VALIGN', (0, 0), (-1, 0), 'MIDDLE'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('TOPPADDING', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        
        # Body Styling
        ('FONTSIZE', (0, 1), (-1, -1), 9.5),
        ('ALIGN', (0, 1), (-1, -1), 'CENTER'),
        ('ALIGN', (0, 1), (0, -1), 'LEFT'), # Well name
        ('LEFTPADDING', (0, 1), (0, -1), 12),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.HexColor('#334155')),
        ('VALIGN', (0, 1), (-1, -1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        
        # Highlighting Net Oil
        ('FONTNAME', (-1, 1), (-1, -1), 'Helvetica-Bold'),
        ('TEXTCOLOR', (-1, 1), (-1, -1), colors.HexColor('#B2000F')),
    ]))
    
    elements.append(t)
    
    # --- FOOTER ---
    elements.append(Spacer(1, 0.5*inch))
    footer_style = ParagraphStyle('Footer', fontSize=8, textColor=colors.HexColor('#94a3b8'), alignment=1)
    elements.append(Paragraph(f"PRODUCED BY WELLTEST PRO SYSTEM • {datetime.now().strftime('%d %B %Y')} • PAGE 1 OF 1", footer_style))

    doc.build(elements)
    buffer.seek(0)
    
    filename = f"Well_Test_Production_Report_{datetime.now().strftime('%Y%m%d')}.pdf"
    response = make_response(buffer.getvalue())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename={filename}'
    
    return response

@export_bp.route('/api/export/well/<int:well_id>/history/csv', methods=['GET'])
def export_well_history_csv(well_id):
    well = Well.query.get_or_404(well_id)
    tests = WellTest.query.filter_by(well_id=well_id).order_by(WellTest.date.desc()).all()
    
    output = io.StringIO()
    output.write('Test ID,Date,Gross Rate,BS&W,Net Prod,Gross BS&W,Readings\n')
    for t in tests:
        output.write(f"{t.test_id},{t.date.isoformat()},{t.avg_gross_rate or 0:.3f},{t.avg_bsw or 0:.2f},{t.net_prod or 0:.3f},{t.gross_bsw or 0:.3f},{t.readings.count()}\n")
    
    output.seek(0)
    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'text/csv'
    response.headers['Content-Disposition'] = f'attachment; filename={well.name}_history.csv'
    
    return response