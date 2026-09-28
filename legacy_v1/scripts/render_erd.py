"""Render an exact, deterministic PNG ERD from the source schema contract."""
from pathlib import Path
import json
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
SPECS = json.loads((ROOT / 'docs/raw_inventory.json').read_text(encoding='utf-8'))
OUT = ROOT / 'docs/cloudcare_erd.png'
WIDTH, HEIGHT = 3900, 2800
BOX_WIDTH, HEADER, ROW = 1050, 110, 45
POSITIONS = {
    'storage_usage_monthly': (100, 200), 'user': (1420, 200), 'plan': (2740, 200),
    'user_activity_daily': (100, 1030), 'support_ticket': (1420, 1030), 'subscription': (2740, 1030),
    'device': (100, 1860), 'subscription_event': (1420, 1860), 'payment_history': (2740, 1860),
}
COLORS = {'user': '#087fa3', 'plan': '#7c4cc0', 'subscription': '#c76b17'}

def font(size, bold=False):
    return ImageFont.truetype('C:/Windows/Fonts/' + ('malgunbd.ttf' if bold else 'malgun.ttf'), size)

def row_y(name, col):
    return POSITIONS[name][1] + HEADER + list(SPECS[name]['columns']).index(col)*ROW + ROW/2

def left(name, col):
    return (POSITIONS[name][0], row_y(name, col))

def right(name, col):
    return (POSITIONS[name][0]+BOX_WIDTH, row_y(name, col))

