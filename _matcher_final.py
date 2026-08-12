# -*- coding: utf-8 -*-
"""Matcher final: core + regiao + guarda de numero + fuzzy + disambiguacao por proximidade.
Saida: dict chave -> (coord, nome_kml, origem) salvo em coords_matched.json + lista p/ geocode."""
import contextlib
import csv
import difflib
import io
import importlib.util
import json
import math
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET

PDAF = r'C:\Users\caio.ribeiro\Documents\Python Scripts\PDAF'
sys.path.insert(0, PDAF)

spec = importlib.util.spec_from_file_location('gera_relatorio', PDAF + r'\_gera_relatorio.py')
mod = importlib.util.module_from_spec(spec)
with contextlib.redirect_stdout(io.StringIO()):
    spec.loader.exec_module(mod)
canonical = mod.canonical
norm = mod.norm
MANUAL_MAP = mod.MANUAL_MAP

def canon(padrao):
    return MANUAL_MAP.get(norm(padrao), canonical(padrao))

REGOES = [
    'CEILANDIA', 'SOL NASCENTE', 'POR DO SOL', 'GAMA', 'PLANALTINA', 'GUARA',
    'TAGUATINGA', 'SAMAMBAIA', 'SANTA MARIA', 'SOBRADINHO', 'PARANOA', 'ITAPOA',
    'BRAZLANDIA', 'SAO SEBASTIAO', 'RECANTO DAS EMAS', 'NUCLEO BANDEIRANTE',
    'CRUZEIRO', 'PLANO PILOTO', 'ASA NORTE', 'ASA SUL', 'LAGO NORTE', 'LAGO SUL',
    'JARDIM BOTANICO', 'VICENTE PIRES', 'RIACHO FUNDO', 'CANDANGOLANDIA',
    'ARAPOANGA', 'FERCAL', 'VARJAO', 'SOBRADINHO II', 'SIA', 'EIXAO',
]

def core_de(nome):
    n = canon(nome)
    n = re.sub(r'\([^)]*\)', ' ', n)
    toks = n.split()
    if len(toks) >= 2 and toks[0] == toks[1]:
        toks = toks[1:]
    n = ' '.join(toks)
    n = re.sub(r'\bEAD\b', ' ', n)
    toks = n.split()
    out = []
    i = 0
    while i < len(toks):
        t = toks[i]
        if t in ('DE', 'DO', 'DA', 'DAS', 'DOS') and i + 1 < len(toks) and toks[i + 1] in REGOES:
            i += 2
            continue
        if t in REGOES:
            i += 1
            continue
        out.append(t)
        i += 1
    return ' '.join(out)

def regiao_de(nome):
    n = canon(nome)
    for r in sorted(REGOES, key=len, reverse=True):
        if re.search(r'\b' + re.escape(r) + r'\b', n):
            return r
    return None

def numero_de(core):
    m = re.search(r'\b(\d{2,3})\b', core)
    return m.group(1) if m else None

def regioes_compat(a, b):
    if a is None or b is None:
        return True
    if a == b:
        return True
    par_ceilandia = {'CEILANDIA', 'SOL NASCENTE', 'POR DO SOL'}
    if a in par_ceilandia and b in par_ceilandia:
        return True
    if {a, b} == {'PARANOA', 'ITAPOA'}:
        return True
    return False

def parse_coord(c):
    try:
        lon, lat = c.split(',')[0], c.split(',')[1]
        return float(lat), float(lon)
    except Exception:
        return None

def dist_km(a, b):
    la1, lo1 = a
    la2, lo2 = b
    return math.hypot(la1 - la2, lo1 - lo2) * 111.0

# ---------- dados ----------
ns = {'k': 'http://www.opengis.net/kml/2.2'}
tree = ET.parse(PDAF + r'\emendas_mapa.kml')
kml = []
for pm in tree.getroot().iter('{http://www.opengis.net/kml/2.2}Placemark'):
    n = pm.find('k:name', ns)
    c = pm.find('k:Point/k:coordinates', ns)
    if n is None or c is None:
        continue
    nome = (n.text or '').strip()
    coord = (c.text or '').strip()
    if not coord:
        continue
    kml.append({'canon': canon(nome), 'core': core_de(nome), 'reg': regiao_de(nome),
                'coord': coord, 'nome': nome, 'pt': parse_coord(coord)})

with open(PDAF + r'\seed_padronizado.csv', encoding='utf-8-sig') as f:
    rows = list(csv.DictReader(f, delimiter=';'))

escolas = {}
for r in rows:
    padrao = r['Escola_Padrao'].strip()
    if not padrao:
        continue
    escolas.setdefault(canon(padrao), padrao)

def candidatos(key, padrao):
    core_s = core_de(padrao)
    reg_s = regiao_de(padrao)
    num_s = numero_de(core_s)
    cands = [k for k in kml if k['core'] == core_s and regioes_compat(k['reg'], reg_s)]
    if not cands:
        cands = []
        for k in kml:
            if k['pt'] is None:
                continue
            num_k = numero_de(k['core'])
            if num_s and num_k and num_s != num_k:
                continue  # numero diferente -> escola diferente
            if difflib.SequenceMatcher(None, k['core'], core_s).ratio() >= 0.85 and \
               regioes_compat(k['reg'], reg_s):
                cands.append(k)
    return cands

matched = {}
geocode = {}
for key, padrao in sorted(escolas.items()):
    cands = candidatos(key, padrao)
    if len(cands) == 1:
        matched[key] = {'coord': cands[0]['coord'], 'nome_kml': cands[0]['nome'], 'origem': 'kml'}
    elif len(cands) > 1:
        # disambiguacao por proximidade: todos os candidatos no mesmo ponto?
        pts = [c['pt'] for c in cands if c['pt']]
        if pts and max(dist_km(pts[0], p) for p in pts) < 2.0:
            matched[key] = {'coord': cands[0]['coord'], 'nome_kml': ' | '.join(c['nome'] for c in cands),
                            'origem': 'kml-proximidade'}
        else:
            geocode[key] = padrao
    else:
        geocode[key] = padrao

with open(PDAF + r'\coords_matched.json', 'w', encoding='utf-8') as f:
    json.dump(matched, f, ensure_ascii=False, indent=1)
with open(PDAF + r'\geocode_pendentes.json', 'w', encoding='utf-8') as f:
    json.dump(geocode, f, ensure_ascii=False, indent=1)

print(f'seed: {len(escolas)} | matched (kml): {len(matched)} | geocode: {len(geocode)}')
print()
print('--- matcheados por proximidade ---')
for k, v in matched.items():
    if v['origem'] == 'kml-proximidade':
        print(f'  {k} <- {v["nome_kml"]}')
print()
print('--- pendentes de geocode ---')
for k, p in sorted(geocode.items()):
    print(f'  {p}')
