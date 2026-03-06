import os
import re
import streamlit as st
import pandas as pd
from unidecode import unidecode
import altair as alt
from fpdf import FPDF
from datetime import datetime

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="PDAF - Gabinete Aba Reta", layout="wide", initial_sidebar_state="collapsed")

if 'compact_mode' not in st.session_state:
    st.session_state.compact_mode = False

# --- FUNÇÕES DE SUPORTE ---
def normalizar_texto(texto: object) -> str:
    if pd.isna(texto) or texto is None: return ""
    return unidecode(str(texto)).upper().strip()

def compute_modalidade(name: str) -> str:
    s = normalizar_texto(name)
    if s.startswith('CEM INTEGRADO') or s == 'CEMI': return 'CEMI'
    parts = s.split()
    return parts[0] if parts else ''

def to_float_safe(v) -> float:
    if pd.isna(v): return 0.0
    if isinstance(v, (int, float)): return float(v)
    s = str(v).strip().replace('R$', '').replace(' ', '')
    if s == '': return 0.0
    if s.count('.') > 0 and s.count(',') > 0 and s.rfind(',') > s.rfind('.'):
        s = s.replace('.', '').replace(',', '.')
    else:
        s = s.replace(',', '.')
    try: return float(re.sub(r'[^0-9\-\.]', '', s))
    except: return 0.0

# --- CLASSE PARA GERAR O PDF ---
class PDFReport(FPDF):
    def header(self):
        self.set_font("Arial", "B", 12)
        self.cell(0, 10, "GABINETE ABA RETA - RELATÓRIO DE PDAF", border=False, ln=True, align="C")
        self.set_font("Arial", "", 9)
        self.cell(0, 5, f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}", border=False, ln=True, align="C")
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_font("Arial", "I", 8)
        self.cell(0, 10, f"Página {self.page_no()}/{{nb}} - PDAF Gabinete Max Maciel", align="C")

