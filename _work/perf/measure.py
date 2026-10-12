"""Measure the editor against the DR §1 performance budget (T-1064).

Local server, browser layout (as on Vercel), Chromium at 1600x1000.  Budget:
open report < 1 s, section / units / comps switch < 150 ms, keystroke < 16 ms
(no server round trip).  Run from engine/:  python ../_work/perf/measure.py
"""
import json, statistics, sys, tempfile, time
sys.path.insert(0, "tests"); sys.path.insert(0, ".")
import shell_kit as K


class F:
    def mktemp(self, n):
        return __import__("pathlib").Path(tempfile.mkdtemp())


gen = K.site.__wrapped__(F()); s = next(gen); p = s.page
out = {}
for tpl in ("sf1_appraisal_v1_4", "2_to_4_unit_appraisal_v1_4"):
    cid = K.new_case(s, tpl)
    runs = []
    for i in range(3):
        t0 = time.perf_counter()
        p.goto(f"{s.base}/#/case/{cid}")
        p.wait_for_function("typeof S!=='undefined'&&S.formReady===true&&!!document.querySelector('#rf')", timeout=300_000)
        runs.append((time.perf_counter() - t0) * 1000)
    sw = []
    for n in (4, 8, 10, 22, 2):
        t0 = time.perf_counter()
        p.evaluate(f"document.querySelector('.railitem[data-secn=\"{n}\"]').click()")
        p.wait_for_function(f"S.section==={n}")
        K.until(p, f"()=>{{const t=document.querySelector('[data-secn=\"{n}\"]'); if(!t) return true; const r=t.getBoundingClientRect(); return r.top<innerHeight&&r.bottom>0;}}", timeout=20)
        sw.append((time.perf_counter() - t0) * 1000)
    # keystroke: typing into a text field, time from key to the value painted
    fr = K.frame(p)
    ks = fr.evaluate("""async()=>{const el=[...document.querySelectorAll('.v[contenteditable]')].find(e=>e.offsetParent);
        if(!el) return null; el.focus(); const t=[];
        for(let i=0;i<20;i++){ const a=performance.now();
          document.execCommand('insertText',false,'x');
          await new Promise(r=>requestAnimationFrame(()=>r())); t.push(performance.now()-a);}
        document.execCommand('undo'); return t;}""")
    out[tpl] = {"open_ms": [round(x) for x in runs], "open_median_ms": round(statistics.median(runs)),
                "section_switch_ms": [round(x) for x in sw],
                "keystroke_to_paint_ms_median": round(statistics.median(ks), 1) if ks else None}
print(json.dumps(out, indent=1))
try: next(gen)
except StopIteration: pass
