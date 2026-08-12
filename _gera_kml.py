# -*- coding: utf-8 -*-
"""Gera emendas_mapa.kml atualizado a partir do seed + coords (KML antigo + geocode)."""
import contextlib
import csv
import io
import importlib.util
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

PDAF = os.path.dirname(os.path.abspath(__file__))
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

def to_float(v):
    try:
        return float(v) if isinstance(v, (int, float)) else float(str(v).replace('.', '').replace(',', '.'))
    except Exception:
        return 0.0

def brl(v):
    return f"R$ {v:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

# ---------- coords ----------
with open(PDAF + r'\coords_matched.json', encoding='utf-8') as f:
    matched = json.load(f)  # key -> {'coord': 'lon,lat,0', ...}
with open(PDAF + r'\geocode_cache.json', encoding='utf-8') as f:
    gcache = json.load(f)

def coord_para(key):
    if key in matched:
        return matched[key]['coord'], False
    if key in gcache and 'lat' in gcache[key]:
        g = gcache[key]
        return f"{g['lon']},{g['lat']},0", bool(g.get('aprox'))
    return None, False

# ---------- seed: valores por (escola, ano, gnd) + cre ----------
with open(PDAF + r'\seed_padronizado.csv', encoding='utf-8-sig') as f:
    rows = list(csv.DictReader(f, delimiter=';'))

valores = {}   # (key, ano, gnd) -> soma
escolas = {}   # key -> {'padrao':..., 'cre':..., 'ra':...}
for r in rows:
    padrao = r['Escola_Padrao'].strip()
    if not padrao:
        continue
    key = canon(padrao)
    if key not in escolas:
        # mesma normalizacao do emendas.py: CRE, fallback RA, upper sem 'CRE '
        cre_raw = (r['CRE'] or '').strip() or (r['RA'] or '').strip()
        cre_norm = re.sub(r'^CRE\s+', '', mod.norm(cre_raw)) if cre_raw else ''
        escolas[key] = {'padrao': padrao, 'cre': cre_norm, 'ra': (r['RA'] or '').strip()}
    ano = int(float(r['Ano']))
    gnd = (r['GND'] or '').strip() or '?'
    v = to_float(r['Valor empenhado'] or r['Valor pago'] or r['Valor Indicado'])
    valores[(key, ano, gnd)] = valores.get((key, ano, gnd), 0.0) + v

# ---------- descricao ----------
def descricao(key):
    linhas = []
    por_ano = {}
    for (k, ano, gnd), v in valores.items():
        if k == key:
            por_ano.setdefault(ano, []).append((gnd, v))
    for ano in sorted(por_ano):
        tot = sum(v for _, v in por_ano[ano])
        linhas.append(f'{ano}: {brl(tot)}')
        for gnd, v in sorted(por_ano[ano]):
            linhas.append(f'&#160;&#160;{gnd}: {brl(v)}')
    return '<br/>'.join(linhas)

# ---------- monta KML ----------
def titulo(cre, ra_display):
    """nome da pasta: RA cru (com acentos) quando disponivel, senao titulo do CRE."""
    if ra_display:
        return ra_display
    if not cre:
        return 'Sem Região'
    t = cre.title().replace('Por Do Sol', 'Pôr do Sol')
    return t

STYLE = '''    <Style id="icon-1526-0288D1-normal">
      <IconStyle>
        <color>ffd18802</color>
        <scale>1</scale>
        <Icon>
          <href>https://www.gstatic.com/mapspro/images/stock/503-wht-blank_maps.png</href>
        </Icon>
      </IconStyle>
      <LabelStyle>
        <scale>0</scale>
      </LabelStyle>
    </Style>
    <Style id="icon-1526-0288D1-highlight">
      <IconStyle>
        <color>ffd18802</color>
        <scale>1</scale>
        <Icon>
          <href>https://www.gstatic.com/mapspro/images/stock/503-wht-blank_maps.png</href>
        </Icon>
      </IconStyle>
      <LabelStyle>
        <scale>1</scale>
      </LabelStyle>
    </Style>
    <StyleMap id="icon-1526-0288D1">
      <Pair>
        <key>normal</key>
        <styleUrl>#icon-1526-0288D1-normal</styleUrl>
      </Pair>
      <Pair>
        <key>highlight</key>
        <styleUrl>#icon-1526-0288D1-highlight</styleUrl>
      </Pair>
    </StyleMap>'''

por_cre = {}
sem_coord = []
for key, info in sorted(escolas.items()):
    coord, aprox = coord_para(key)
    if not coord:
        sem_coord.append(info['padrao'])
        continue
    por_cre.setdefault(info['cre'] or 'SEM REGIAO', []).append((key, info, coord, aprox))

out = ['<?xml version="1.0" encoding="UTF-8"?>',
       '<kml xmlns="http://www.opengis.net/kml/2.2">',
       '  <Document>',
       '    <name>Emendas Gab Max Maciel</name>',
       '    <description>PDAF 2023-2026 - valores indicados por ano (fonte: seed_padronizado.csv)</description>',
       STYLE]
n_placemarks = 0
for cre in sorted(por_cre):
    membros = por_cre[cre]
    ra_disp = next((m[1]['ra'] for m in membros if m[1]['ra']), '')
    out.append(f'    <Folder>')
    out.append(f'      <name>{escape(titulo(cre, ra_disp))}</name>')
    for key, info, coord, aprox in membros:
        n_placemarks += 1
        d = descricao(key)
        if aprox:
            d += '<br/><i>(coordenada aproximada da região)</i>'
        out.append('      <Placemark>')
        out.append(f'        <name>{escape(info["padrao"])}</name>')
        out.append(f'        <description>{d}</description>')
        out.append('        <styleUrl>#icon-1526-0288D1</styleUrl>')
        out.append('        <Point>')
        out.append('          <coordinates>')
        out.append(f'            {coord}')
        out.append('          </coordinates>')
        out.append('        </Point>')
        out.append('      </Placemark>')
    out.append('    </Folder>')
out.append('  </Document>')
out.append('</kml>')

with open(PDAF + r'\emendas_mapa.kml', 'w', encoding='utf-8') as f:
    f.write('\n'.join(out))

print(f'KML gerado: {n_placemarks} placemarks em {len(por_cre)} pastas')
print(f'sem coordenada (omitidos): {len(sem_coord)}')
for s in sem_coord:
    print(f'  - {s}')