def gerar_pdf(dataframe, total_val, escolas_count):
    pdf = PDFReport()
    pdf.add_page()
    
    # Resumo do Relatório
    pdf.set_font("Arial", "B", 10)
    pdf.set_fill_color(240, 240, 240)
    pdf.cell(0, 10, "RESUMO DOS INVESTIMENTOS FILTRADOS", ln=True, fill=True)
    pdf.set_font("Arial", "", 10)
    pdf.cell(0, 8, f"Total Investido: R$ {total_val:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'), ln=True)
    pdf.cell(0, 8, f"Escolas Beneficiadas: {escolas_count}", ln=True)
    pdf.ln(5)

    # Cabeçalho da Tabela
    pdf.set_font("Arial", "B", 8)
    pdf.set_fill_color(31, 41, 55) 
    pdf.set_text_color(255, 255, 255)
    
    # Ajustei as larguras: Unidade Escolar agora tem 70mm para caber o nome
    # Ano(15) + Regional(30) + Escola(70) + Valor(35) + Data(40) = 190mm (perfeito para A4)
    cols = [("Ano", 15), ("Regional", 30), ("Unidade Escolar", 70), ("Valor (R$)", 35), ("Data Pag.", 40)]
    
    for col_name, width in cols:
        pdf.cell(width, 8, col_name, border=1, align="C", fill=True)
    pdf.ln()

    # Linhas da Tabela
    pdf.set_font("Arial", "", 7)
    pdf.set_text_color(0, 0, 0)
    
    for _, row in dataframe.iterrows():
        # Tratar dados nulos para não dar erro no PDF
        ano = str(row.get('Ano', ''))
        cre = str(row.get('CRE', ''))
        escola = str(row.get('Unidade Escolar', ''))[:45] # Limita caracteres para não vazar a célula
        valor = f"{row.get('Valor_Num', 0):,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
        data_pag = str(row.get('Data pagamento', '')) if pd.notna(row.get('Data pagamento')) else "-"

        # Desenha as células na mesma ordem do cabeçalho
        pdf.cell(15, 7, ano, border=1, align="C")
        pdf.cell(30, 7, cre, border=1)
        pdf.cell(70, 7, escola, border=1)
        pdf.cell(35, 7, valor, border=1, align="R")
        pdf.cell(40, 7, data_pag, border=1, align="C")
        pdf.ln()

    return bytes(pdf.output())

# --- CARREGAMENTO DE DADOS ---
@st.cache_data
# --- CARREGAMENTO DE DADOS (CORRIGIDO) ---
@st.cache_data
def load_all_data(file_mtimes: tuple):
    csv_files = [('PDAF2023.csv', 2023), ('PDAF2024.csv', 2024), ('PDAF2025.csv', 2025)]
    frames = []
    for path, ano in csv_files:
        if not os.path.exists(path): continue
        try:
            df_temp = pd.read_csv(path, sep=';', encoding='utf-8')
            if df_temp.shape[1] <= 2: df_temp = pd.read_csv(path, sep=',', encoding='utf-8')
        except:
            df_temp = pd.read_csv(path, sep=None, engine='python', encoding='utf-8')
        
        df_temp['Ano'] = ano
        val_col = next((c for c in ['Valor da Emenda', 'Valor', 'Total', 'Montante'] if c in df_temp.columns), None)
        if not val_col:
            for c in df_temp.columns:
                if 'VAL' in c.upper() or 'TOTAL' in c.upper(): val_col = c; break
        
        df_temp['Valor da Emenda'] = df_temp[val_col] if val_col else 0
        df_temp['Unidade Escolar'] = df_temp.get('Unidade Escolar', df_temp.get('Escola', 'N/A'))
        df_temp['CRE'] = df_temp.get('CRE', df_temp.get('Regional', 'N/A'))
        df_temp['Data pagamento'] = df_temp.get('Data pagamento', df_temp.get('Data', ''))
        
        frames.append(df_temp[['Ano', 'CRE', 'Unidade Escolar', 'Valor da Emenda', 'Data pagamento']])
    
    if not frames: return pd.DataFrame()
    
    df_result = pd.concat(frames, ignore_index=True)
    df_result['Valor_Num'] = df_result['Valor da Emenda'].apply(to_float_safe)
    df_result['Unidade_Busca'] = df_result['Unidade Escolar'].apply(normalizar_texto)
    df_result['CRE_Normalizada'] = df_result['CRE'].apply(normalizar_texto)
    
    # Tratamento de Datas para os Gráficos (Movido para dentro da função)
    df_result['Data_DT'] = pd.to_datetime(df_result['Data pagamento'], dayfirst=True, errors='coerce')
    df_result['Mes_Ano'] = df_result['Data_DT'].dt.to_period('M').astype(str)
    
    return df_result

# Monitora os arquivos para atualizar o cache se algum mudar
paths = ['PDAF2023.csv', 'PDAF2024.csv', 'PDAF2025.csv']
key = tuple(os.path.getmtime(p) if os.path.exists(p) else 0 for p in paths)
df = load_all_data(key)
# --- CSS PERSONALIZADO ---
st.markdown(
    """
    <style>
    .header-container {
        text-align: center;
        padding: 15px;
        background-color: #1f2937;
        border-bottom: 4px solid #ff6a00;
        border-radius: 0 0 10px 10px;
        margin-bottom: 25px;
    }
    .main-title { color: #ff6a00; font-weight: 800; font-size: 32px; margin: 0; }
    .sub-title { color: #ffffff; font-size: 14px; opacity: 0.9; }

    [data-testid="stMetric"] { 
        background-color: #1f2937 !important; 
        border-radius: 8px !important; 
        padding: 15px !important;
        border-bottom: 4px solid #ff6a00 !important; 
        box-shadow: 0 4px 6px rgba(0,0,0,0.3) !important;
    }

    [data-testid="stMetric"] [data-testid="stMetricLabel"] p {
        color: #ff6a00 !important;
        font-weight: 700 !important;
        font-size: 1.1rem !important;
    }
    
    [data-testid="stMetric"] [data-testid="stMetricValue"] div {
        color: #ffffff !important;
        font-weight: 800 !important;
    }

    .stCheckbox label p {
        color: black !important;
        font-weight: 600 !important;
    }

    #MainMenu, header, footer { visibility: hidden; }
    </style>

    <div class="header-container">
        <div class="main-title">SISTEMA DE VISUALIZAÇÃO DE PDAF</div>
        <div class="sub-title">GABINETE ABA RETA</div>
    </div>
    """,
    unsafe_allow_html=True,
)

# --- CONTROLE SUPERIOR ---
c_space, c_toggle = st.columns([8, 2])
with c_toggle:
    compact = st.checkbox('📱 Modo Celular', value=st.session_state.compact_mode, key="compact_toggle")
    st.session_state.compact_mode = compact

# --- FILTROS ---
df['Modalidade'] = df['Unidade Escolar'].apply(compute_modalidade)

with st.container():
    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        sel_anos = st.multiselect("📅 Anos", options=sorted(df['Ano'].unique(), reverse=True))
    with col2:
        df_y = df[df['Ano'].isin(sel_anos)] if sel_anos else df
        sel_cres = st.multiselect("📍 Regionais", options=sorted(df_y['CRE'].dropna().unique()))
    with col3:
        df_yc = df_y[df_y['CRE'].isin(sel_cres)] if sel_cres else df_y
        sel_schools = st.multiselect("🏫 Escolas", options=sorted(df_yc['Unidade Escolar'].unique()))

busca_geral = st.text_input("🔎 Busca Rápida", placeholder="Digite o nome da escola ou CRE...")

# Lógica de Filtro
df_f = df.copy()
if sel_anos: df_f = df_f[df_f['Ano'].isin(sel_anos)]
if sel_cres: df_f = df_f[df_f['CRE'].isin(sel_cres)]
if sel_schools: df_f = df_f[df_f['Unidade Escolar'].isin(sel_schools)]
if busca_geral:
    p = normalizar_texto(busca_geral)
    df_f = df_f[df_f['Unidade_Busca'].str.contains(p, na=False) | df_f['CRE_Normalizada'].str.contains(p, na=False)]

# --- DASHBOARD DE MÉTRICAS ---
st.write("")
m1, m2, m3 = st.columns(3)
total_val = df_f['Valor_Num'].sum()
escolas_contagem = df_f['Unidade_Busca'].nunique()

m1.metric("TOTAL INVESTIDO", f"R$ {total_val:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'))
m2.metric("ESCOLAS BENEFICIADAS", f"{escolas_contagem}")
m3.metric("TOTAL DE REPASSES", f"{len(df_f)}")

# --- TABELA E GRÁFICOS ---
st.write("")
tab1, tab2 = st.tabs(["📋 Lista de Repasses", "📊 Análise Gráfica"])

with tab1:
    if compact:
        cols_view = ['Ano', 'Unidade Escolar', 'Valor da Emenda']
    else:
        cols_view = ['Ano', 'CRE', 'Unidade Escolar', 'Valor da Emenda', 'Data pagamento']
    
    df_display = df_f[cols_view].copy()
    
    st.dataframe(
        df_display.sort_values(['Unidade Escolar'], ascending=[True]),
        use_container_width=True,
        hide_index=True,
        height=300 if compact else 500
    )
    
# --- AQUI VOCÊ COLA A LÓGICA DO NOME DO ARQUIVO ---
    filtro_nome = []

    def limpar_string(txt):
        if not txt or txt == "N/A": return ""
        txt = unidecode(str(txt))
        return re.sub(r'[^a-zA-Z0-9]', '', txt).strip()

    if sel_anos:
        filtro_nome.append(f"Anos_{'_'.join(map(str, sel_anos))}")

    if sel_cres:
        cres_limpas = [limpar_string(c) for c in sel_cres if limpar_string(c)]
        if cres_limpas:
            filtro_nome.append(f"CRE_{'_'.join(cres_limpas)}")

    if sel_schools:
        esc_limpas = [limpar_string(e)[:15] for e in sel_schools[:2] if limpar_string(e)]
        if esc_limpas:
            txt_esc = f"Escolas_{'_'.join(esc_limpas)}"
            if len(sel_schools) > 2: txt_esc += "_etc"
            filtro_nome.append(txt_esc)

    if busca_geral:
        busca_slug = limpar_string(busca_geral)[:15]
        if busca_slug:
            filtro_nome.append(f"Busca_{busca_slug}")

    prefixo = "Relatorio_PDAF"
    detalhes = f"_{'_'.join(filtro_nome)}" if filtro_nome else "_Geral"
    if len(detalhes) > 120: detalhes = detalhes[:115] + "_resumo"

    data_hoje = datetime.now().strftime('%d_%m_%y')
    nome_arquivo_final = f"{prefixo}{detalhes}_{data_hoje}.pdf"


# --- BOTÃO DE DOWNLOAD COM A KEY E O NOME CORRETOS ---
    if not df_f.empty:
        try:
            # Chama a função gerar_pdf que ajustamos antes
            pdf_data = gerar_pdf(df_f.sort_values(['Unidade Escolar']), total_val, escolas_contagem)
            
            st.download_button(
                label="📄 Gerar Relatório PDF (Filtros Atuais)",
                data=pdf_data,
                file_name=nome_arquivo_final,
                mime="application/pdf",
                use_container_width=True,
                key="btn_download_pdf_pdaf"  # A key evita o erro de ID duplicado
            )
        except Exception as e:
            st.error(f"Erro ao gerar PDF: {e}")



with tab2:
    if not df_f.empty:
        col_graf1, col_graf2 = st.columns(2)

        with col_graf1:
            st.subheader("📍 Top 10 Regionais (R$)")
            chart_cre = alt.Chart(
                df_f.groupby('CRE')['Valor_Num'].sum().reset_index().nlargest(10, 'Valor_Num')
            ).mark_bar(color='#ff6a00', cornerRadiusTopRight=5, cornerRadiusBottomRight=5).encode(
                x=alt.X('Valor_Num:Q', title="Total Acumulado (R$)"),
                y=alt.Y('CRE:N', sort='-x', title="Regional"),
                tooltip=[alt.Tooltip('CRE', title='Regional'), alt.Tooltip('Valor_Num', title='Total (R$)', format=',.2f')]
            ).properties(height=400)
            st.altair_chart(chart_cre, use_container_width=True)

        # Gráfico de Comparação Anual (Crescimento por Ano)
        st.write("---")
        st.subheader("📊 Comparativo Total por Ano")
        df_ano = df_f.groupby('Ano')['Valor_Num'].sum().reset_index()
        
        chart_ano = alt.Chart(df_ano).mark_bar(size=60, color='#1f2937').encode(
            x=alt.X('Ano:O', title="Ano"),
            y=alt.Y('Valor_Num:Q', title="Total Investido (R$)"),
            text=alt.Text('Valor_Num:Q', format=',.2f')
        ).properties(height=300)
        
        # Adiciona os rótulos de texto sobre as barras
        text_ano = chart_ano.mark_text(dy=-10, color='black', fontWeight='bold')
        
        st.altair_chart(chart_ano + text_ano, use_container_width=True)

    else:
        st.info("Utilize os filtros acima para gerar os gráficos comparativos.")

st.markdown("<br><br><center><small style='color: gray;'>Gabinete Aba Reta | Desenvolvido por Caio Henrique Machado</small></center>", unsafe_allow_html=True)