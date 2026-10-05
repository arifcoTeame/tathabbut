"""Break down the engine_end_to_end misses of benchmark_typos.py (same sample, seed 7):
abstained (no source, NO_ORIGIN) versus another verse shown. Run from backend/."""
import sys, json, random
from collections import Counter
sys.path.insert(0,'.')
import scripts.benchmark_typos as bt
from app.core.index import HybridIndex
from app.core import pipeline
from app.core.judge import Thresholds
from app.core.arabic import strip_diacritics, wording_tokens
from pathlib import Path
index=HybridIndex.load(Path('../data/index'))
docs=index.docs
quran=[i for i,d in enumerate(docs) if d.id.startswith('quran-')]
wording={d.id: wording_tokens(d.text) for d in docs if d.id.startswith('quran-')}
def contains(h,n):
    return any(h[i:i+len(n)]==n for i in range(len(h)-len(n)+1))
def holds(doc_id,intended):
    if not doc_id or not doc_id.startswith('quran-'): return False
    loc=doc_id[6:]
    if '-' in loc:
        s,a=loc.split('-')[0].split(':'); b=int(loc.split('-')[1])
        hay=[w for n in range(int(a),b+1) for w in wording.get(f'quran-{s}:{n}',[])]
    else: hay=wording.get(doc_id,[])
    return contains(hay,intended)
rng=random.Random(7); sample=sorted(rng.sample(quran,1000))
out={}
for i in sample:
    words=strip_diacritics(docs[i].text).split()
    for kind,q,raw in bt.queries(words):
        if kind=='exact': continue
        intended=wording_tokens(' '.join(raw))
        c=pipeline.run(index,'﴿'+q+'﴾',Thresholds(),'{surah}')['claims'][0]
        src=(c.get('source') or {}).get('id') or ''
        code=c['verdict']['code']
        ok=holds(src,intended) and code=='ALTERED'
        if not ok:
            cat = 'right_verse_other_verdict' if holds(src,intended) else ('no_source' if not src else 'other_source')
            out.setdefault(kind,Counter())[(cat,code)]+=1
for k,v in out.items(): print(k, dict(v))
