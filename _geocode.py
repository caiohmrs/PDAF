# -*- coding: utf-8 -*-
"""Geocodifica as escolas pendentes via Nominatim (OSM), com cache resumivel.
Fallback: centroide da regiao. Saida: geocode_cache.json"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

PDAF = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(PDAF, 'geocode_cache.json')
PEND = os.path.join(PDAF, 'geocode_pendentes.json')

UA = 'PDAF-KML/1.0 (atualizacao de mapa de escolas; contato: caiohmrs@gmail.com)'
DELAY = 1.15  # Nominatim: max 1 req/s

# expansao de prefixos para montar queries melhores
EXPANDE = {
    'EC': 'Escola Classe', 'CEF': 'Centro de Ensino Fundamental',
    'CED': 'Centro Educacional', 'CEM': 'Centro de Ensino Medio',
    'CEI': 'Centro de Educacao Infantil', 'CEE': 'Centro de Ensino Especial',
    'CIL': 'Centro Interescolar de Linguas', 'JI': 'Jardim de Infancia',
    'EP': 'Escola Parque', 'CEMI': 'Centro de Ensino Medio Integrado',
    'CAIC': 'CAIC', 'CEJAEP': 'CEJAEP', 'CEP': 'Centro de Educacao Profissional',
}

def expandir(padrao):
    p = padrao.strip()
    for k, v in EXPANDE.items():
        if p.upper().startswith(k + ' '):
            return v + p[len(k):]
    return p

def geocode(q):
    url = 'https://nominatim.openstreetmap.org/search?format=json&limit=1&q=' + urllib.parse.quote(q)
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode('utf-8'))
    if data:
        return float(data[0]['lat']), float(data[0]['lon']), data[0].get('display_name', '')
    return None

def queries_para(padrao, regiao):
    p = padrao.strip()
    ex = expandir(p)
    qs = [f'{p}, Brasilia, DF', f'{ex}, Brasilia, DF', f'{p}, Distrito Federal',
          f'{ex}, Distrito Federal']
    if regiao and regiao.upper() not in p.upper():
        qs.append(f'{p}, {regiao}, Distrito Federal')
    return qs

cache = {}
if os.path.exists(CACHE):
    with open(CACHE, encoding='utf-8') as f:
        cache = json.load(f)

with open(PEND, encoding='utf-8') as f:
    pend = json.load(f)  # chave canonical -> padrao

REGOES = {
    'CEILANDIA': ('Ceilandia, Distrito Federal, Brasil',),
    'GAMA': ('Gama, Distrito Federal, Brasil',),
    'PLANALTINA': ('Planaltina, Distrito Federal, Brasil',),
    'GUARA': ('Guara, Distrito Federal, Brasil',),
    'TAGUATINGA': ('Taguatinga, Distrito Federal, Brasil',),
    'SAMAMBAIA': ('Samambaia, Distrito Federal, Brasil',),
    'SANTA MARIA': ('Santa Maria, Distrito Federal, Brasil',),
    'SOBRADINHO': ('Sobradinho, Distrito Federal, Brasil',),
    'PARANOA': ('Paranoa, Distrito Federal, Brasil',),
    'ITAPOA': ('Itapoa, Distrito Federal, Brasil',),
    'BRAZLANDIA': ('Brazlandia, Distrito Federal, Brasil',),
    'SAO SEBASTIAO': ('Sao Sebastiao, Distrito Federal, Brasil',),
    'RECANTO DAS EMAS': ('Recanto das Emas, Distrito Federal, Brasil',),
    'NUCLEO BANDEIRANTE': ('Nucleo Bandeirante, Distrito Federal, Brasil',),
    'CRUZEIRO': ('Cruzeiro, Distrito Federal, Brasil',),
    'PLANO PILOTO': ('Plano Piloto, Brasilia, Distrito Federal, Brasil',),
    'SOL NASCENTE': ('Sol Nascente, Ceilandia, Distrito Federal, Brasil',),
    'VICENTE PIRES': ('Vicente Pires, Distrito Federal, Brasil',),
    'RIACHO FUNDO': ('Riacho Fundo, Distrito Federal, Brasil',),
    'CANDANGOLANDIA': ('Candangolandia, Distrito Federal, Brasil',),
    'ARAPOANGA': ('Arapoanga, Planaltina, Distrito Federal, Brasil',),
}

def regiao_de(padrao):
    n = padrao.upper()
    for r in sorted(REGOES, key=len, reverse=True):
        if r in n:
            return r
    return None

def centroide_regiao(r):
    if r in cache.get('__regioes__', {}):
        return cache['__regioes__'][r]
    for q in REGOES.get(r, (f'{r}, Distrito Federal, Brasil',)):
        try:
            res = geocode(q)
            if res:
                cache.setdefault('__regioes__', {})[r] = res
                return res
        except Exception as e:
            print(f'  [regiao {r}] erro: {e}', flush=True)
        time.sleep(DELAY)
    return None

print(f'{len(pend)} escolas pendentes de geocode', flush=True)
ok = 0
aprox = 0
falhou = []
for i, (key, padrao) in enumerate(sorted(pend.items())):
    if key in cache:
        ok += 1
        continue
    reg = regiao_de(padrao)
    resultado = None
    for q in queries_para(padrao, reg):
        try:
            res = geocode(q)
        except Exception as e:
            print(f'  [{padrao}] erro em {q!r}: {e}', flush=True)
            res = None
        time.sleep(DELAY)
        if res:
            resultado = {'lat': res[0], 'lon': res[1], 'endereco': res[2], 'query': q, 'aprox': False}
            break
    if not resultado and reg:
        c = centroide_regiao(reg)
        if c:
            resultado = {'lat': c[0], 'lon': c[1], 'endereco': f'centroide de {reg}', 'query': 'regiao', 'aprox': True}
    if resultado:
        cache[key] = resultado
        ok += 1
        if resultado['aprox']:
            aprox += 1
        print(f'  [{i+1}/{len(pend)}] OK {padrao} -> {resultado["lat"]:.5f},{resultado["lon"]:.5f}'
              + (' (aprox)' if resultado['aprox'] else ''), flush=True)
    else:
        falhou.append(padrao)
        print(f'  [{i+1}/{len(pend)}] FALHOU {padrao}', flush=True)
    if (i + 1) % 10 == 0:
        with open(CACHE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=1)
        print(f'  ...checkpoint {i+1}/{len(pend)}', flush=True)

with open(CACHE, 'w', encoding='utf-8') as f:
    json.dump(cache, f, ensure_ascii=False, indent=1)

print()
print(f'FIM: geocodificados/ok={ok} | aprox={aprox} | falhou={len(falhou)}')
if falhou:
    print('Falharam:', falhou)
