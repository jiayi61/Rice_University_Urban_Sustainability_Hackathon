"""Paginated reports from server-owned model snapshots; no second model/API run."""
from collections import OrderedDict
from copy import deepcopy
from io import BytesIO
from pathlib import Path
import secrets
import threading
import time
from xml.sax.saxutils import escape

_runs = OrderedDict()
_lock = threading.Lock()


def remember_plan(payload):
    run_id = secrets.token_urlsafe(24)
    payload['report_id'] = run_id
    with _lock:
        _runs[run_id] = (time.monotonic(), deepcopy(payload))
        while len(_runs) > 30:
            _runs.popitem(last=False)
    return payload


def saved_report(run_id):
    with _lock:
        entry = _runs.get(run_id) if isinstance(run_id, str) else None
        if not entry or time.monotonic() - entry[0] > 3600:
            raise ValueError('This calculation has expired. Build your event plan again before downloading.')
        payload = deepcopy(entry[1])
    return build_pdf(payload)


def build_pdf(p):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether
    from reportlab.graphics.shapes import Drawing, Line, PolyLine, String

    with _lock:
        if 'EventFlowSans' not in pdfmetrics.getRegisteredFontNames():
            fonts = Path(__file__).resolve().parents[2] / 'assets/fonts'
            pdfmetrics.registerFont(TTFont('EventFlowSans', str(fonts / 'NotoSansSC-Regular.ttf')))
            pdfmetrics.registerFont(TTFont('EventFlowBold', str(fonts / 'NotoSansSC-Bold.ttf')))
    ink, green, muted = '#18372F', '#176D60', '#55675F'
    styles = {
        'body': ParagraphStyle('body', fontName='EventFlowSans', fontSize=10, leading=15, textColor=ink, spaceAfter=8),
        'small': ParagraphStyle('small', fontName='EventFlowSans', fontSize=8, leading=11, textColor=muted, spaceAfter=5),
        'h1': ParagraphStyle('h1', fontName='EventFlowBold', fontSize=27, leading=32, textColor=ink, spaceAfter=15),
        'h2': ParagraphStyle('h2', fontName='EventFlowBold', fontSize=16, leading=21, textColor=ink, spaceAfter=12),
        'eyebrow': ParagraphStyle('eyebrow', fontName='EventFlowBold', fontSize=9, leading=13, textColor=green, spaceAfter=12),
    }

    def para(value, kind='body'):
        text = str(value).replace('→', ' to ').replace('—', '-').replace('–', '-').replace('×', 'x')
        style = styles[kind]
        if any('\u3000' <= c <= '\u9fff' for c in text):
            style = ParagraphStyle(kind+'CJK', parent=style, fontName='EventFlowSans', wordWrap='CJK')
        return Paragraph(escape(text).replace('\n', '<br/>'), style)

    def table(heads, rows, widths):
        data = [[para(h, 'small') for h in heads]] + [[para(v, 'small') for v in row] for row in rows]
        t = Table(data, colWidths=widths, repeatRows=1, hAlign='LEFT')
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#DFEAE3')),
            ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#F5F7F4')]),
            ('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),9),
            ('RIGHTPADDING',(0,0),(-1,-1),9),('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),8),
            ('LINEBELOW',(0,0),(-1,0),.6,colors.HexColor('#B4C7BD'))]))
        return t

    s=p['simulation']; b=s['baseline']; r=s['recommended']; width=499
    buffer=BytesIO()
    doc=SimpleDocTemplate(buffer,pagesize=(595,842),leftMargin=48,rightMargin=48,topMargin=62,bottomMargin=55,
                          title='EventFlow | '+p['venue']['city']+' event mobility plan',author='EventFlow')
    story=[para('EVENTFLOW / EVENT MOBILITY DECISION REPORT','eyebrow'),para(p['venue']['city'],'h1'),
           para(p['venue']['name'],'h2'),para(p['event']['name']),
           para('Generated '+p['brief']['generated_at']+' | Calculation '+p.get('report_id','preview')[:12],'small'),
           para('Event date: '+p['event']['date']+' | Attendance: '+format(p['event']['attendance'],',')+' | Currency: USD','small'),
           Spacer(1,12),table(['Measure','Baseline','Selected plan'],[
               ['Transport cohort',f"{b['cohort']:,} people",f"{r['cohort']:,} people"],
               ['Queue clearance',f"{b['clearance_minutes']:.1f} min",f"{r['clearance_minutes']:.1f} min"],
               ['Queue burden',f"{b['queue_person_hours']:,.1f} person-hours",f"{r['queue_person_hours']:,.1f} person-hours"],
               ['Served within 2 hours',f"{b['served_120']:,}",f"{r['served_120']:,}"],
               ['Additional buses','0',str(r['fleet'])],['Incremental cost','$0',f"${r['cost_usd']:,}"]],[195,152,152]),Spacer(1,15),
           para('Decision and scope','h2'),para(f"Selected {r['fleet']} additional buses from {s['evaluated_portfolios']} evaluated fleet sizes, minimizing queue burden within the fleet and budget constraints. Costs include an 18% delivery allowance."),
           para('Budget: '+(f"${s['budget_usd']:,.0f}" if s['budget_usd'] is not None else 'Not supplied; fleet limit governs selection.')),
           para('Scenario projection, not measured performance. Public place and road data are combined with user-editable operating assumptions. Only the selected transport cohort is modeled.','small'),
           PageBreak(),para('01 / TRANSPORT PLAN','eyebrow'),para('Routes and fleet allocation','h1'),
           para('Road travel times inform the proposed shuttle cycles. Catchment demand shares and baseline service require local verification.'),
           table(['Catchment','People','Buses','Cycle min','Clearance min'],[
               [v['name'],f"{v['people']:,.0f}",v['buses'],v['cycle_minutes'],v['clearance_minutes']] for v in r['routes']],[219,65,55,75,85]),
           Spacer(1,18),para('Before deployment','h2'),para('Confirm bus availability, permitted routes, loading areas, accessible vehicles, staffing and event operating windows with local operators. A road route does not establish transit service or bus access permission.'),
           PageBreak(),para('02 / MODEL BEHAVIOR','eyebrow'),para('Queue clearance and sensitivity','h1')]
    chart=Drawing(width,190); max_t=max(120,b['clearance_minutes'],r['clearance_minutes']); max_q=b['cohort']
    for fraction in (0,.25,.5,.75,1):
        y=28+fraction*125;chart.add(Line(55,y,480,y,strokeColor=colors.HexColor('#DBE2DC')))
        chart.add(String(2,y-3,f'{round(max_q*fraction):,}',fontName='EventFlowSans',fontSize=8,fillColor=colors.HexColor(muted)))
        chart.add(String(55+fraction*425,12,str(round(max_t*fraction)),fontName='EventFlowSans',fontSize=8))
    for series,color in ((b,'#929B95'),(r,green)):
        # Include terminal zero at the displayed end; retain enough points for short queues.
        rows=series['routes'];points=[]
        for i in range(81):
            t=max_t*i/80;remaining=sum(max(0,x['people']-x['service_pph']*t/60) for x in rows)
            points.extend([55+t/max_t*425,28+remaining/max_q*125])
        chart.add(PolyLine(points,strokeColor=colors.HexColor(color),strokeWidth=2))
    chart.add(String(55,175,'People remaining | Grey: baseline | Green: selected plan',fontName='EventFlowSans',fontSize=9))
    chart.add(String(300,0,'Minutes after event end',fontName='EventFlowSans',fontSize=8))
    story.extend([chart,Spacer(1,15),para('Demand and service variation','h2'),
        table(['Demand multiplier','Service multiplier','Baseline min','Plan min'],[[x['demand_factor'],x['service_factor'],x['baseline'],x['plan']] for x in s['sensitivity']],[130,130,119,120]),
        Spacer(1,10),para('Nine deterministic scenarios vary demand and service by +/-15%. These ranges are not statistical confidence intervals.','small'),
        PageBreak(),para('03 / AUDIT TRAIL','eyebrow'),para('Inputs, evidence and limits','h1'),para('Your event request','h2'),para(p['brief']['original_prompt']),
        para('Parser: '+p['brief']['parser'],'small'),
        table(['Operating input','Value'],[[k.replace('_',' '),v] for k,v in s['parameters'].items()],[330,169]),Spacer(1,14)])
    for a in p['brief']['assumptions']:
        story.append(para(a['field']+': '+str(a['value'])+'. '+a['basis'],'small'))
    story.extend([PageBreak(),para('04 / SOURCES & MODEL','eyebrow'),para('Know what the calculation supports','h1')])
    for key,value in p['data_freshness'].items():
        story.append(para(key.replace('_',' ').title()+': '+str(value),'small'))
    for route in r['routes']:
        story.append(para(route['name']+': '+route['source'],'small'))
    story.extend([Spacer(1,12),para('Method','h2'),para('Bus cycle = twice one-way road time + dwell. Added people/hour = buses x seats x load factor x 60 / cycle. For cohort Q and hourly service rate m: clearance = 60Q/m; queue burden = Q squared / (2m). All passengers enter queues at event end. Fleet is allocated proportionally using integer rounding with conserved totals.','small')])
    for item in s['limitations']:
        story.append(para('- '+item,'small'))
    story.extend([Spacer(1,10),para('Public data references: OpenStreetMap contributors (ODbL), https://www.openstreetmap.org/copyright ; OSRM, https://project-osrm.org ; Open-Meteo historical data (when available), https://open-meteo.com . The source status above distinguishes fetched/cached data from assumptions.','small')])

    def footer(canvas, document):
        canvas.setStrokeColor(colors.HexColor('#D6DFD8'));canvas.line(48,43,547,43)
        canvas.setFont('EventFlowSans',8);canvas.setFillColor(colors.HexColor(muted))
        canvas.drawString(48,29,'EVENTFLOW | Planning scenario - local validation required')
        canvas.drawRightString(547,29,f'{document.page}')
        canvas.setFont('EventFlowBold',8);canvas.drawString(48,814,'EVENTFLOW / RESEARCH & OPERATIONS')
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    return buffer.getvalue()
