import json, sys
d = json.load(open('engine/spec/c1_form.json', encoding='utf-8'))


def show(pn):
    p = [x for x in d['pages'] if x['page'] == pn][0]
    print('=== page', pn)
    for e in p['elements']:
        k = e['kind']
        if k == 'table':
            print(f"TABLE y={e['y']:.0f}-{e['y1']:.0f} x={e['x0']:.0f}-{e['x1']:.0f} {e['column']} cols={[c['head'] for c in e['columns']]}")
            for r in e['rows']:
                print('    row', r.get('bar', ''), r.get('text', ''), r.get('ids', ''),
                      [(c['text'], c['ids'], 'CK' if c['check'] else '') for c in r['cells']])
        elif k == 'lead':
            print('LEAD', [l['text'] for l in e['lines']], e['ids'])
        else:
            print(f"{k:6} {e.get('column',''):5} {e.get('style',''):6} y={e['y']:.0f} x={e.get('x0',0):.0f} "
                  f"{e.get('title') or e.get('text','')!r} ids={e['ids']} {'YN' if e.get('yes_no') else ''}")


for pn in sys.argv[1:]:
    show(int(pn))