def render():
    im = Image.new('RGB', (WIDTH, HEIGHT), '#f6f8fc')
    draw = ImageDraw.Draw(im)
    draw.text((100, 45), 'CloudCare | Database ERD', fill='#102b4c', font=font(58, True))
    draw.text((100, 122), 'MySQL 8.4  ·  9 tables  ·  73 columns  ·  11 foreign keys', fill='#506078', font=font(31))

    # Each path is parent PK -> child FK; all segments stay outside table interiors.
    paths = [
        ('user', 'storage_usage_monthly', 'user_id', [left('user','user_id'), (1260,row_y('user','user_id')), (1260,row_y('storage_usage_monthly','user_id')), right('storage_usage_monthly','user_id')]),
        ('user', 'user_activity_daily', 'user_id', [left('user','user_id'), (1300,row_y('user','user_id')), (1300,row_y('user_activity_daily','user_id')), right('user_activity_daily','user_id')]),
        ('user', 'device', 'user_id', [left('user','user_id'), (1340,row_y('user','user_id')), (1340,row_y('device','user_id')), right('device','user_id')]),
        ('user', 'support_ticket', 'user_id', [left('user','user_id'), (1380,row_y('user','user_id')), (1380,row_y('support_ticket','user_id')), left('support_ticket','user_id')]),
        ('user', 'subscription', 'user_id', [right('user','user_id'), (2520,row_y('user','user_id')), (2520,880), (2670,880), (2670,row_y('subscription','user_id')), left('subscription','user_id')]),
        ('user', 'subscription_event', 'user_id', [right('user','user_id'), (2490,row_y('user','user_id')), (2490,1760), (2500,1760), (2500,row_y('subscription_event','user_id')), right('subscription_event','user_id')]),
        ('plan', 'subscription', 'plan_id', [left('plan','plan_id'), (2630,row_y('plan','plan_id')), (2630,row_y('subscription','plan_id')), left('subscription','plan_id')]),
        ('plan', 'subscription_event', 'old_plan_id', [right('plan','plan_id'), (3830,row_y('plan','plan_id')), (3830,1740), (2590,1740), (2590,row_y('subscription_event','old_plan_id')), right('subscription_event','old_plan_id')]),
        ('plan', 'subscription_event', 'new_plan_id', [right('plan','plan_id'), (3870,row_y('plan','plan_id')), (3870,1800), (2630,1800), (2630,row_y('subscription_event','new_plan_id')), right('subscription_event','new_plan_id')]),
        ('subscription', 'payment_history', 'subscription_id', [right('subscription','subscription_id'), (3810,row_y('subscription','subscription_id')), (3810,row_y('payment_history','subscription_id')), right('payment_history','subscription_id')]),
        ('subscription', 'subscription_event', 'subscription_id', [left('subscription','subscription_id'), (2550,row_y('subscription','subscription_id')), (2550,row_y('subscription_event','subscription_id')), right('subscription_event','subscription_id')]),
    ]
    actual = {(parent,child,col) for parent,child,col,_ in paths}
    expected = {(parent,child,col) for child,spec in SPECS.items() for col,(parent,pk) in spec['fk'].items()}
    assert actual == expected and len(paths) == 11
    for parent, child, col, points in paths:
        color = COLORS[parent]
        if SPECS[child]['columns'][col]['nullable']:
            for (x1,y1),(x2,y2) in zip(points,points[1:]):
                length = abs(x2-x1)+abs(y2-y1)
                for start in range(0,int(length),22):
                    end = min(start+12,length)
                    draw.line([(x1+(x2-x1)*start/length,y1+(y2-y1)*start/length),
                               (x1+(x2-x1)*end/length,y1+(y2-y1)*end/length)],fill=color,width=4)
        else:
            draw.line(points, fill=color, width=4, joint='curve')

    for name, (x,y) in POSITIONS.items():
        spec = SPECS[name]
        h = HEADER + len(spec['columns'])*ROW + 14
        draw.rounded_rectangle((x+5,y+7,x+BOX_WIDTH+5,y+h+7),radius=15,fill='#e1e7ef')
        draw.rounded_rectangle((x,y,x+BOX_WIDTH,y+h),radius=15,fill='white',outline='#c4cfdd',width=2)
        draw.rounded_rectangle((x,y,x+BOX_WIDTH,y+65),radius=15,fill='#14365a')
        draw.rectangle((x,y+35,x+BOX_WIDTH,y+65),fill='#14365a')
        draw.text((x+22,y+10),name,fill='white',font=font(32,True))
        draw.text((x+BOX_WIDTH-160,y+17),f'{len(spec["columns"])} columns',fill='#c6d8eb',font=font(22))
        for dx,label in [(20,'KEY'),(130,'COLUMN'),(620,'TYPE'),(920,'NULL')]:
            draw.text((x+dx,y+75),label,fill='#677b93',font=font(21,True))
        for i,(col,info) in enumerate(spec['columns'].items()):
            top = y+HEADER+i*ROW
            if i%2==0:
                draw.rectangle((x+2,top,x+BOX_WIDTH-2,top+ROW),fill='#f0f4f9')
            key = 'PK' if col==spec['pk'] else ('FK' if col in spec['fk'] else ('UK' if name=='plan' and col=='plan_name' else ''))
            if key:
                key_color = '#bd7900' if key=='PK' else (COLORS[spec['fk'][col][0]] if key=='FK' else '#5675a7')
                draw.rounded_rectangle((x+18,top+7,x+85,top+ROW-6),radius=5,fill=key_color)
                draw.text((x+29,top+7),key,fill='white',font=font(23,True))
            draw.text((x+130,top+5),col,fill='#16304d',font=font(27,key=='PK'))
            draw.text((x+620,top+6),info['type'],fill='#455b72',font=font(25))
            draw.text((x+940,top+7),'Y' if info['nullable'] else '-',fill='#657b91',font=font(24))

    # Endpoint markers: bars at parent PK, crow's foot plus circle at child FK.
    for parent, child, col, points in paths:
        color = COLORS[parent]
        px,py = points[0]; nx,ny = points[1]
        direction = 1 if nx>px else -1
        for offset in [12,22]:
            draw.line((px+direction*offset,py-12,px+direction*offset,py+12),fill=color,width=4)
        if SPECS[child]['columns'][col]['nullable']:
            cx=px+direction*22
            draw.ellipse((cx-9,py-9,cx+9,py+9),fill='#f6f8fc',outline=color,width=3)
        cx,cy = points[-1]; bx,by = points[-2]
        direction = 1 if bx>cx else -1
        for delta in [-13,0,13]:
            draw.line((cx,cy+delta,cx+direction*23,cy),fill=color,width=4)
        ox=cx+direction*36
        draw.ellipse((ox-8,cy-8,ox+8,cy+8),fill='#f6f8fc',outline=color,width=3)

    draw.text((100,2530),'PK  Primary key     FK  Foreign key     UK  Unique     NULL Y  Nullable',fill='#263f5b',font=font(29,True))
    draw.text((100,2580),'All parent records can have 0..N children. Solid FK: exactly 1 parent. Dashed FK: 0..1 parent.',fill='#536a82',font=font(28))
    draw.text((100,2630),'Dashed relationship: subscription_event.new_plan_id → plan.plan_id (nullable)',fill='#7c4cc0',font=font(28))
    draw.text((100,2700),'Source: db/init/01_schema.sql  •  Schema design; database deployment pending',fill='#6a7d91',font=font(25))
    assert sum(len(s['columns']) for s in SPECS.values()) == 73
    im.save(OUT)
    print(f'{OUT}: {WIDTH}x{HEIGHT}, 9 tables, 73 columns, 11 verified FK paths')

if __name__ == '__main__':
    render()
