# -*- coding: utf-8 -*-
"""Passe 2: retry das escolas que falharam, usando o RA/CRE da linha como fallback."""
import csv
import json
import os
import time
import urllib.parse
import urllib.request

PDAF = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(PDAF, 'geocode_cache.json')
UA = 'PDAF-KML/1.0 (atualizacao de mapa de escolas; contato: caiohmrs@gmail.com)'
DELAY = 1.2

def geocode(q, tentativas=3):
    url = 'https://nominatim.openstreetmap.org/search?format=json&limit=1&q=' + urllib.parse.quote(q)
    for t in range(tentativas):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA})
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode('utf-8'))
            if data:
                return float(data[0]['lat']), float(data[0]['lon']), data[0].get('display_name', '')
            return None
        except Exception as e:
            print(f'    tentativa {t+1} falhou: {e}', flush=True)
            time.sleep(2)
    return None

cache = {}
if os.path.exists(CACHE):
    with open(CACHE, encoding='utf-8') as f:
        cache = json.load(f)

with open(PDAF + r'\seed_padronizado.csv', encoding='utf-8-sig') as f:
    rows = list(csv.DictReader(f, delimiter=';'))

# chave canonical -> (padrao, ra, cre)
import contextlib, importlib.util, io, sys
sys.path.insert(0, PDAF)
spec = importlib.util.spec_from_file_location('gera_relatorio', PDAF + r'\_gera_relatorio.py')
mod = importlib.util.module_from_spec(spec)
with contextlib.redirect_stdout(io.StringIO()):
    spec.loader.exec_module(mod)
canonical = mod.canonical
norm = mod.norm
MANUAL_MAP = mod.MANUAL_MAP

def canon(p):
    return MANUAL_MAP.get(norm(p), canonical(p))

pend = {}
matched_keys = set()
if os.path.exists(PDAF + r'\coords_matched.json'):
    with open(PDAF + r'\coords_matched.json', encoding='utf-8') as f:
        matched_keys = set(json.load(f).keys())
for r in rows:
    padrao = r['Escola_Padrao'].strip()
    if not padrao:
        continue
    key = canon(padrao)
    if key in cache or key in matched_keys:
        continue
    pend.setdefault(key, {'padrao': padrao, 'ra': (r['RA'] or '').strip(), 'cre': (r['CRE'] or '').strip()})

print(f'{len(pend)} escolas ainda sem coordenada', flush=True)
ok = 0
falhou = []
for key, info in sorted(pend.items()):
    print(f'  tentando {info["padrao"]} (RA={info["ra"]!r}, CRE={info["cre"]!r})', flush=True)
    res = None
    alvos = []
    if info['ra']:
        alvos.append(f'{info["ra"]}, Distrito Federal, Brasil')
    if info['cre']:
        alvos.append(f'{info["cre"]}, Distrito Federal, Brasil')
    for q in alvos:
        r = geocode(q)
        time.sleep(DELAY)
        if r:
            res = {'lat': r[0], 'lon': r[1], 'endereco': r[2], 'query': q, 'aprox': True}
            break
    if res:
        cache[key] = res
        ok += 1
        print(f'    OK -> {res["lat"]:.5f},{res["lon"]:.5f} ({q})', flush=True)
    else:
        falhou.append(info['padrao'])
        print(f'    FALHOU', flush=True)

with open(CACHE, 'w', encoding='utf-8') as f:
    json.dump(cache, f, ensure_ascii=False, indent=1)

print(f'FIM passe2: ok={ok} | falhou={len(falhou)}')
if falhou:
    print('Falharam:', falhou)
