import os
import re
import json
import math
import time
import base64
import io
import textwrap
import zipfile
import urllib.request
import urllib.parse
import unicodedata
import difflib
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from html import escape as html_escape
from html.parser import HTMLParser
from xml.sax.saxutils import escape as xml_escape
from zoneinfo import ZoneInfo
import pandas as pd
import requests
import streamlit as st
import folium
from streamlit_folium import st_folium
from sqlalchemy import text

# =====================================================================
# CONFIGURAÇÕES DE TELA E RELÓGIO (VIRADA DE TURNO)
# =====================================================================
st.set_page_config(page_title="Aproar - Torre de Controle", page_icon="🚚", layout="wide")

FUSO_LOCAL = ZoneInfo("America/Fortaleza")
AGORA_REAL = datetime.now(FUSO_LOCAL)

if AGORA_REAL.hour >= 18:
    DATA_REF_ROTA_DATE = AGORA_REAL.date() + timedelta(days=1)
    DATA_REF_ROTA_STR = (AGORA_REAL + timedelta(days=1)).strftime("%d/%m/%Y")
else:
    DATA_REF_ROTA_DATE = AGORA_REAL.date()
    DATA_REF_ROTA_STR = AGORA_REAL.strftime("%d/%m/%Y")

DATA_HOJE_REAL_STR = AGORA_REAL.strftime("%d/%m/%Y")

# =====================================================================
# MOTOR DE BANCO DE DADOS NA NUVEM (POSTGRESQL / SUPABASE)
# =====================================================================
def get_conn():
    # Puxa a conexão automaticamente dos Secrets do Streamlit
    return st.connection("postgresql", type="sql")

def execute_db(query, params=None):
    if params is None: params = {}
    conn_db = get_conn()
    with conn_db.session as s:
        s.execute(text(query), params)
        s.commit()

def fetch_one(query, params=None):
    if params is None: params = {}
    conn_db = get_conn()
    with conn_db.session as s:
        return s.execute(text(query), params).fetchone()

def fetch_all(query, params=None):
    if params is None: params = {}
    conn_db = get_conn()
    with conn_db.session as s:
        return s.execute(text(query), params).fetchall()

def get_df(query, params=None):
    if params is None: params = {}
    conn_db = get_conn()
    with conn_db.session as s:
        res = s.execute(text(query), params)
        keys = res.keys()
        data = res.fetchall()
        return pd.DataFrame(data, columns=keys)

def save_df_to_db(df, table_name):
    conn_db = get_conn()
    with conn_db.session as s:
        s.execute(text(f"TRUNCATE TABLE {table_name} RESTART IDENTITY"))
        s.commit()
    df.to_sql(table_name, conn_db.engine, if_exists="append", index=False)

@st.cache_data(ttl=30, show_spinner=False)
def carregar_abastecimentos_df():
    return get_df("SELECT * FROM abastecimentos")

@st.cache_data(ttl=30, show_spinner=False)
def carregar_registro_km_df():
    return get_df("SELECT * FROM registro_km")

# =====================================================================
# DICIONÁRIO INTELIGENTE DE SINÔNIMOS E ERROS DE DIGITAÇÃO
# =====================================================================
DICIONARIO_SINONIMOS = {
    "DEPOSITO JP": "JP CONSTRUÇÃO",
    "DEPÓSITO JP": "JP CONSTRUÇÃO",
    "JP CONSTRUCOES": "JP CONSTRUÇÃO",
    "ELETRICA FORTALEZA": "ELÉTRICA FORTALEZA",
}

def remover_acentos(txt):
    if not txt: return ""
    return ''.join(c for c in unicodedata.normalize('NFD', str(txt)) if unicodedata.category(c) != 'Mn')

# --- INJEÇÃO DE CSS CUSTOMIZADO (VISUAL PREMIUM E DASHBOARD CORPORATIVO) ---
def aplicar_estilo_customizado():
    st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
        html, body, [class*="css"], .stMarkdown, .stText, p, div, h1, h2, h3, h4, h5, h6 { font-family: 'Inter', sans-serif !important; color: #e4e8f4; }
        /* Ícones do Streamlit usam uma fonte própria. Forçar Inter nos spans
           fazia nomes como keyboard_arrow_right aparecerem como texto. */
        span[data-testid="stIconMaterial"], .material-symbols-rounded, .material-symbols-outlined {
            font-family: 'Material Symbols Rounded', 'Material Symbols Outlined' !important;
            font-weight: normal !important; font-style: normal !important;
            letter-spacing: normal !important; text-transform: none !important;
            white-space: nowrap !important; word-wrap: normal !important;
        }
        [data-testid="stAppViewContainer"] { background-color: #070913 !important; }
        [data-testid="stSidebar"] { background-color: #0b0e1e !important; border-right: 1px solid rgba(64,116,146,.15) !important; }
        [data-testid="stHeader"] { background-color: rgba(7, 9, 19, 0.8) !important; backdrop-filter: blur(8px); }
        /* Evita que a tela inteira escureça enquanto apenas um trecho é atualizado. */
        [data-stale="true"] { opacity: 1 !important; }
        button[kind="primary"], [data-testid="baseButton-primary"] { background: linear-gradient(135deg, #2563eb, #1d4ed8) !important; color: #ffffff !important; border-radius: 8px !important; border: none !important; font-weight: 600 !important; box-shadow: 0 4px 10px rgba(37, 99, 235, 0.3); transition: all 0.2s ease-in-out; padding: 10px 20px !important; }
        button[kind="primary"]:hover { transform: translateY(-2px); box-shadow: 0 6px 15px rgba(37, 99, 235, 0.5); }
        button[kind="primary"]:disabled { background: #1e293b !important; color: #64748b !important; box-shadow: none !important; transform: none !important; cursor: not-allowed !important; }
        .stTabs [data-baseweb="tab-list"] { gap: 12px; background-color: rgba(18, 21, 48, 0.6); padding: 8px 12px; border-radius: 12px; border: 1px solid rgba(64,116,146,.15); }
        .stTabs [data-baseweb="tab"] { background-color: transparent; border-radius: 8px; color: #8da0b8; padding: 10px 18px; font-weight: 500; transition: all 0.2s ease; border: none !important; }
        .stTabs [data-baseweb="tab"]:hover { color: #ffffff; background-color: rgba(255,255,255,0.05); }
        .stTabs [aria-selected="true"] { background-color: #2563eb !important; color: white !important; box-shadow: 0 2px 8px rgba(37, 99, 235, 0.4); }
        div[data-testid="stMetric"] { background-color: rgba(25, 30, 56, 0.6); backdrop-filter: blur(10px); border: 1px solid rgba(64, 116, 146, 0.25); padding: 20px 25px; border-radius: 14px; box-shadow: 0 8px 20px rgba(0,0,0,0.15); transition: transform 0.2s ease; }
        div[data-testid="stMetric"]:hover { transform: translateY(-3px); border-color: rgba(37, 99, 235, 0.5); }
        div[data-testid="stForm"], div[data-testid="stVerticalBlockBorderWrapper"] { background-color: rgba(18, 21, 48, 0.4) !important; border-radius: 14px !important; padding: 24px !important; border: 1px solid rgba(64,116,146,.2) !important; box-shadow: 0 4px 15px rgba(0,0,0,0.1); }
        div[data-baseweb="input"] > div, div[data-baseweb="select"] > div, div[data-baseweb="textarea"] > div { background-color: rgba(13, 16, 37, 0.8) !important; border: 1px solid rgba(64,116,146,.3) !important; color: #e4e8f4 !important; border-radius: 8px !important; transition: border-color 0.2s; }
        div[data-baseweb="input"] > div:focus-within, div[data-baseweb="select"] > div:focus-within { border-color: #2563eb !important; box-shadow: 0 0 0 1px rgba(37, 99, 235, 0.3) !important; }
        [data-testid="stDataFrame"] { background-color: rgba(18, 21, 48, 0.6) !important; border: 1px solid rgba(64,116,146,.2) !important; border-radius: 12px !important; overflow: hidden; }
        ::-webkit-scrollbar { width: 8px; height: 8px; }
        ::-webkit-scrollbar-track { background: #070913; }
        ::-webkit-scrollbar-thumb { background: #2563eb; border-radius: 4px; }
        ::-webkit-scrollbar-thumb:hover { background: #1d4ed8; }
    </style>
    """, unsafe_allow_html=True)

aplicar_estilo_customizado()

def fragmento_independente(func):
    """Mantém compatibilidade e evita recarregar o aplicativo inteiro por um formulário."""
    return st.fragment(func) if hasattr(st, "fragment") else func

# =====================================================================
# FUNÇÕES DE FORMATAÇÃO E ETA DINÂMICO Waze
# =====================================================================
def parse_time_to_mins(time_str):
    if not time_str: return 0
    try:
        h, m = map(int, time_str.split(':'))
        return h * 60 + m
    except: return 0

def format_time(minutes):
    total = int(round(minutes))
    return f"{total // 60:02d}:{total % 60:02d}"

def format_mins_to_time(mins):
    return f"{int(mins) // 60:02d}:{int(mins) % 60:02d}"

def _limpar_texto_relatorio(valor):
    if valor is None:
        return ""
    if isinstance(valor, (dict, list, tuple, set)):
        valor = json.dumps(valor, ensure_ascii=False, default=str)
    texto = str(valor)
    # Imagens anexadas pelo Trello não agregam ao relatório e deixavam URLs
    # enormes no meio dos materiais.
    texto = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", texto)
    texto = re.sub(r"\s*\|\s*", " • ", texto)
    texto = re.sub(r"[\t\r\n]+", " ", texto)
    texto = re.sub(r"\s{2,}", " ", texto).strip(" •")
    return texto

def _normalizar_tabelas_relatorio(dados):
    """Entrega relatórios limpos, com rótulos amigáveis e sem campos técnicos."""
    itens = [("Dados", dados)] if isinstance(dados, pd.DataFrame) else list((dados or {}).items())
    colunas_tecnicas = {"id", "data_dt", "json_route", "json_locais", "json_geometria", "json_enderecos"}
    nomes_amigaveis = {
        "Urgência": "Prazo",
        "Peso": "Prioridade (1-5)",
        "Tempo_Coleta": "Tempo de coleta (min)",
        "Tempo_Entrega": "Tempo de entrega (min)",
        "obs": "Observação",
        "data": "Data",
        "km": "KM",
        "litros": "Litros",
        "valor_litro": "Valor por litro (R$)",
        "manutencao": "Manutenção (R$)",
        "veiculo": "Veículo",
        "apelido": "Local",
        "endereco": "Endereço",
        "lat": "Latitude",
        "lon": "Longitude",
        "🟢 Início da Rota (Hoje)": "Início da rota (hoje)",
        "Última atualização": "Última atualização",
        "Velocidade (km/h)": "Velocidade (km/h)",
        "obra": "Obra",
        "origem": "Origem",
        "destino": "Destino",
        "materiais": "Materiais",
        "data_conclusao": "Data da conclusão",
        "hora_conclusao": "Hora da conclusão",
    }
    tabelas = []
    for nome, tabela in itens:
        if tabela is None:
            continue
        df = tabela.copy() if isinstance(tabela, pd.DataFrame) else pd.DataFrame(tabela)
        remover = [coluna for coluna in df.columns if str(coluna).strip().lower() in colunas_tecnicas]
        df = df.drop(columns=remover, errors="ignore").rename(columns=nomes_amigaveis)
        for coluna in df.columns:
            if pd.api.types.is_datetime64_any_dtype(df[coluna]):
                df[coluna] = df[coluna].dt.strftime("%d/%m/%Y %H:%M").fillna("")
            elif df[coluna].dtype == "object":
                df[coluna] = df[coluna].map(_limpar_texto_relatorio)
        df = df.dropna(axis=1, how="all")
        df = df.loc[:, [coluna for coluna in df.columns if not (df[coluna].astype(str).str.strip() == "").all()]]
        tabelas.append((str(nome), df.fillna("")))
    return tabelas or [("Dados", pd.DataFrame({"Informação": ["Nenhum registro disponível."]}))]

def _criar_resumo_analitico_relatorio(titulo, tabelas):
    """Cria indicadores úteis de acordo com o assunto e os campos de cada relatório."""
    def normalizar(valor):
        return re.sub(r"[^a-z0-9]+", " ", remover_acentos(str(valor or "")).lower()).strip()

    def localizar_coluna(df, *candidatos):
        mapa = {coluna: normalizar(coluna) for coluna in df.columns}
        procurados = [normalizar(candidato) for candidato in candidatos]
        for procurado in procurados:
            for coluna, nome in mapa.items():
                if nome == procurado:
                    return coluna
        for procurado in procurados:
            for coluna, nome in mapa.items():
                if procurado and procurado in nome:
                    return coluna
        return None

    def numeros(df, *candidatos):
        coluna = localizar_coluna(df, *candidatos)
        if not coluna:
            return pd.Series(dtype="float64")
        if pd.api.types.is_numeric_dtype(df[coluna]):
            return pd.to_numeric(df[coluna], errors="coerce")

        def converter(valor):
            texto = re.sub(r"[^0-9,.-]", "", str(valor or ""))
            if not texto or texto in {"-", ".", ","}:
                return None
            if "," in texto:
                texto = texto.replace(".", "").replace(",", ".")
            try:
                return float(texto)
            except (TypeError, ValueError):
                return None
        return df[coluna].map(converter).astype("float64")

    def minutos_horario(valor):
        encontrado = re.search(r"(?<!\d)(\d{1,2}):(\d{2})(?!\d)", str(valor or ""))
        if not encontrado:
            return None
        hora, minuto = map(int, encontrado.groups())
        return hora * 60 + minuto if hora < 24 and minuto < 60 else None

    def horario_medio(valores):
        minutos = [minuto for minuto in (minutos_horario(valor) for valor in valores) if minuto is not None]
        if not minutos:
            return None
        media = int(round(sum(minutos) / len(minutos)))
        return f"{media // 60:02d}:{media % 60:02d}"

    def duracao_media(chegadas, saidas):
        duracoes = []
        for chegada, saida in zip(chegadas, saidas):
            inicio, fim = minutos_horario(chegada), minutos_horario(saida)
            if inicio is None or fim is None:
                continue
            if fim < inicio:
                fim += 24 * 60
            if 0 <= fim - inicio <= 12 * 60:
                duracoes.append(fim - inicio)
        return sum(duracoes) / len(duracoes) if duracoes else None

    def numero_br(valor, casas=1):
        return f"{float(valor):,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")

    def moeda_br(valor):
        return f"R$ {numero_br(valor, 2)}"

    indicadores = []
    def adicionar(indicador, resultado, leitura=""):
        if resultado is None or (isinstance(resultado, float) and math.isnan(resultado)):
            return
        indicadores.append({"Indicador": indicador, "Resultado": resultado, "Leitura para análise": leitura})

    por_nome = {normalizar(nome): df for nome, df in tabelas}
    titulo_norm = normalizar(titulo)
    tabelas_preenchidas = [(nome, df) for nome, df in tabelas if not df.empty]
    principal = max(tabelas_preenchidas, key=lambda item: len(item[1]))[1] if tabelas_preenchidas else pd.DataFrame()

    if "rastreador" in titulo_norm:
        velocidades = numeros(principal, "Velocidade (km/h)").dropna()
        em_movimento = velocidades[velocidades > 0]
        total = len(principal)
        adicionar("Veículos monitorados", total, "Quantidade de veículos com leitura atual.")
        adicionar("Veículos em movimento", len(em_movimento), f"{numero_br(100 * len(em_movimento) / total, 1)}% da frota monitorada." if total else "")
        adicionar("Veículos parados", total - len(em_movimento), "Veículos com velocidade igual a zero na última leitura.")
        adicionar("Velocidade média geral", f"{numero_br(velocidades.mean(), 1)} km/h" if len(velocidades) else None, "Inclui veículos parados.")
        adicionar("Velocidade média em movimento", f"{numero_br(em_movimento.mean(), 1)} km/h" if len(em_movimento) else None, "Considera somente velocidades acima de zero.")
        inicio_col = localizar_coluna(principal, "Início da rota (hoje)")
        adicionar("Horário médio de saída", horario_medio(principal[inicio_col]) if inicio_col else None, "Média das saídas registradas no dia.")

    elif "demandas ativas" in titulo_norm:
        total = len(principal)
        status_col = localizar_coluna(principal, "Status da rota", "Status")
        status = principal[status_col].astype(str) if status_col else pd.Series([""] * total)
        concluidas = int(status.str.contains(r"entregue|conclu", case=False, regex=True).sum())
        pendentes = total - concluidas
        adicionar("Demandas analisadas", total, "Volume total presente no relatório.")
        adicionar("Taxa de conclusão", f"{numero_br(100 * concluidas / total, 1)}%" if total else "0,0%", "Boa aderência" if total and concluidas / total >= 0.9 else "Atenção às demandas ainda pendentes.")
        adicionar("Demandas concluídas", concluidas)
        adicionar("Demandas pendentes", pendentes)
        prioridade = numeros(principal, "Prioridade (1-5)").dropna()
        adicionar("Prioridade média", numero_br(prioridade.mean(), 2) if len(prioridade) else None, "Quanto maior, mais urgente é o conjunto de demandas.")
        coleta = numeros(principal, "Tempo de coleta (min)").dropna()
        entrega = numeros(principal, "Tempo de entrega (min)").dropna()
        adicionar("Tempo médio de coleta", f"{numero_br(coleta.mean(), 1)} min" if len(coleta) else None)
        adicionar("Tempo médio de entrega", f"{numero_br(entrega.mean(), 1)} min" if len(entrega) else None)
        if len(coleta) and len(entrega):
            adicionar("Tempo médio total por demanda", f"{numero_br(coleta.mean() + entrega.mean(), 1)} min", "Soma das médias de coleta e entrega.")
        prazo_col = localizar_coluna(principal, "Prazo")
        if prazo_col:
            prazos = principal[prazo_col].astype(str)
            adicionar("Demandas vencidas/atrasadas", int(prazos.str.contains(r"vencid|atrasad", case=False, regex=True).sum()), "Prioridade de regularização.")

    elif "roteiro do davi" in titulo_norm:
        resumo = next((df for nome, df in tabelas if normalizar(nome) == "resumo"), pd.DataFrame())
        paradas = next((df for nome, df in tabelas if "paradas" in normalizar(nome)), principal)
        parada_col = localizar_coluna(paradas, "Parada")
        acao_col = localizar_coluna(paradas, "Ação")
        status_col = localizar_coluna(paradas, "Status")
        paradas_operacionais = set()
        if parada_col:
            paradas_operacionais = {str(valor) for valor in paradas[parada_col] if str(valor).strip().isdigit()}
        entregas = paradas[paradas[acao_col].astype(str).str.contains("ENTREGAR", case=False, na=False)].copy() if acao_col else paradas.copy()
        status = entregas[status_col].astype(str) if status_col else pd.Series([""] * len(entregas))
        concluidas = int(status.str.contains(r"conclu|entregue", case=False, regex=True).sum())
        total_demandas = len(entregas)
        km = numeros(resumo, "Distância planejada (km)").dropna()
        km_total = float(km.iloc[0]) if len(km) else None
        adicionar("Paradas operacionais", len(paradas_operacionais), "Não inclui almoço nem retorno à base.")
        adicionar("Demandas previstas", total_demandas)
        adicionar("Taxa de conclusão da rota", f"{numero_br(100 * concluidas / total_demandas, 1)}%" if total_demandas else "0,0%", "Percentual de entregas previstas que tiveram baixa.")
        adicionar("Demandas concluídas", concluidas)
        adicionar("Demandas pendentes", total_demandas - concluidas)
        adicionar("Distância planejada", f"{numero_br(km_total, 1)} km" if km_total is not None else None)
        adicionar("Distância média por parada", f"{numero_br(km_total / len(paradas_operacionais), 1)} km" if km_total is not None and paradas_operacionais else None, "Indicador de dispersão da rota.")
        if not resumo.empty:
            inicio_col = localizar_coluna(resumo, "Início")
            fim_col = localizar_coluna(resumo, "Término previsto")
            inicio = minutos_horario(resumo.iloc[0][inicio_col]) if inicio_col else None
            fim = minutos_horario(resumo.iloc[0][fim_col]) if fim_col else None
            if inicio is not None and fim is not None:
                adicionar("Duração planejada da rota", f"{numero_br((fim - inicio) / 60, 1)} h", "Tempo estimado entre saída e retorno.")

    elif "fechamento individualizado" in titulo_norm:
        resumo = next((df for nome, df in tabelas if normalizar(nome) == "resumo"), principal)
        km = numeros(resumo, "KM").fillna(0).sum()
        combustivel = numeros(resumo, "Combustível (R$)").fillna(0).sum()
        manutencao = numeros(resumo, "Manutenção (R$)").fillna(0).sum()
        custo_total = numeros(resumo, "Custo total (R$)").fillna(0).sum()
        custo_km = custo_total / km if km > 0 else None
        adicionar("Quilometragem total", f"{numero_br(km, 1)} km")
        adicionar("Custo total da frota", moeda_br(custo_total))
        adicionar("Custo médio por KM", moeda_br(custo_km) if custo_km is not None else None, "Dentro da referência de R$ 1,50/km." if custo_km is not None and custo_km <= 1.5 else "Acima da referência de R$ 1,50/km." if custo_km is not None else "")
        adicionar("Total de combustível", moeda_br(combustivel), f"{numero_br(100 * combustivel / custo_total, 1)}% do custo total." if custo_total else "")
        adicionar("Total de manutenção", moeda_br(manutencao), f"{numero_br(100 * manutencao / custo_total, 1)}% do custo total." if custo_total else "")
        gastos = pd.concat([df for nome, df in tabelas if normalizar(nome).startswith("gastos") and not df.empty], ignore_index=True) if any(normalizar(nome).startswith("gastos") and not df.empty for nome, df in tabelas) else pd.DataFrame()
        litros = numeros(gastos, "Litros").dropna()
        adicionar("Litros médios por abastecimento", f"{numero_br(litros.mean(), 1)} L" if len(litros) else None)
        adicionar("Custo médio por lançamento", moeda_br(numeros(gastos, "Total (R$)").dropna().mean()) if len(numeros(gastos, "Total (R$)").dropna()) else None)

    elif "registros e historico da frota" in titulo_norm:
        inicios = next((df for nome, df in tabelas if "inicios de rota" in normalizar(nome)), pd.DataFrame())
        paradas = next((df for nome, df in tabelas if "paradas rastreadas" in normalizar(nome)), pd.DataFrame())
        abastecimentos = next((df for nome, df in tabelas if "abastecimentos" in normalizar(nome)), pd.DataFrame())
        quilometragens = next((df for nome, df in tabelas if "quilometragens" in normalizar(nome)), pd.DataFrame())
        saida_col = localizar_coluna(inicios, "Hora Saída") if not inicios.empty else None
        adicionar("Saídas registradas", len(inicios))
        adicionar("Horário médio de saída", horario_medio(inicios[saida_col]) if saida_col else None, "Permite acompanhar a aderência ao início previsto.")
        adicionar("Paradas rastreadas", len(paradas))
        chegada_col = localizar_coluna(paradas, "Chegada") if not paradas.empty else None
        saida_parada_col = localizar_coluna(paradas, "Saída") if not paradas.empty else None
        media_parada = duracao_media(paradas[chegada_col], paradas[saida_parada_col]) if chegada_col and saida_parada_col else None
        adicionar("Tempo médio por parada", f"{numero_br(media_parada, 1)} min" if media_parada is not None else None, "Considera paradas com chegada e saída registradas.")
        locais_col = localizar_coluna(paradas, "Local") if not paradas.empty else None
        adicionar("Locais distintos visitados", int(paradas[locais_col].astype(str).nunique()) if locais_col else None)
        litros = numeros(abastecimentos, "Litros").dropna()
        valor_litro = numeros(abastecimentos, "Valor por litro (R$)", "valor_litro").dropna()
        manutencao = numeros(abastecimentos, "Manutenção (R$)", "manutencao").fillna(0)
        combustivel_total = float((numeros(abastecimentos, "Litros").fillna(0) * numeros(abastecimentos, "Valor por litro (R$)", "valor_litro").fillna(0)).sum()) if not abastecimentos.empty else 0
        adicionar("Litros médios por abastecimento", f"{numero_br(litros.mean(), 1)} L" if len(litros) else None)
        adicionar("Preço médio do litro", moeda_br(valor_litro.mean()) if len(valor_litro) else None)
        adicionar("Custo total registrado", moeda_br(combustivel_total + manutencao.sum()), "Combustível calculado mais manutenções registradas.")
        kms = numeros(quilometragens, "KM").dropna()
        adicionar("KM total registrado", f"{numero_br(kms.sum(), 1)} km" if len(kms) else None)
        adicionar("KM médio por registro", f"{numero_br(kms.mean(), 1)} km" if len(kms) else None)

    elif "entregas concluidas" in titulo_norm:
        total = len(principal)
        obra_col = localizar_coluna(principal, "Obra")
        destino_col = localizar_coluna(principal, "Destino")
        hora_col = localizar_coluna(principal, "Hora da conclusão", "hora_conclusao")
        obras = int(principal[obra_col].astype(str).nunique()) if obra_col else 0
        destinos = int(principal[destino_col].astype(str).nunique()) if destino_col else 0
        adicionar("Entregas concluídas", total)
        adicionar("Obras atendidas", obras)
        adicionar("Destinos atendidos", destinos)
        adicionar("Média de entregas por obra", numero_br(total / obras, 2) if obras else None, "Ajuda a identificar concentração de atendimento.")
        adicionar("Média de entregas por destino", numero_br(total / destinos, 2) if destinos else None)
        adicionar("Horário médio das conclusões", horario_medio(principal[hora_col]) if hora_col else None)
        if destino_col and total:
            frequencias = principal[destino_col].astype(str).replace("", pd.NA).dropna().value_counts()
            if len(frequencias):
                adicionar("Destino com mais entregas", f"{frequencias.index[0]} ({int(frequencias.iloc[0])})", "Local de maior concentração no período.")

    if not indicadores:
        adicionar("Registros analisados", sum(len(df) for _, df in tabelas), "Total de linhas incluídas no relatório.")
        numericas = principal.select_dtypes(include="number") if not principal.empty else pd.DataFrame()
        for coluna in numericas.columns[:4]:
            serie = pd.to_numeric(numericas[coluna], errors="coerce").dropna()
            adicionar(f"Média de {coluna}", numero_br(serie.mean(), 2) if len(serie) else None)

    return pd.DataFrame(indicadores, columns=["Indicador", "Resultado", "Leitura para análise"])

def _dados_grafico_resumo(df):
    """Seleciona apenas comparações com unidades compatíveis e leitura gerencial clara."""
    if df is None or df.empty or "Indicador" not in df.columns or "Resultado" not in df.columns:
        return None, []

    def normalizar(valor):
        return re.sub(r"[^a-z0-9]+", " ", remover_acentos(str(valor or "")).lower()).strip()

    def valor_numerico(valor):
        if isinstance(valor, (int, float)) and not isinstance(valor, bool):
            return float(valor) if math.isfinite(float(valor)) else None
        texto = str(valor or "").strip()
        encontrado = re.search(r"-?[0-9][0-9.]*([,][0-9]+)?", texto)
        if not encontrado:
            return None
        numero = encontrado.group(0)
        if "," in numero:
            numero = numero.replace(".", "").replace(",", ".")
        try:
            return float(numero)
        except (TypeError, ValueError):
            return None

    valores = {
        normalizar(linha["Indicador"]): (str(linha["Indicador"]), valor_numerico(linha["Resultado"]))
        for _, linha in df.iterrows()
    }
    comparacoes = [
        ("Demandas concluídas", "Demandas pendentes", "Conclusão das demandas"),
        ("Veículos em movimento", "Veículos parados", "Situação da frota"),
        ("Total de combustível", "Total de manutenção", "Composição dos custos"),
        ("Saídas registradas", "Paradas rastreadas", "Atividade operacional registrada"),
        ("Obras atendidas", "Destinos atendidos", "Cobertura das entregas"),
    ]
    for primeiro, segundo, titulo in comparacoes:
        chave_a, chave_b = normalizar(primeiro), normalizar(segundo)
        if chave_a not in valores or chave_b not in valores:
            continue
        itens = [valores[chave_a], valores[chave_b]]
        if all(valor is not None and valor >= 0 for _, valor in itens) and sum(valor for _, valor in itens) > 0:
            return titulo, itens
    return None, []

def _organizar_secoes_relatorio(titulo, tabelas):
    """Separa o resumo e escolhe a tabela operacional principal de cada relatório."""
    def normalizar(valor):
        return re.sub(r"[^a-z0-9]+", " ", remover_acentos(str(valor or "")).lower()).strip()

    resumo = next((df for nome, df in tabelas if normalizar(nome) == "resumo analitico"), pd.DataFrame())
    dados = [(nome, df) for nome, df in tabelas if normalizar(nome) != "resumo analitico"]
    if not dados:
        return resumo, [], None

    titulo_norm = normalizar(titulo)
    indice_principal = None
    preferencias = []
    if "roteiro" in titulo_norm:
        preferencias = ["paradas e demandas", "paradas"]
    elif "fechamento" in titulo_norm:
        preferencias = ["resumo", "gastos"]
    elif "registros e historico" in titulo_norm:
        preferencias = ["paradas rastreadas", "abastecimentos e manutencao"]
    for preferencia in preferencias:
        indice_principal = next((i for i, (nome, _) in enumerate(dados) if preferencia in normalizar(nome)), None)
        if indice_principal is not None:
            break
    if indice_principal is None:
        indice_principal = max(range(len(dados)), key=lambda i: len(dados[i][1]))

    principal = dados[indice_principal]
    ordenadas = [principal] + [item for i, item in enumerate(dados) if i != indice_principal]
    return resumo, ordenadas, principal[0]

def _colunas_relevantes_pdf(df, limite=9):
    """Mantém no PDF as colunas de maior utilidade operacional quando a tabela é muito larga."""
    if df is None or len(df.columns) <= limite:
        return df

    def pontuacao(coluna):
        nome = remover_acentos(str(coluna)).lower()
        regras = [
            ("status", 120), ("situacao", 118), ("data", 115), ("placa", 112),
            ("veiculo", 110), ("obra", 108), ("parada", 106), ("acao", 104),
            ("origem", 102), ("destino", 101), ("local", 100), ("material", 98),
            ("descricao", 96), ("prazo", 94), ("prioridade", 92), ("urgencia", 92),
            ("tempo", 90), ("hora", 89), ("km", 88), ("distancia", 87),
            ("custo", 86), ("valor", 85), ("litro", 84), ("manutencao", 83),
            ("endereco", 80), ("estrategia", 78), ("responsavel", 76),
        ]
        return max((pontos for chave, pontos in regras if chave in nome), default=50)

    posicoes = {coluna: indice for indice, coluna in enumerate(df.columns)}
    escolhidas = sorted(df.columns, key=lambda coluna: (-pontuacao(coluna), posicoes[coluna]))[:limite]
    escolhidas = sorted(escolhidas, key=lambda coluna: posicoes[coluna])
    return df.loc[:, escolhidas]

def _criar_csv_relatorio(tabelas):
    secoes = []
    for nome, df in tabelas:
        tabela = df.copy()
        if "Seção" in tabela.columns:
            tabela = tabela.rename(columns={"Seção": "Seção original"})
        tabela.insert(0, "Seção", nome)
        secoes.append(tabela)
    consolidado = pd.concat(secoes, ignore_index=True, sort=False).fillna("")
    return consolidado.to_csv(index=False, sep=";", decimal=",", lineterminator="\n").encode("utf-8-sig")

def _nome_aba_excel(nome, usados):
    nome_limpo = re.sub(r"[\\/*?:\[\]]", " ", str(nome)).strip() or "Dados"
    nome_limpo = nome_limpo[:31]
    candidato, contador = nome_limpo, 2
    while candidato.lower() in usados:
        sufixo = f" {contador}"
        candidato = f"{nome_limpo[:31-len(sufixo)]}{sufixo}"
        contador += 1
    usados.add(candidato.lower())
    return candidato

def _criar_xlsx_basico(tabelas):
    """Fallback XLSX feito apenas com a biblioteca padrão do Python."""
    def coluna_excel(indice):
        texto = ""
        while indice:
            indice, resto = divmod(indice - 1, 26)
            texto = chr(65 + resto) + texto
        return texto

    def celula_xml(referencia, valor, estilo=0):
        estilo_xml = f' s="{estilo}"' if estilo else ""
        if isinstance(valor, bool):
            return f'<c r="{referencia}" t="b"{estilo_xml}><v>{1 if valor else 0}</v></c>'
        if isinstance(valor, (int, float)) and not isinstance(valor, bool) and math.isfinite(float(valor)):
            return f'<c r="{referencia}"{estilo_xml}><v>{valor}</v></c>'
        texto = xml_escape(str(valor), {'"': '&quot;'})
        return f'<c r="{referencia}" t="inlineStr"{estilo_xml}><is><t xml:space="preserve">{texto}</t></is></c>'

    usados, abas = set(), []
    for nome, df in tabelas:
        nome_aba = _nome_aba_excel(nome, usados)
        linhas = [list(map(str, df.columns))] + df.values.tolist()
        linhas_xml = []
        for numero_linha, valores in enumerate(linhas, start=1):
            celulas = "".join(
                celula_xml(f"{coluna_excel(indice)}{numero_linha}", valor, 1 if numero_linha == 1 else 0)
                for indice, valor in enumerate(valores, start=1)
            )
            linhas_xml.append(f'<row r="{numero_linha}">{celulas}</row>')
        ultima_coluna = coluna_excel(max(1, len(df.columns)))
        ultima_linha = max(1, len(linhas))
        larguras = "".join(
            f'<col min="{i}" max="{i}" width="{min(45, max(12, len(str(col)) + 3))}" customWidth="1"/>'
            for i, col in enumerate(df.columns, start=1)
        )
        filtro = f'<autoFilter ref="A1:{ultima_coluna}{ultima_linha}"/>' if len(df.columns) else ""
        planilha = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f'<dimension ref="A1:{ultima_coluna}{ultima_linha}"/>'
            '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
            f'<cols>{larguras}</cols><sheetData>{"".join(linhas_xml)}</sheetData>{filtro}</worksheet>'
        )
        abas.append((nome_aba, planilha))

    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as arquivo:
        overrides = "".join(
            f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            for i in range(1, len(abas) + 1)
        )
        arquivo.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            f'{overrides}</Types>')
        arquivo.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            '</Relationships>')
        sheets = "".join(
            f'<sheet name="{xml_escape(nome, {chr(34): "&quot;"})}" sheetId="{i}" r:id="rId{i}"/>'
            for i, (nome, _) in enumerate(abas, start=1)
        )
        arquivo.writestr("xl/workbook.xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f'<sheets>{sheets}</sheets></workbook>')
        relacionamentos = "".join(
            f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>'
            for i in range(1, len(abas) + 1)
        )
        arquivo.writestr("xl/_rels/workbook.xml.rels", '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'{relacionamentos}<Relationship Id="rId{len(abas)+1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
            '</Relationships>')
        arquivo.writestr("xl/styles.xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><color rgb="FFFFFFFF"/><sz val="11"/><name val="Calibri"/></font></fonts>'
            '<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF2563EB"/><bgColor indexed="64"/></patternFill></fill></fills>'
            '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
            '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
            '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/></cellXfs>'
            '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>')
        for i, (_, planilha) in enumerate(abas, start=1):
            arquivo.writestr(f"xl/worksheets/sheet{i}.xml", planilha)
    return saida.getvalue()

def _criar_excel_relatorio(tabelas, titulo="Relatório Operacional"):
    def coluna_data_excel(coluna):
        nome = remover_acentos(str(coluna)).lower().strip()
        if "quantidade" in nome or "contagem" in nome:
            return False
        return (
            "data" in nome or nome.startswith("dt.") or nome.startswith("dt ")
            or "limite d+4" in nome or "prazo final" in nome
        )

    def preparar_datas_excel(df):
        preparado = df.copy()
        for coluna in preparado.columns:
            if not coluna_data_excel(coluna):
                continue
            try:
                convertida = pd.to_datetime(preparado[coluna], dayfirst=True, errors="coerce", format="mixed")
            except (TypeError, ValueError):
                convertida = pd.to_datetime(preparado[coluna], dayfirst=True, errors="coerce")
            preenchidos = preparado[coluna].astype(str).str.strip() != ""
            if preenchidos.any() and convertida[preenchidos].notna().mean() >= 0.8:
                preparado[coluna] = convertida
        return preparado

    def coluna_identificador(coluna):
        nome = remover_acentos(str(coluna)).lower()
        return any(chave in nome for chave in ("numero da oc", "numero da cotacao", "solicitacoes"))

    resumo_analitico, secoes_dados, _ = _organizar_secoes_relatorio(titulo, tabelas)
    tabelas_excel = list(secoes_dados)
    if not resumo_analitico.empty:
        tabelas_excel.insert(1 if tabelas_excel else 0, ("Resumo Analítico", resumo_analitico))
    if not tabelas_excel:
        tabelas_excel = list(tabelas)

    try:
        saida = io.BytesIO()
        with pd.ExcelWriter(
            saida, engine="xlsxwriter", date_format="dd/mm/yyyy", datetime_format="dd/mm/yyyy",
            engine_kwargs={"options": {"strings_to_formulas": False, "strings_to_urls": False}},
        ) as escritor:
            workbook = escritor.book
            titulo_fmt = workbook.add_format({"bold": True, "font_size": 15, "font_color": "#FFFFFF", "bg_color": "#08B7B7", "align": "center", "valign": "vcenter"})
            meta_fmt = workbook.add_format({"font_size": 9, "font_color": "#64748B", "italic": True})
            texto_fmt = workbook.add_format({"valign": "top", "text_wrap": True, "border": 1, "border_color": "#20C4C4"})
            moeda_fmt = workbook.add_format({"num_format": 'R$ #,##0.00', "valign": "top", "border": 1, "border_color": "#20C4C4"})
            numero_fmt = workbook.add_format({"num_format": '#,##0.00', "valign": "top", "border": 1, "border_color": "#20C4C4"})
            data_fmt = workbook.add_format({"num_format": 'dd/mm/yyyy', "valign": "top", "border": 1, "border_color": "#20C4C4"})
            identificador_fmt = workbook.add_format({"num_format": "@", "valign": "top", "text_wrap": True, "border": 1, "border_color": "#20C4C4"})
            cartao_rotulo_fmt = workbook.add_format({"bold": True, "font_size": 8.5, "font_color": "#FFFFFF", "bg_color": "#4B4B4B", "align": "center", "valign": "vcenter", "text_wrap": True, "border": 1, "border_color": "#FFFFFF"})
            cartao_valor_fmt = workbook.add_format({"bold": True, "font_size": 13, "font_color": "#334155", "bg_color": "#F3FAF3", "align": "center", "valign": "vcenter", "text_wrap": True, "border": 1, "border_color": "#B7D9D9"})
            subtitulo_fmt = workbook.add_format({"bold": True, "font_size": 11, "font_color": "#FFFFFF", "bg_color": "#08B7B7", "align": "left", "valign": "vcenter"})
            cabecalho_tabela_fmt = workbook.add_format({"bold": True, "font_size": 9, "font_color": "#FFFFFF", "bg_color": "#08B7B7", "align": "center", "valign": "vcenter", "text_wrap": True, "border": 1, "border_color": "#FFFFFF"})
            usados = set()

            for ordem_item, (nome, df_original) in enumerate(tabelas_excel):
                df = preparar_datas_excel(df_original)
                nome_aba = _nome_aba_excel(nome, usados)
                eh_resumo_analitico = nome_aba == "Resumo Analítico"
                eh_principal = ordem_item == 0 and not eh_resumo_analitico
                inicio_tabela = 18 if eh_resumo_analitico else 6 if eh_principal else 3
                df.to_excel(escritor, sheet_name=nome_aba, index=False, startrow=inicio_tabela)
                worksheet = escritor.sheets[nome_aba]
                ultima_coluna = max(0, len(df.columns) - 1)
                if eh_resumo_analitico:
                    worksheet.merge_range(0, 0, 0, 13, f"{titulo.upper()} - ANÁLISES", titulo_fmt)
                    worksheet.merge_range(1, 0, 1, 13, f"Gerado em {datetime.now(FUSO_LOCAL).strftime('%d/%m/%Y às %H:%M')} • {len(df)} indicador(es)", meta_fmt)
                    worksheet.set_row(0, 29)
                    worksheet.set_row(1, 19)
                    worksheet.hide_gridlines(2)
                    worksheet.set_landscape()
                    worksheet.fit_to_pages(1, 0)
                    worksheet.set_margins(0.35, 0.35, 0.55, 0.55)
                    worksheet.set_footer("&LAPROAR Engenharia&CResumo analítico&R Página &P de &N")
                    worksheet.set_column(0, 5, 14)
                    worksheet.set_column(6, 6, 2)
                    worksheet.set_column(7, 13, 11)

                    for indice, (_, indicador) in enumerate(df.head(6).iterrows()):
                        linha = 3 + (indice // 2) * 4
                        coluna = 0 if indice % 2 == 0 else 3
                        worksheet.merge_range(linha, coluna, linha, coluna + 2, str(indicador.get("Indicador", "Indicador")), cartao_rotulo_fmt)
                        worksheet.merge_range(linha + 1, coluna, linha + 2, coluna + 2, str(indicador.get("Resultado", "-")), cartao_valor_fmt)
                        worksheet.set_row(linha, 22)
                        worksheet.set_row(linha + 1, 23)
                        worksheet.set_row(linha + 2, 23)

                    titulo_grafico, dados_grafico = _dados_grafico_resumo(df)
                    if dados_grafico:
                        linha_auxiliar = 2
                        worksheet.write(linha_auxiliar, 15, "Categoria")
                        worksheet.write(linha_auxiliar, 16, "Valor")
                        for posicao, (rotulo, valor) in enumerate(dados_grafico, start=1):
                            indice_df = next((i for i, texto_indicador in enumerate(df["Indicador"].astype(str)) if texto_indicador == rotulo), None)
                            linha_origem_excel = inicio_tabela + 2 + indice_df if indice_df is not None else None
                            linha_destino = linha_auxiliar + posicao
                            if linha_origem_excel:
                                worksheet.write_formula(linha_destino, 15, f"=A{linha_origem_excel}", None, rotulo)
                                formula_valor = f'=IFERROR(NUMBERVALUE(SUBSTITUTE(SUBSTITUTE(B{linha_origem_excel},"R$ ",""),"%",""),",","."),B{linha_origem_excel})'
                                worksheet.write_formula(linha_destino, 16, formula_valor, None, valor)
                            else:
                                worksheet.write(linha_destino, 15, rotulo)
                                worksheet.write_number(linha_destino, 16, valor)
                        worksheet.set_column(15, 16, None, None, {"hidden": True})
                        grafico = workbook.add_chart({"type": "doughnut"})
                        pontos = [{"fill": {"color": "#16A34A"}}, {"fill": {"color": "#F59E0B"}}]
                        if "custos" in remover_acentos(titulo_grafico).lower(): pontos = [{"fill": {"color": "#08B7B7"}}, {"fill": {"color": "#F59E0B"}}]
                        grafico.add_series({
                            "name": titulo_grafico,
                            "categories": [nome_aba, linha_auxiliar + 1, 15, linha_auxiliar + len(dados_grafico), 15],
                            "values": [nome_aba, linha_auxiliar + 1, 16, linha_auxiliar + len(dados_grafico), 16],
                            "points": pontos[:len(dados_grafico)],
                            "data_labels": {"percentage": True, "leader_lines": True},
                        })
                        grafico.set_title({"name": titulo_grafico, "name_font": {"size": 12, "bold": True, "color": "#334155"}})
                        grafico.set_hole_size(58)
                        grafico.set_legend({"position": "bottom", "font": {"size": 9}})
                        grafico.set_chartarea({"border": {"none": True}, "fill": {"color": "#FFFFFF"}})
                        grafico.set_plotarea({"border": {"none": True}, "fill": {"color": "#FFFFFF"}})
                        grafico.set_size({"width": 500, "height": 265})
                        worksheet.insert_chart(3, 7, grafico)

                    worksheet.merge_range(16, 0, 16, 13, "Leituras gerenciais e indicadores complementares", subtitulo_fmt)
                    worksheet.set_row(16, 23)
                    if len(df):
                        worksheet.add_table(inicio_tabela, 0, inicio_tabela + len(df), ultima_coluna, {
                            "name": f"Tabela_{len(usados)}_ResumoAnalitico",
                            "style": "Table Style Light 9",
                            "columns": [{"header": str(coluna), "header_format": cabecalho_tabela_fmt} for coluna in df.columns],
                        })
                    worksheet.set_column(0, 0, 34, texto_fmt)
                    worksheet.set_column(1, 1, 22, texto_fmt)
                    worksheet.set_column(2, 2, 52, texto_fmt)
                    worksheet.set_row(inicio_tabela, 26)
                    for linha in range(inicio_tabela + 1, inicio_tabela + 1 + len(df)):
                        worksheet.set_row(linha, 32)
                    worksheet.freeze_panes(inicio_tabela + 1, 0)
                    continue

                largura_modelo = max(ultima_coluna, 5 if eh_principal else ultima_coluna)
                titulo_planilha = titulo.upper() if eh_principal else f"{titulo} - {nome}".upper()
                if largura_modelo:
                    worksheet.merge_range(0, 0, 0, largura_modelo, titulo_planilha, titulo_fmt)
                else:
                    worksheet.write(0, 0, titulo_planilha, titulo_fmt)
                worksheet.write(1, 0, f"Gerado em {datetime.now(FUSO_LOCAL).strftime('%d/%m/%Y às %H:%M')} • {len(df)} registro(s) • Seção: {nome}", meta_fmt)
                worksheet.set_row(0, 27)
                worksheet.set_row(inicio_tabela, 28)
                worksheet.freeze_panes(inicio_tabela + 1, 0)
                worksheet.hide_gridlines(2)
                worksheet.set_landscape()
                worksheet.fit_to_pages(1, 0)
                worksheet.set_margins(0.35, 0.35, 0.55, 0.55)
                worksheet.set_footer("&LAPROAR Engenharia&CRelatório operacional&R Página &P de &N")

                if eh_principal:
                    total_colunas_painel = largura_modelo + 1
                    worksheet.set_column(0, largura_modelo, 14)
                    for indice_kpi, (_, indicador) in enumerate(resumo_analitico.head(6).iterrows()):
                        coluna_inicial = (indice_kpi * total_colunas_painel) // 6
                        coluna_final = ((indice_kpi + 1) * total_colunas_painel) // 6 - 1
                        rotulo = str(indicador.get("Indicador", "Indicador"))
                        resultado = str(indicador.get("Resultado", "-"))
                        if coluna_inicial == coluna_final:
                            worksheet.write(3, coluna_inicial, rotulo, cartao_rotulo_fmt)
                            worksheet.write(4, coluna_inicial, resultado, cartao_valor_fmt)
                        else:
                            worksheet.merge_range(3, coluna_inicial, 3, coluna_final, rotulo, cartao_rotulo_fmt)
                            worksheet.merge_range(4, coluna_inicial, 4, coluna_final, resultado, cartao_valor_fmt)
                    worksheet.set_row(3, 31)
                    worksheet.set_row(4, 34)

                if len(df.columns):
                    if len(df):
                        worksheet.add_table(inicio_tabela, 0, inicio_tabela + len(df), ultima_coluna, {
                            "name": f"Tabela_{len(usados)}_{re.sub(r'[^A-Za-z0-9]', '', nome_aba)[:15] or 'Dados'}",
                            "style": "Table Style Light 9",
                            "columns": [{"header": str(coluna), "header_format": cabecalho_tabela_fmt} for coluna in df.columns],
                        })
                    else:
                        for indice, coluna in enumerate(df.columns):
                            worksheet.write(inicio_tabela, indice, str(coluna), cabecalho_tabela_fmt)

                    for indice, coluna in enumerate(df.columns):
                        valores = df[coluna].astype(str).head(250).tolist()
                        maior = max([len(str(coluna))] + [len(valor) for valor in valores])
                        nome_coluna = remover_acentos(str(coluna)).lower()
                        longa = any(chave in nome_coluna for chave in ("material", "endereco", "observacao", "motivo", "leitura"))
                        if nome_aba == "Resumo Analítico" and nome_coluna == "resultado": largura = 22
                        elif nome_aba == "Resumo Analítico" and "indicador" in nome_coluna: largura = 34
                        else: largura = 52 if longa else min(32, max(12, maior + 2))
                        formato = identificador_fmt if coluna_identificador(coluna) else data_fmt if coluna_data_excel(coluna) else moeda_fmt if "r$" in nome_coluna or "custo" in nome_coluna or "valor" in nome_coluna or "manutencao" in nome_coluna else numero_fmt if nome_coluna in {"km", "litros", "distancia (km)"} else texto_fmt
                        worksheet.set_column(indice, indice, largura, formato)
                        if coluna_identificador(coluna):
                            for deslocamento, valor in enumerate(df[coluna].tolist(), start=inicio_tabela + 1):
                                texto_valor = "" if pd.isna(valor) else str(valor)
                                worksheet.write_string(deslocamento, indice, texto_valor, identificador_fmt)

                    for linha, valores in enumerate(df.astype(str).values.tolist(), start=inicio_tabela + 1):
                        maior_texto = max([len(valor) for valor in valores] + [0])
                        altura = min(72, 18 + 12 * max(0, maior_texto // 70))
                        worksheet.set_row(linha, altura)

                    for indice, coluna in enumerate(df.columns):
                        if "status" in remover_acentos(str(coluna)).lower() and len(df):
                            intervalo = (inicio_tabela + 1, indice, inicio_tabela + len(df), indice)
                            worksheet.conditional_format(*intervalo, {"type": "text", "criteria": "containing", "value": "Dentro", "format": workbook.add_format({"bg_color": "#DCFCE7", "font_color": "#166534"})})
                            worksheet.conditional_format(*intervalo, {"type": "text", "criteria": "containing", "value": "Conclu", "format": workbook.add_format({"bg_color": "#DCFCE7", "font_color": "#166534"})})
                            worksheet.conditional_format(*intervalo, {"type": "text", "criteria": "containing", "value": "Fora", "format": workbook.add_format({"bg_color": "#FEE2E2", "font_color": "#991B1B"})})
                            worksheet.conditional_format(*intervalo, {"type": "text", "criteria": "containing", "value": "Sem Recebimento", "format": workbook.add_format({"bg_color": "#E2E8F0", "font_color": "#334155"})})
                            worksheet.conditional_format(*intervalo, {"type": "text", "criteria": "containing", "value": "Pend", "format": workbook.add_format({"bg_color": "#FEF3C7", "font_color": "#92400E"})})
                        if "observacao" in remover_acentos(str(coluna)).lower() and len(df):
                            intervalo = (inicio_tabela + 1, indice, inicio_tabela + len(df), indice)
                            worksheet.conditional_format(*intervalo, {"type": "text", "criteria": "containing", "value": "corre", "format": workbook.add_format({"bg_color": "#FEF3C7", "font_color": "#92400E"})})
        return saida.getvalue()
    except (ImportError, ModuleNotFoundError):
        pass

    try:
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter
        saida = io.BytesIO()
        with pd.ExcelWriter(saida, engine="openpyxl") as escritor:
            usados = set()
            for ordem_item, (nome, df_original) in enumerate(tabelas_excel):
                df = preparar_datas_excel(df_original)
                nome_aba = _nome_aba_excel(nome, usados)
                eh_resumo_analitico = nome_aba == "Resumo Analítico"
                eh_principal = ordem_item == 0 and not eh_resumo_analitico
                inicio_tabela = 6 if eh_principal else 3
                df.to_excel(escritor, sheet_name=nome_aba, index=False, startrow=inicio_tabela)
                ws = escritor.sheets[nome_aba]
                ultima_coluna = max(6 if eh_principal else 1, len(df.columns))
                ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=ultima_coluna)
                ws.cell(1, 1, titulo.upper() if eh_principal else f"{titulo} - {nome}".upper())
                ws.cell(1, 1).font = Font(bold=True, size=16, color="FFFFFF")
                ws.cell(1, 1).alignment = Alignment(horizontal="center", vertical="center")
                for coluna_titulo in range(1, ultima_coluna + 1): ws.cell(1, coluna_titulo).fill = PatternFill("solid", fgColor="08B7B7")
                tipo_linha = "indicador(es)" if nome_aba == "Resumo Analítico" else "registro(s)"
                ws.cell(2, 1, f"Gerado em {datetime.now(FUSO_LOCAL).strftime('%d/%m/%Y às %H:%M')} • {len(df)} {tipo_linha}")
                ws.cell(2, 1).font = Font(size=9, italic=True, color="64748B")
                if eh_principal:
                    for indice_kpi, (_, indicador) in enumerate(resumo_analitico.head(6).iterrows(), start=1):
                        ws.cell(4, indice_kpi, str(indicador.get("Indicador", "Indicador")))
                        ws.cell(5, indice_kpi, str(indicador.get("Resultado", "-")))
                        ws.cell(4, indice_kpi).font = Font(bold=True, color="FFFFFF", size=9)
                        ws.cell(4, indice_kpi).fill = PatternFill("solid", fgColor="4B4B4B")
                        ws.cell(5, indice_kpi).font = Font(bold=True, color="334155", size=12)
                        ws.cell(5, indice_kpi).fill = PatternFill("solid", fgColor="F3FAF3")
                        ws.cell(4, indice_kpi).alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
                        ws.cell(5, indice_kpi).alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
                linha_cabecalho = inicio_tabela + 1
                ws.freeze_panes = f"A{linha_cabecalho + 1}"
                ws.sheet_view.showGridLines = False
                ws.auto_filter.ref = f"A{linha_cabecalho}:{get_column_letter(max(1, len(df.columns)))}{max(linha_cabecalho, linha_cabecalho + len(df))}"
                for celula in ws[linha_cabecalho]:
                    celula.font = Font(bold=True, color="FFFFFF")
                    celula.fill = PatternFill("solid", fgColor="08B7B7")
                    celula.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
                for indice, coluna in enumerate(df.columns, start=1):
                    valores = df[coluna].astype(str).head(250).tolist()
                    maior = max([len(str(coluna))] + [len(valor) for valor in valores])
                    nome_coluna = remover_acentos(str(coluna)).lower()
                    longa = any(chave in nome_coluna for chave in ("material", "endereco", "observacao", "motivo", "leitura"))
                    if nome_aba == "Resumo Analítico" and nome_coluna == "resultado": largura = 22
                    elif nome_aba == "Resumo Analítico" and "indicador" in nome_coluna: largura = 34
                    else: largura = 52 if longa else min(32, max(12, maior + 2))
                    ws.column_dimensions[get_column_letter(indice)].width = largura
                    for linha in range(linha_cabecalho + 1, linha_cabecalho + 1 + len(df)):
                        ws.cell(linha, indice).alignment = Alignment(vertical="top", wrap_text=True)
                        if coluna_data_excel(coluna): ws.cell(linha, indice).number_format = "dd/mm/yyyy"
                        if coluna_identificador(coluna): ws.cell(linha, indice).number_format = "@"
                if nome_aba == "Resumo Analítico":
                    for linha in range(linha_cabecalho + 1, linha_cabecalho + 1 + len(df)): ws.row_dimensions[linha].height = 32
        return saida.getvalue()
    except (ImportError, ModuleNotFoundError):
        pass
    return _criar_xlsx_basico(tabelas_excel)

def _texto_pdf(valor):
    bytes_texto = str(valor).encode("cp1252", errors="replace")
    return "".join(
        chr(byte) if 32 <= byte <= 126 and chr(byte) not in "\\()" else
        f"\\{chr(byte)}" if chr(byte) in "\\()" else f"\\{byte:03o}"
        for byte in bytes_texto
    )

def _criar_pdf_textual(titulo, tabelas):
    """PDF visual independente de bibliotecas externas, usado como contingência."""
    largura_pagina, altura_pagina = 842.0, 595.0
    margem_x, limite_inferior = 34.0, 42.0
    largura_util = largura_pagina - 2 * margem_x
    cores = {
        "teal": (0.031, 0.718, 0.718),
        "teal_borda": (0.125, 0.769, 0.769),
        "cinza": (0.294, 0.294, 0.294),
        "texto": (0.204, 0.255, 0.333),
        "borda": (0.796, 0.835, 0.882),
        "branco": (1.0, 1.0, 1.0),
        "fundo": (0.973, 0.980, 0.988),
        "verde": (0.867, 0.957, 0.835),
        "amarelo": (0.996, 0.953, 0.780),
        "vermelho": (0.996, 0.792, 0.792),
    }

    def limpo(valor):
        return str(valor).replace("—", "-").replace("–", "-").replace("‑", "-").replace("•", "-").replace("\n", " ").strip()

    def rgb(cor, operador):
        return f"{cor[0]:.3f} {cor[1]:.3f} {cor[2]:.3f} {operador}"

    def retangulo(comandos, x, y, largura, altura, preenchimento, contorno=None, espessura=0.5):
        comandos.append(rgb(preenchimento, "rg"))
        if contorno:
            comandos.extend([rgb(contorno, "RG"), f"{espessura:.2f} w", f"{x:.2f} {y:.2f} {largura:.2f} {altura:.2f} re B"])
        else:
            comandos.append(f"{x:.2f} {y:.2f} {largura:.2f} {altura:.2f} re f")

    def largura_texto(texto, tamanho):
        return len(str(texto)) * tamanho * 0.50

    def escrever(comandos, texto, x, y, tamanho=8, negrito=False, cor=None, alinhamento="esquerda"):
        texto = limpo(texto)
        cor = cor or cores["texto"]
        if alinhamento == "centro":
            x -= largura_texto(texto, tamanho) / 2
        elif alinhamento == "direita":
            x -= largura_texto(texto, tamanho)
        fonte = "F2" if negrito else "F1"
        comandos.extend([
            rgb(cor, "rg"),
            f"BT /{fonte} {tamanho:.2f} Tf {x:.2f} {y:.2f} Td ({_texto_pdf(texto)}) Tj ET",
        ])

    def quebrar_texto(valor, largura, tamanho=7, limite=240):
        texto = limpo(valor)
        if len(texto) > limite:
            texto = texto[:limite - 3].rstrip() + "..."
        caracteres = max(4, int(largura / max(3.5, tamanho * 0.50)))
        return textwrap.wrap(texto, width=caracteres, break_long_words=True, break_on_hyphens=False) or ["-"]

    def escrever_caixa(comandos, valor, x, y, largura, altura, tamanho=7, negrito=False, cor=None, alinhamento="esquerda", limite=240):
        linhas = quebrar_texto(valor, largura - 8, tamanho, limite)
        entrelinha = tamanho + 1.6
        bloco = len(linhas) * entrelinha
        inicio = y + altura - 5 - tamanho if alinhamento == "esquerda" else y + (altura + bloco) / 2 - tamanho
        for indice, linha in enumerate(linhas):
            eixo_x = x + 4 if alinhamento == "esquerda" else x + largura / 2
            escrever(comandos, linha, eixo_x, inicio - indice * entrelinha, tamanho, negrito, cor, alinhamento)

    paginas, comandos, y = [], [], 0.0

    def nova_pagina():
        nonlocal comandos, y
        if comandos:
            paginas.append(comandos)
        comandos = []
        y = 548.0

    def garantir(altura_necessaria):
        if y - altura_necessaria < limite_inferior:
            nova_pagina()
            return True
        return False

    def desenhar_cabecalho_tabela(colunas, larguras, y_topo):
        altura = 27.0
        x = margem_x
        for coluna, largura in zip(colunas, larguras):
            retangulo(comandos, x, y_topo - altura, largura, altura, cores["teal"], cores["branco"], 0.45)
            escrever_caixa(comandos, coluna, x, y_topo - altura, largura, altura, 7.0, True, cores["branco"], "centro", 100)
            x += largura
        return y_topo - altura

    def desenhar_secao(nome, df_original):
        nonlocal y
        df = _colunas_relevantes_pdf(df_original, limite=9)
        garantir(28)
        retangulo(comandos, margem_x, y - 21, largura_util, 21, cores["teal"])
        escrever(comandos, f"{limpo(nome).upper()} - {len(df_original)} registro(s)", margem_x + 7, y - 14, 9, True, cores["branco"])
        y -= 21
        if df.empty or not len(df.columns):
            escrever(comandos, "Nenhum registro disponível nesta seção.", margem_x + 6, y - 15, 8, False, cores["texto"])
            y -= 27
            return

        pesos = []
        for coluna in df.columns:
            nome_coluna = remover_acentos(str(coluna)).lower()
            amostra = [len(str(coluna))] + [len(str(valor)) for valor in df[coluna].astype(str).head(80)]
            peso = max(8, min(30, max(amostra)))
            if any(chave in nome_coluna for chave in ("material", "descricao", "endereco", "observacao")):
                peso = max(peso, 25)
            pesos.append(peso)
        soma_pesos = sum(pesos) or 1
        larguras = [largura_util * peso / soma_pesos for peso in pesos]
        y = desenhar_cabecalho_tabela(list(df.columns), larguras, y)

        for indice_registro, (_, registro) in enumerate(df.iterrows(), start=1):
            linhas_celulas = [quebrar_texto(registro[coluna], largura - 8, 6.7, 240) for coluna, largura in zip(df.columns, larguras)]
            altura_linha = max(20.0, min(68.0, 8.3 * max(len(linhas) for linhas in linhas_celulas) + 7))
            if y - altura_linha < limite_inferior:
                nova_pagina()
                retangulo(comandos, margem_x, y - 21, largura_util, 21, cores["teal"])
                escrever(comandos, f"{limpo(nome).upper()} - CONTINUAÇÃO", margem_x + 7, y - 14, 9, True, cores["branco"])
                y -= 21
                y = desenhar_cabecalho_tabela(list(df.columns), larguras, y)
            x = margem_x
            fundo_linha = cores["fundo"] if indice_registro % 2 == 0 else cores["branco"]
            for indice_coluna, (coluna, largura, linhas) in enumerate(zip(df.columns, larguras, linhas_celulas)):
                fundo_celula = fundo_linha
                nome_coluna = remover_acentos(str(coluna)).lower()
                if "status" in nome_coluna or "situacao" in nome_coluna:
                    status = remover_acentos(str(registro[coluna])).lower()
                    if re.search(r"conclu|entregue|dentro", status): fundo_celula = cores["verde"]
                    elif re.search(r"fora|atras|vencid", status): fundo_celula = cores["vermelho"]
                    elif re.search(r"pend|aguard", status): fundo_celula = cores["amarelo"]
                retangulo(comandos, x, y - altura_linha, largura, altura_linha, fundo_celula, cores["teal_borda"], 0.35)
                entrelinha = 8.3
                for indice_linha, linha in enumerate(linhas[:7]):
                    escrever(comandos, linha, x + 4, y - 11 - indice_linha * entrelinha, 6.7, False, cores["texto"])
                x += largura
            y -= altura_linha
        y -= 8

    resumo_analitico, secoes_dados, _ = _organizar_secoes_relatorio(titulo, tabelas)
    total_registros = sum(len(df) for _, df in secoes_dados)
    nova_pagina()

    retangulo(comandos, margem_x, y - 29, largura_util, 29, cores["teal"])
    escrever(comandos, limpo(titulo).upper(), largura_pagina / 2, y - 19, 13, True, cores["branco"], "centro")
    y -= 36
    escrever(comandos, f"Gerado em {datetime.now(FUSO_LOCAL).strftime('%d/%m/%Y às %H:%M')} | {total_registros} registro(s)", margem_x + 6, y - 8, 8, False, cores["texto"])
    y -= 19

    if not resumo_analitico.empty:
        kpis = resumo_analitico.head(6).to_dict("records")
        while len(kpis) < 6:
            kpis.append({"Indicador": "", "Resultado": ""})
        largura_kpi = largura_util / 6
        altura_rotulo, altura_valor = 28.0, 31.0
        x = margem_x
        for kpi in kpis:
            retangulo(comandos, x, y - altura_rotulo, largura_kpi, altura_rotulo, cores["cinza"], cores["branco"], 0.5)
            escrever_caixa(comandos, kpi.get("Indicador", ""), x, y - altura_rotulo, largura_kpi, altura_rotulo, 7.0, True, cores["branco"], "centro", 90)
            retangulo(comandos, x, y - altura_rotulo - altura_valor, largura_kpi, altura_valor, cores["verde"], cores["borda"], 0.5)
            escrever_caixa(comandos, kpi.get("Resultado", ""), x, y - altura_rotulo - altura_valor, largura_kpi, altura_valor, 10.5, True, cores["texto"], "centro", 70)
            x += largura_kpi
        y -= altura_rotulo + altura_valor + 9

    for nome, df in secoes_dados:
        desenhar_secao(nome, df)

    if not resumo_analitico.empty:
        leituras = resumo_analitico[resumo_analitico["Leitura para análise"].astype(str).str.strip() != ""]
        complementares = resumo_analitico.iloc[6:]
        analises = pd.concat([leituras, complementares], ignore_index=True).drop_duplicates(subset=["Indicador"])
        if not analises.empty:
            desenhar_secao("Análises complementares", analises[["Indicador", "Resultado", "Leitura para análise"]].rename(columns={"Leitura para análise": "Interpretação"}))

    if comandos:
        paginas.append(comandos)

    objetos = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
    ]
    ids_paginas = []
    total_paginas = len(paginas)
    for numero_pagina, comandos_pagina in enumerate(paginas, start=1):
        moldura = []
        retangulo(moldura, 0, altura_pagina - 28, largura_pagina, 28, cores["cinza"])
        escrever(moldura, "APROAR ENGENHARIA", margem_x, altura_pagina - 18, 8.5, True, cores["branco"])
        escrever(moldura, "Torre de Controle Logístico", largura_pagina - margem_x, altura_pagina - 18, 7, False, cores["branco"], "direita")
        moldura.extend([rgb(cores["borda"], "RG"), "0.5 w", f"{margem_x:.2f} 30 m {largura_pagina - margem_x:.2f} 30 l S"])
        escrever(moldura, "Relatório operacional", margem_x, 18, 7, False, cores["texto"])
        escrever(moldura, f"Página {numero_pagina} de {total_paginas}", largura_pagina - margem_x, 18, 7, False, cores["texto"], "direita")
        conteudo_bytes = ("\n".join(moldura + comandos_pagina)).encode("ascii")
        id_pagina = len(objetos) + 1
        id_conteudo = id_pagina + 1
        ids_paginas.append(id_pagina)
        objetos.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {largura_pagina:.0f} {altura_pagina:.0f}] /Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents {id_conteudo} 0 R >>".encode("ascii"))
        objetos.append(f"<< /Length {len(conteudo_bytes)} >>\nstream\n".encode("ascii") + conteudo_bytes + b"\nendstream")
    objetos[1] = f"<< /Type /Pages /Kids [{' '.join(f'{i} 0 R' for i in ids_paginas)}] /Count {len(ids_paginas)} >>".encode("ascii")

    arquivo = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for indice, objeto in enumerate(objetos, start=1):
        offsets.append(len(arquivo))
        arquivo.extend(f"{indice} 0 obj\n".encode("ascii") + objeto + b"\nendobj\n")
    inicio_xref = len(arquivo)
    arquivo.extend(f"xref\n0 {len(objetos)+1}\n0000000000 65535 f \n".encode("ascii"))
    for offset in offsets[1:]:
        arquivo.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    arquivo.extend(f"trailer\n<< /Size {len(objetos)+1} /Root 1 0 R >>\nstartxref\n{inicio_xref}\n%%EOF".encode("ascii"))
    return bytes(arquivo)

def _criar_pdf_relatorio(titulo, tabelas):
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except (ImportError, ModuleNotFoundError):
        return _criar_pdf_textual(titulo, tabelas)

    def texto_pdf_limpo(valor):
        return str(valor).replace("—", "-").replace("–", "-").replace("‑", "-").replace("•", "-")

    def paragrafo(valor, estilo, limite=700):
        texto = texto_pdf_limpo(valor)
        if len(texto) > limite:
            texto = texto[:limite - 3].rstrip() + "..."
        texto = html_escape(texto).replace("\n", "<br/>")
        return Paragraph(texto or "-", estilo)

    teal = colors.HexColor("#08B7B7")
    teal_borda = colors.HexColor("#20C4C4")
    cinza_escuro = colors.HexColor("#4B4B4B")
    cinza_fundo = colors.HexColor("#F8FAFC")
    cinza_borda = colors.HexColor("#CBD5E1")
    cinza_texto = colors.HexColor("#475569")
    verde_claro = colors.HexColor("#DDF4D5")
    amarelo_claro = colors.HexColor("#FEF3C7")
    vermelho_claro = colors.HexColor("#FECACA")
    pagina = landscape(A4)
    largura_util = pagina[0] - 24 * mm

    estilos = getSampleStyleSheet()
    estilo_titulo = ParagraphStyle("TituloModelo", parent=estilos["Title"], fontName="Helvetica-Bold", fontSize=13, leading=16, textColor=colors.white, alignment=TA_CENTER)
    estilo_meta = ParagraphStyle("MetaModelo", parent=estilos["Normal"], fontName="Helvetica", fontSize=8, leading=10, textColor=cinza_texto, alignment=TA_LEFT)
    estilo_secao = ParagraphStyle("SecaoModelo", parent=estilos["Heading2"], fontName="Helvetica-Bold", fontSize=9.5, leading=12, textColor=colors.white, backColor=teal, borderPadding=(5, 7, 5, 7), spaceBefore=7, spaceAfter=0, keepWithNext=1)
    estilo_cabecalho = ParagraphStyle("CabecalhoModelo", parent=estilos["Normal"], fontName="Helvetica-Bold", fontSize=7.2, leading=8.5, textColor=colors.white, alignment=TA_CENTER)
    estilo_celula = ParagraphStyle("CelulaModelo", parent=estilos["Normal"], fontName="Helvetica", fontSize=6.8, leading=8.4, textColor=colors.HexColor("#334155"))
    estilo_kpi_rotulo = ParagraphStyle("RotuloKPIModelo", parent=estilos["Normal"], fontName="Helvetica-Bold", fontSize=7.2, leading=8.5, textColor=colors.white, alignment=TA_CENTER)
    estilo_kpi_valor = ParagraphStyle("ValorKPIModelo", parent=estilos["Normal"], fontName="Helvetica-Bold", fontSize=10.5, leading=13, textColor=colors.HexColor("#334155"), alignment=TA_CENTER)
    estilo_vazio = ParagraphStyle("VazioModelo", parent=estilos["Normal"], fontName="Helvetica-Oblique", fontSize=8, textColor=cinza_texto, spaceBefore=5, spaceAfter=7)

    titulo_limpo = texto_pdf_limpo(titulo)
    resumo_analitico, secoes_dados, _ = _organizar_secoes_relatorio(titulo, tabelas)
    total_registros = sum(len(df) for _, df in secoes_dados)
    saida = io.BytesIO()
    documento = SimpleDocTemplate(
        saida, pagesize=pagina, rightMargin=12 * mm, leftMargin=12 * mm,
        topMargin=19 * mm, bottomMargin=14 * mm,
        title=titulo_limpo, author="APROAR Engenharia",
    )

    def cabecalho_rodape(canvas, doc):
        largura, altura = pagina
        canvas.saveState()
        canvas.setFillColor(cinza_escuro)
        canvas.rect(0, altura - 10 * mm, largura, 10 * mm, stroke=0, fill=1)
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 8.5)
        canvas.drawString(12 * mm, altura - 6.5 * mm, "APROAR ENGENHARIA")
        canvas.setFont("Helvetica", 7)
        canvas.drawRightString(largura - 12 * mm, altura - 6.5 * mm, "Torre de Controle Logístico")
        canvas.setStrokeColor(cinza_borda)
        canvas.line(12 * mm, 9 * mm, largura - 12 * mm, 9 * mm)
        canvas.setFillColor(cinza_texto)
        canvas.setFont("Helvetica", 7)
        canvas.drawString(12 * mm, 5 * mm, "Relatório operacional")
        canvas.drawRightString(largura - 12 * mm, 5 * mm, f"Página {doc.page}")
        canvas.restoreState()

    faixa_titulo = Table([[Paragraph(html_escape(titulo_limpo.upper()), estilo_titulo)]], colWidths=[largura_util], rowHeights=[26])
    faixa_titulo.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), teal), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    elementos = [
        faixa_titulo,
        Spacer(1, 5),
        Paragraph(f"Gerado em {datetime.now(FUSO_LOCAL).strftime('%d/%m/%Y às %H:%M')} &nbsp;&nbsp;|&nbsp;&nbsp; {total_registros} registro(s)", estilo_meta),
        Spacer(1, 7),
    ]

    if not resumo_analitico.empty:
        kpis = resumo_analitico.head(6)
        dados_kpi = [
            [paragrafo(linha.get("Indicador", "Indicador"), estilo_kpi_rotulo, 90) for _, linha in kpis.iterrows()],
            [paragrafo(linha.get("Resultado", "-"), estilo_kpi_valor, 80) for _, linha in kpis.iterrows()],
        ]
        while len(dados_kpi[0]) < 6:
            dados_kpi[0].append("")
            dados_kpi[1].append("")
        painel_kpi = Table(dados_kpi, colWidths=[largura_util / 6] * 6, rowHeights=[28, 32])
        painel_kpi.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), cinza_escuro),
            ("BACKGROUND", (0, 1), (-1, 1), verde_claro),
            ("GRID", (0, 0), (-1, -1), 0.55, colors.white),
            ("BOX", (0, 0), (-1, -1), 0.55, cinza_borda),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        elementos.extend([painel_kpi, Spacer(1, 6)])

    for nome, df_original in secoes_dados:
        elementos.append(Paragraph(f"{html_escape(texto_pdf_limpo(nome).upper())} &nbsp; - &nbsp; {len(df_original)} registro(s)", estilo_secao))
        if df_original.empty or not len(df_original.columns):
            elementos.append(Paragraph("Nenhum registro disponível nesta seção.", estilo_vazio))
            continue

        df = _colunas_relevantes_pdf(df_original, limite=9)
        pesos = []
        for coluna in df.columns:
            nome_coluna = remover_acentos(str(coluna)).lower()
            amostra = [len(str(coluna))] + [len(str(valor)) for valor in df[coluna].astype(str).head(80)]
            peso = max(8, min(30, max(amostra)))
            if any(chave in nome_coluna for chave in ("material", "descricao", "endereco", "observacao")):
                peso = max(peso, 25)
            pesos.append(peso)
        total_pesos = sum(pesos) or 1
        larguras = [largura_util * peso / total_pesos for peso in pesos]
        dados_tabela = [[paragrafo(coluna, estilo_cabecalho, 70) for coluna in df.columns]]
        dados_tabela.extend([[paragrafo(valor, estilo_celula) for valor in linha] for linha in df.astype(str).values.tolist()])
        tabela = Table(dados_tabela, colWidths=larguras, repeatRows=1, hAlign="LEFT")
        comandos = [
            ("BACKGROUND", (0, 0), (-1, 0), teal),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("GRID", (0, 0), (-1, -1), 0.35, teal_borda),
        ]
        for indice_linha in range(1, len(dados_tabela)):
            comandos.append(("BACKGROUND", (0, indice_linha), (-1, indice_linha), cinza_fundo if indice_linha % 2 == 0 else colors.white))
        for indice_coluna, coluna in enumerate(df.columns):
            nome_coluna = remover_acentos(str(coluna)).lower()
            if "status" not in nome_coluna and "situacao" not in nome_coluna:
                continue
            for indice_linha, valor in enumerate(df[coluna].astype(str), start=1):
                texto_status = remover_acentos(valor).lower()
                cor = verde_claro if re.search(r"conclu|entregue|dentro", texto_status) else vermelho_claro if re.search(r"fora|atras|vencid", texto_status) else amarelo_claro if re.search(r"pend|aguard", texto_status) else None
                if cor:
                    comandos.append(("BACKGROUND", (indice_coluna, indice_linha), (indice_coluna, indice_linha), cor))
        tabela.setStyle(TableStyle(comandos))
        elementos.extend([tabela, Spacer(1, 7)])

    if not resumo_analitico.empty:
        leituras = resumo_analitico[resumo_analitico["Leitura para análise"].astype(str).str.strip() != ""]
        complementares = resumo_analitico.iloc[6:]
        analises = pd.concat([leituras, complementares], ignore_index=True).drop_duplicates(subset=["Indicador"])
        if not analises.empty:
            elementos.append(Paragraph("ANÁLISES COMPLEMENTARES", estilo_secao))
            dados_analise = [[
                paragrafo("Indicador", estilo_cabecalho),
                paragrafo("Resultado", estilo_cabecalho),
                paragrafo("Interpretação", estilo_cabecalho),
            ]]
            dados_analise.extend([
                [paragrafo(linha.get("Indicador", ""), estilo_celula), paragrafo(linha.get("Resultado", ""), estilo_celula), paragrafo(linha.get("Leitura para análise", ""), estilo_celula)]
                for _, linha in analises.iterrows()
            ])
            tabela_analise = Table(dados_analise, colWidths=[largura_util * 0.27, largura_util * 0.18, largura_util * 0.55], repeatRows=1)
            tabela_analise.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), cinza_escuro),
                ("BACKGROUND", (0, 1), (-1, -1), cinza_fundo),
                ("GRID", (0, 0), (-1, -1), 0.35, cinza_borda),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]))
            elementos.append(tabela_analise)

    documento.build(elementos, onFirstPage=cabecalho_rodape, onLaterPages=cabecalho_rodape)
    return saida.getvalue()

def _conteudo_exportador(titulo, dados, nome_arquivo, chave):
    st.markdown("##### 📤 Exportar relatório")
    col_formato, col_download = st.columns([1, 2])
    formato = col_formato.selectbox("Formato", ["PDF", "CSV", "Excel"], key=f"formato_relatorio_{chave}")
    tabelas_dados = _normalizar_tabelas_relatorio(dados)
    resumo_analitico = _criar_resumo_analitico_relatorio(titulo, tabelas_dados)
    tabelas = [("Resumo Analítico", resumo_analitico)] + tabelas_dados
    if formato == "CSV":
        arquivo, extensao, mime = _criar_csv_relatorio(tabelas), "csv", "text/csv"
    elif formato == "Excel":
        arquivo, extensao, mime = _criar_excel_relatorio(tabelas, titulo), "xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        arquivo, extensao, mime = _criar_pdf_relatorio(titulo, tabelas), "pdf", "application/pdf"
    col_download.download_button(
        f"⬇️ Baixar {formato}", data=arquivo,
        file_name=f"{nome_arquivo}_{AGORA_REAL.strftime('%Y-%m-%d')}.{extensao}",
        mime=mime, use_container_width=True, key=f"baixar_relatorio_{chave}_{formato}",
    )

@fragmento_independente
def renderizar_exportador(titulo, dados, nome_arquivo, chave):
    _conteudo_exportador(titulo, dados, nome_arquivo, chave)

@fragmento_independente
def renderizar_detalhes_fechamento(veiculo, gastos, quilometragem, chave):
    mostrar = st.checkbox(f"Ver lançamentos da {veiculo}", key=f"mostrar_fechamento_{chave}")
    if not mostrar:
        return
    st.caption("Combustível e manutenções do mês")
    if gastos.empty: st.info("Nenhum gasto lançado no mês.")
    else: st.dataframe(gastos, use_container_width=True, hide_index=True)
    st.caption("Quilometragens do mês")
    if quilometragem.empty: st.info("Nenhuma quilometragem lançada no mês.")
    else: st.dataframe(quilometragem, use_container_width=True, hide_index=True)

def montar_relatorio_rota(route_steps, concluidos):
    linhas, numero_parada = [], 0
    for step in route_steps:
        if step.get("type") == "lunch":
            linhas.append({"Parada": "Almoço", "Local": "Pausa", "Chegada": step.get("dyn_chegada", step.get("chegada", "")), "Saída": step.get("dyn_saida", step.get("saida", "")), "Ação": "PAUSA"})
            continue
        if step.get("type") == "return":
            linhas.append({"Parada": "Retorno", "Local": step.get("destino", ""), "Chegada": step.get("dyn_chegada", step.get("chegada", "")), "Saída": step.get("dyn_saida", step.get("saida", "")), "Ação": "RETORNO", "Distância (km)": step.get("dist", 0)})
            continue
        numero_parada += 1
        acoes = step.get("actions", []) or [("DESLOCAMENTO", {})]
        for acao, tarefa in acoes:
            card_id = str(tarefa.get("id", ""))
            linhas.append({
                "Parada": numero_parada, "Local": step.get("destino", ""),
                "Chegada": step.get("dyn_chegada", step.get("chegada", "")),
                "Saída": step.get("dyn_saida", step.get("saida", "")),
                "Distância (km)": round(float(step.get("dist", 0) or 0), 2),
                "Ação": acao, "Obra": tarefa.get("Obra", ""), "Materiais": tarefa.get("Materiais", ""),
                "Status": f"Concluída às {concluidos[card_id]}" if card_id in concluidos else "Pendente",
            })
    return pd.DataFrame(linhas)

def calcular_distancia_km(lat1, lon1, lat2, lon2):
    dLat = math.radians(lat2 - lat1)
    dLon = math.radians(lon2 - lon1)
    a = math.sin(dLat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dLon/2)**2
    return 6371.0 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def aplicar_tempos_dinamicos(route_steps, dict_concluidos, start_time_str):
    agora_min = AGORA_REAL.hour * 60 + AGORA_REAL.minute
    agora_min_efetivo = 13*60 if 12*60 <= agora_min < 13*60 else agora_min
    current_min = parse_time_to_mins(start_time_str) if start_time_str else (7 * 60 + 0)
    
    for step in route_steps:
        if step['type'] == 'lunch':
            step['dyn_chegada'] = "12:00"
            step['dyn_saida'] = "13:00"
            step['is_concluded'] = False
            current_min = max(current_min, 13 * 60)
            continue
            
        if step['type'] == 'return':
            arr_min = current_min + step.get('travel_mins', 0)
            if current_min <= 12*60 and arr_min > 12*60: arr_min = max(arr_min + 60, 13*60)
            if arr_min < agora_min_efetivo: arr_min = agora_min_efetivo
            if 12*60 <= arr_min < 13*60: arr_min = 13*60
            
            step['dyn_chegada'] = format_mins_to_time(arr_min)
            step['dyn_saida'] = step['dyn_chegada']
            step['is_concluded'] = False
            continue
            
        concluded_times = []
        has_pending = False
        for a, t in step.get('actions', []):
            card_id = str(t.get('id', ''))
            if card_id in dict_concluidos:
                concluded_times.append(parse_time_to_mins(dict_concluidos[card_id]))
            else:
                has_pending = True
                
        if not has_pending and concluded_times:
            max_c = max(concluded_times)
            step['dyn_chegada'] = "Concluído"
            step['dyn_saida'] = format_mins_to_time(max_c)
            current_min = max(current_min, max_c)
            step['is_concluded'] = True
        else:
            if 12*60 <= current_min < 13*60: current_min = 13*60
                
            travel = step.get('travel_mins', 0)
            arr_min = current_min + travel
            
            if current_min <= 12*60 and arr_min > 12*60: arr_min = max(arr_min + 60, 13*60)
            if arr_min < agora_min_efetivo: arr_min = agora_min_efetivo
            if 12*60 <= arr_min < 13*60: arr_min = 13*60
                
            service = step.get('tempo_local', 0)
            dep_min = arr_min + service
            
            if arr_min <= 12*60 and dep_min > 12*60: dep_min = max(dep_min + 60, 13*60)
            
            step['dyn_chegada'] = format_mins_to_time(arr_min)
            step['dyn_saida'] = format_mins_to_time(dep_min)
            current_min = dep_min
            step['is_concluded'] = False
            
    return route_steps, current_min

def renderizar_banner_eta(hora_atual_str, nova_previsao_str, final_dyn_min):
    if not hora_atual_str: return
    cor_previsao = "#16a34a" if final_dyn_min <= (17 * 60) else "#f59e0b" if final_dyn_min <= (17 * 60 + 30) else "#ef4444"
            
    st.markdown(f'''
    <div style="background: linear-gradient(145deg, rgba(18,21,48,0.8), rgba(13,16,37,0.9)); padding: 15px 25px; border-radius: 12px; border: 1px solid rgba(64,116,146,.3); display: flex; justify-content: space-between; align-items: center; margin-bottom: 25px; box-shadow: 0 8px 20px rgba(0,0,0,0.2);">
       <div style="font-size: 14px; color: #8da0b8; text-align: left;">
            <span style="font-size: 20px;">⏱️</span> Atualizada:<br>
            <b style="color: #e4e8f4; font-size: 20px;">{hora_atual_str}</b>
       </div>
       <div style="font-size: 14px; color: #8da0b8; text-align: right;">
            <span style="font-size: 20px;">🏁</span> Previsão de Término:<br>
            <b style="color: {cor_previsao}; font-size: 20px;">{nova_previsao_str}</b>
       </div>
    </div>
    ''', unsafe_allow_html=True)

# =====================================================================
# MARCAÇÕES COMPARTILHADAS DO APP DO DAVI
# =====================================================================
SQL_TABELA_CHECKINS_DAVI = """
CREATE TABLE IF NOT EXISTS roteiro_checkins_davi (
    data_rota TEXT NOT NULL,
    etapa_indice INTEGER NOT NULL,
    destino TEXT NOT NULL,
    marcado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (data_rota, etapa_indice)
)
"""

@st.cache_resource(show_spinner=False)
def garantir_tabela_checkins_davi():
    """Cria uma única vez a estrutura compartilhada entre celular e escritório."""
    execute_db(SQL_TABELA_CHECKINS_DAVI)
    return True

def carregar_checkins_davi(data_rota):
    rows = fetch_all(
        """
        SELECT etapa_indice, destino,
               TO_CHAR(marcado_em AT TIME ZONE 'America/Fortaleza', 'HH24:MI') AS hora,
               EXTRACT(EPOCH FROM marcado_em) AS instante
        FROM roteiro_checkins_davi
        WHERE data_rota = :data
        ORDER BY etapa_indice
        """,
        {"data": data_rota},
    )
    return {
        int(row[0]): {"destino": str(row[1]), "hora": str(row[2] or ""), "instante": float(row[3] or 0)}
        for row in rows
    }

def filtrar_checkins_da_rota(route_steps, checkins):
    """Impede que uma marca antiga seja ligada a outro destino após refazer a rota."""
    return {
        indice: dados
        for indice, dados in checkins.items()
        if 0 <= indice < len(route_steps)
        and route_steps[indice].get("type") not in {"lunch", "return"}
        and str(route_steps[indice].get("destino", "")) == dados.get("destino", "")
    }

def salvar_checkin_davi(data_rota, etapa_indice, destino, feita):
    if feita:
        execute_db(
            """
            INSERT INTO roteiro_checkins_davi (data_rota, etapa_indice, destino, marcado_em)
            VALUES (:data, :indice, :destino, NOW())
            ON CONFLICT (data_rota, etapa_indice)
            DO UPDATE SET destino = EXCLUDED.destino, marcado_em = NOW()
            """,
            {"data": data_rota, "indice": etapa_indice, "destino": destino},
        )
    else:
        execute_db(
            """
            DELETE FROM roteiro_checkins_davi
            WHERE data_rota = :data AND etapa_indice = :indice AND destino = :destino
            """,
            {"data": data_rota, "indice": etapa_indice, "destino": destino},
        )

# =====================================================================
# RENDERIZAÇÃO DO MODO MOBILE (APP DO DAVI)
# =====================================================================
modo_url = st.query_params.get("davi", "")

if modo_url == "true":
    st.markdown("""
        <style>
            [data-testid="stSidebar"] {display: none !important;}
            [data-testid="stHeader"] {display: none !important;}
            .block-container {padding-top: 1rem !important; padding-bottom: 2rem !important; max-width: 100% !important;}
        </style>
    """, unsafe_allow_html=True)

    st.markdown("<h2 style='text-align: center; color: #e4e8f4; margin-bottom: 0;'>📱 App do Motorista</h2>", unsafe_allow_html=True)
    st.caption(f"<div style='text-align:center; font-size: 14px; margin-bottom: 15px; color: #8da0b8;'>Rota Oficial de: <b>{DATA_REF_ROTA_STR}</b></div>", unsafe_allow_html=True)

    if st.button("🔄 ATUALIZAR ROTA", use_container_width=True, type="primary"): st.rerun()

    erro_checkin_mobile = ""
    try:
        garantir_tabela_checkins_davi()
        res = fetch_one("SELECT json_route, json_locais, json_geometria, json_enderecos, total_km FROM rota_ativa WHERE id = 1 AND data_rota = :data", {"data": DATA_REF_ROTA_STR})
        df_mobile = get_df("SELECT id, hora_conclusao FROM historico_concluidos WHERE data_conclusao = :data", {"data": DATA_REF_ROTA_STR})
        dict_concluidos_mobile = dict(zip(df_mobile['id'].astype(str), df_mobile['hora_conclusao']))
        res_inicio = fetch_one("SELECT MIN(hora_inicio) FROM inicio_movimento WHERE data=:data", {"data": DATA_REF_ROTA_STR})
        hora_inicio_real = res_inicio[0] if res_inicio and res_inicio[0] else "07:30"
    except: res, dict_concluidos_mobile, hora_inicio_real = None, {}, "07:30"

    if not res:
        st.info("Nenhuma rota foi liberada pela Torre de Controle para hoje ainda. Aguarde a central calcular e tente atualizar a tela.")
        st.stop()

    route_steps = json.loads(res[0])
    locais_dict = json.loads(res[1])
    geometria_rota = json.loads(res[2])
    enderecos_dict = json.loads(res[3])
    total_km = res[4]
    p_saida = route_steps[0]['destino'] if route_steps else ""

    # O clique no cartão volta ao app com estes parâmetros. A gravação é feita
    # no servidor para que a mesma informação apareça no painel do escritório.
    etapa_param = st.query_params.get("etapa", "")
    feito_param = st.query_params.get("feito", "")
    if etapa_param != "" and feito_param in {"0", "1"}:
        try:
            etapa_indice = int(etapa_param)
            if not 0 <= etapa_indice < len(route_steps):
                raise ValueError("Etapa fora da rota atual")
            etapa_escolhida = route_steps[etapa_indice]
            if etapa_escolhida.get("type") in {"lunch", "return"}:
                raise ValueError("Esta etapa não pode ser marcada")
            salvar_checkin_davi(
                DATA_REF_ROTA_STR,
                etapa_indice,
                str(etapa_escolhida.get("destino", "")),
                feito_param == "1",
            )
            st.query_params.clear()
            st.query_params["davi"] = "true"
            st.rerun()
        except Exception:
            erro_checkin_mobile = "Não foi possível salvar a marcação. Tente novamente."
            st.query_params.clear()
            st.query_params["davi"] = "true"

    try:
        dict_checkins_mobile = filtrar_checkins_da_rota(route_steps, carregar_checkins_davi(DATA_REF_ROTA_STR))
    except Exception:
        dict_checkins_mobile = {}
        erro_checkin_mobile = "Não foi possível carregar as marcações compartilhadas agora."

    if erro_checkin_mobile:
        st.error(erro_checkin_mobile)

    route_steps, final_dyn_min = aplicar_tempos_dinamicos(route_steps, dict_concluidos_mobile, hora_inicio_real)
    
    hora_atual_str = AGORA_REAL.strftime("%H:%M")
    nova_previsao_str = format_mins_to_time(final_dyn_min)
    renderizar_banner_eta(hora_atual_str, nova_previsao_str, final_dyn_min)

    st.markdown(f"<h4 style='color: #e4e8f4; margin-bottom:4px;'>Roteiro Passo a Passo ({total_km:.1f} km)</h4>", unsafe_allow_html=True)
    st.caption("Deslize para o lado para avançar pelas etapas da rota.")
    cartoes_mobile = []
    numero_parada_mobile = 1

    for i, step in enumerate(route_steps):
        tipo_step = step.get('type', '')
        destino_step = str(step.get('destino', ''))
        is_start = (i == 0 and destino_step == p_saida)
        classe_card, selo, titulo_card, meta_card, botao_gps, botao_feito = "normal", "ETAPA", destino_step, "", "", ""
        etapa_marcada = False

        if tipo_step == 'lunch':
            classe_card, selo = "almoco", "PAUSA"
            titulo_card = "🍔 Almoço"
            meta_card = f"Horário previsto: {html_escape(str(step.get('dyn_chegada', '12:00')))} às {html_escape(str(step.get('dyn_saida', '13:00')))}"
            corpo_acoes = "<div class='mensagem-etapa'>Pausa programada para descanso e alimentação.</div>"
        elif tipo_step == 'return':
            classe_card, selo = "retorno", "RETORNO"
            titulo_card = f"🏁 Retorno à Base: {html_escape(destino_step)}"
            meta_card = f"Chegada prevista: {html_escape(str(step.get('dyn_chegada', '')))}"
            corpo_acoes = "<div class='mensagem-etapa'>Última etapa do roteiro. Retorne para a base indicada.</div>"
        else:
            endereco_db = enderecos_dict.get(destino_step, "")
            coordenadas = locais_dict.get(destino_step, [None, None])
            if str(endereco_db).startswith("http"):
                link_gps = str(endereco_db)
            elif endereco_db:
                link_gps = f"https://www.google.com/maps/dir/?api=1&destination={urllib.parse.quote(str(endereco_db))}"
            elif len(coordenadas) >= 2 and coordenadas[0] is not None:
                link_gps = f"https://www.google.com/maps/dir/?api=1&destination={coordenadas[0]},{coordenadas[1]}"
            else:
                link_gps = ""

            if is_start:
                classe_card, selo = "preparacao", "PREPARAÇÃO"
                titulo_card = f"🏁 {html_escape(destino_step)}"
                meta_card = f"Base: {html_escape(str(step.get('chegada', '')))} às {html_escape(str(step.get('saida', '')))}"
            else:
                selo = f"PARADA {numero_parada_mobile}"
                titulo_card = f"📍 {html_escape(destino_step)}"
                meta_card = f"Trecho: {float(step.get('dist', 0) or 0):.1f} km | Base: {html_escape(str(step.get('chegada', '')))} às {html_escape(str(step.get('saida', '')))}"

            status_tempo = f"<span class='status concluido'>✅ Concluído às {html_escape(str(step.get('dyn_saida', '')))}</span>" if step.get('is_concluded') else f"<span class='status pendente'>⏳ Previsão: {html_escape(str(step.get('dyn_chegada', '')))} às {html_escape(str(step.get('dyn_saida', '')))}</span>"
            blocos_acao = []
            for acao, tarefa in step.get('actions', []):
                eh_coleta = acao == "COLETAR"
                classe_acao, icone = ("coleta", "📦") if eh_coleta else ("entrega", "📬")
                card_id = str(tarefa.get('id', ''))
                concluido = f"<div class='baixa'>✅ Baixa às {html_escape(str(dict_concluidos_mobile[card_id]))}</div>" if card_id in dict_concluidos_mobile else ""
                blocos_acao.append(
                    f"<div class='acao {classe_acao}'><div class='acao-titulo'>{icone} {html_escape(str(acao))}</div>"
                    f"<div class='materiais'>{html_escape(str(tarefa.get('Materiais', '')))}</div>"
                    f"<div class='obra'>Obra: {html_escape(str(tarefa.get('Obra', '')))}</div>{concluido}</div>"
                )
            corpo_acoes = status_tempo + ("".join(blocos_acao) if blocos_acao else "<div class='mensagem-etapa'>Nenhuma movimentação cadastrada nesta etapa.</div>")
            rotulo_lembrete = "preparação" if is_start else "parada"
            checkin_etapa = dict_checkins_mobile.get(i)
            etapa_marcada = bool(checkin_etapa) or bool(step.get('is_concluded'))
            if step.get('is_concluded'):
                botao_feito = "<button class='marcar-feita ativa' data-feita='1' disabled>✅ Concluída no sistema</button>"
            else:
                novo_estado = "0" if checkin_etapa else "1"
                classe_marcacao = " ativa" if checkin_etapa else ""
                texto_marcacao = (
                    f"✅ Marcada às {html_escape(checkin_etapa['hora'])} • toque para desfazer"
                    if checkin_etapa else f"☐ Marcar {rotulo_lembrete} como feita"
                )
                link_marcacao = html_escape(f"?davi=true&etapa={i}&feito={novo_estado}", quote=True)
                botao_feito = (
                    f"<a class='marcar-feita{classe_marcacao}' data-feita='{'1' if checkin_etapa else '0'}' "
                    f"href='{link_marcacao}' target='_top' onclick='prepararEnvio(this)'>{texto_marcacao}</a>"
                )
            if not is_start:
                if link_gps:
                    botao_gps = f"<a class='gps' href='{html_escape(link_gps, quote=True)}' target='_blank' rel='noopener'>🧭 ABRIR GPS DA PARADA {numero_parada_mobile}</a>"
                numero_parada_mobile += 1

        rodape_card = f"<div class='rodape-card'>{botao_feito}{botao_gps}</div>" if botao_feito or botao_gps else ""
        cartoes_mobile.append(
            f"<article class='cartao {classe_card}{' feita' if etapa_marcada else ''}'><div class='topo-card'><span class='selo'>{html_escape(str(selo))}</span>"
            f"<h2>{titulo_card}</h2><div class='meta'>{meta_card}</div></div>"
            f"<div class='conteudo-card'>{corpo_acoes}</div>{rodape_card}</article>"
        )

    if cartoes_mobile:
        html_carrossel = """
        <!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
        <style>
            * { box-sizing: border-box; }
            html, body { margin: 0; padding: 0; background: transparent; color: #e4e8f4; font-family: Inter, Arial, sans-serif; }
            .barra { display:flex; justify-content:space-between; align-items:center; margin:0 4px 8px; color:#8da0b8; font-size:13px; }
            .resumo-topo { display:flex; align-items:center; gap:6px; }
            .feitas { color:#86efac; font-weight:800; background:rgba(22,163,74,.13); border:1px solid rgba(34,197,94,.28); padding:6px 9px; border-radius:999px; }
            .contador { color:#e4e8f4; font-weight:800; background:#151a31; border:1px solid #2b3654; padding:6px 10px; border-radius:999px; }
            .trilho { display:flex; gap:12px; overflow-x:auto; scroll-snap-type:x mandatory; scroll-behavior:smooth; overscroll-behavior-x:contain; -webkit-overflow-scrolling:touch; touch-action:pan-x pan-y; scrollbar-width:none; padding:2px 4px 12px; }
            .trilho::-webkit-scrollbar { display:none; }
            .cartao { flex:0 0 calc(100% - 8px); height:430px; scroll-snap-align:center; scroll-snap-stop:always; display:flex; flex-direction:column; overflow:hidden; background:linear-gradient(145deg,#121530,#0d1025); border:1px solid #303a59; border-radius:18px; box-shadow:0 10px 28px rgba(0,0,0,.32); }
            .cartao.preparacao { border-color:#2563eb; }
            .cartao.almoco { border-color:#f59e0b; }
            .cartao.retorno { border-color:#16a34a; }
            .cartao.feita { border-color:#22c55e; box-shadow:0 0 0 2px rgba(34,197,94,.18),0 10px 28px rgba(0,0,0,.32); }
            .cartao.feita .topo-card { background:linear-gradient(135deg,rgba(22,163,74,.18),rgba(22,163,74,.03)); }
            .topo-card { padding:18px 18px 13px; border-bottom:1px solid rgba(141,160,184,.18); }
            .selo { display:inline-block; color:#bfdbfe; background:#1d4ed8; font-size:11px; font-weight:900; letter-spacing:.08em; padding:5px 9px; border-radius:999px; }
            .almoco .selo { background:#92400e; color:#fef3c7; }
            .retorno .selo { background:#166534; color:#dcfce7; }
            h2 { margin:11px 0 6px; color:#f8fafc; font-size:21px; line-height:1.18; }
            .meta { color:#8da0b8; font-size:12px; line-height:1.45; }
            .conteudo-card { flex:1; overflow-y:auto; padding:14px 16px 8px; }
            .status { display:block; margin-bottom:12px; padding:9px 11px; border-radius:10px; font-size:13px; font-weight:800; }
            .status.concluido { color:#bbf7d0; background:rgba(22,163,74,.15); }
            .status.pendente { color:#fde68a; background:rgba(245,158,11,.14); }
            .acao { margin-bottom:11px; padding:12px; border-radius:12px; border-left:4px solid; background:rgba(255,255,255,.035); }
            .acao.coleta { border-color:#f59e0b; }
            .acao.entrega { border-color:#16a34a; }
            .acao-titulo { font-size:13px; font-weight:900; color:#f8fafc; margin-bottom:7px; }
            .materiais { color:#e4e8f4; font-size:13px; line-height:1.45; }
            .obra { color:#8da0b8; font-size:11.5px; font-style:italic; margin-top:7px; }
            .baixa { color:#86efac; font-size:12px; font-weight:800; margin-top:7px; }
            .mensagem-etapa { color:#cbd5e1; font-size:15px; line-height:1.55; padding:18px 6px; }
            .rodape-card { display:grid; gap:8px; padding:10px 14px 15px; border-top:1px solid rgba(141,160,184,.14); }
            .marcar-feita { display:block; width:100%; padding:12px 10px; border-radius:11px; border:1px solid #22c55e; background:rgba(22,163,74,.08); color:#bbf7d0; font-size:13px; font-weight:900; cursor:pointer; text-align:center; text-decoration:none; }
            .marcar-feita.ativa { background:linear-gradient(135deg,#16a34a,#15803d); color:white; }
            .marcar-feita:disabled { cursor:default; opacity:1; background:linear-gradient(135deg,#16a34a,#15803d); color:white; }
            .gps { display:block; margin:0; padding:13px 12px; text-decoration:none; text-align:center; color:white; font-size:14px; font-weight:900; border-radius:11px; background:linear-gradient(135deg,#2563eb,#1d4ed8); box-shadow:0 5px 13px rgba(37,99,235,.28); }
            .controles { display:grid; grid-template-columns:1fr auto 1fr; align-items:center; gap:10px; padding:0 4px; }
            .controle { border:1px solid #303a59; background:#151a31; color:#e4e8f4; border-radius:10px; padding:10px 8px; font-weight:800; cursor:pointer; }
            .controle:disabled { opacity:.35; }
            .pontos { display:flex; gap:5px; justify-content:center; max-width:130px; overflow:hidden; }
            .ponto { width:7px; height:7px; padding:0; border:0; border-radius:50%; background:#475569; cursor:pointer; }
            .ponto.ativo { width:18px; border-radius:999px; background:#2563eb; }
        </style></head><body>
            <div class="barra"><span>↔️ Deslize • sincronizado</span><div class="resumo-topo"><span id="feitas" class="feitas">0 feitas</span><span id="contador" class="contador">1 de __TOTAL__</span></div></div>
            <div id="trilho" class="trilho">__CARTOES__</div>
            <div class="controles"><button id="anterior" class="controle" onclick="mover(-1)">← Anterior</button><div id="pontos" class="pontos"></div><button id="proxima" class="controle" onclick="mover(1)">Próxima →</button></div>
        <script>
            const trilho = document.getElementById('trilho');
            const cartoes = Array.from(trilho.querySelectorAll('.cartao'));
            const contador = document.getElementById('contador');
            const anterior = document.getElementById('anterior');
            const proxima = document.getElementById('proxima');
            const pontos = document.getElementById('pontos');
            const feitasEl = document.getElementById('feitas');
            let atual = 0;
            cartoes.forEach((_, i) => { const p=document.createElement('button'); p.className='ponto'; p.onclick=()=>ir(i); pontos.appendChild(p); });
            function atualizarFeitas() { const botoes=Array.from(document.querySelectorAll('.marcar-feita')); const total=botoes.length; const feitas=botoes.filter(b=>b.dataset.feita==='1').length; feitasEl.textContent=`${feitas}/${total} ${feitas===1?'feita':'feitas'}`; }
            function prepararEnvio(botao) { botao.textContent='⏳ Salvando...'; botao.style.pointerEvents='none'; }
            function atualizar(i) { atual=Math.max(0,Math.min(cartoes.length-1,i)); contador.textContent=`${atual+1} de ${cartoes.length}`; anterior.disabled=atual===0; proxima.disabled=atual===cartoes.length-1; Array.from(pontos.children).forEach((p,j)=>p.classList.toggle('ativo',j===atual)); }
            function ir(i) { const indice=Math.max(0,Math.min(cartoes.length-1,i)); const alvo=cartoes[indice]; trilho.scrollTo({left:alvo.offsetLeft-trilho.offsetLeft,behavior:'smooth'}); atualizar(indice); }
            function mover(delta) { ir(atual+delta); }
            let timer; trilho.addEventListener('scroll',()=>{ clearTimeout(timer); timer=setTimeout(()=>{ const centro=trilho.scrollLeft+trilho.clientWidth/2; let melhor=0,dist=Infinity; cartoes.forEach((c,i)=>{ const d=Math.abs(c.offsetLeft+c.offsetWidth/2-centro); if(d<dist){dist=d;melhor=i;} }); atualizar(melhor); },80); },{passive:true});
            atualizarFeitas(); atualizar(0);
        </script></body></html>
        """.replace("__CARTOES__", "".join(cartoes_mobile)).replace("__TOTAL__", str(len(cartoes_mobile)))
        st.components.v1.html(html_carrossel, height=520, scrolling=False)
    else:
        st.info("A rota ainda não possui etapas para exibir.")

    st.divider()
    st.markdown("#### 🗺️ Visão Geral da Rota")
    m_mobile = folium.Map(location=[-3.7319, -38.5267], zoom_start=12, tiles="OpenStreetMap")
    path_points_mobile = []
    offsets_dict_mobile = {}
    
    def apply_offset_mobile(lat, lon):
        key = (round(lat, 4), round(lon, 4))
        offsets_dict_mobile[key] = offsets_dict_mobile.get(key, 0) + 1
        cnt = offsets_dict_mobile[key]
        if cnt > 1: return lat - 0.00035 * (cnt - 1), lon + 0.00035 * (cnt - 1)
        return lat, lon

    p_num_mapa = 1
    if p_saida in locais_dict:
        lat_s, lon_s = apply_offset_mobile(*locais_dict[p_saida])
        path_points_mobile.append([lat_s, lon_s])

    for i, step in enumerate(route_steps):
        if step.get('destino') and step['destino'] in locais_dict:
            if step['type'] in ['lunch', 'return']: continue
            if (i == 0 and step['destino'] == p_saida): continue 

            lat_orig, lon_orig = locais_dict[step['destino']]
            lat, lon = apply_offset_mobile(lat_orig, lon_orig)
            path_points_mobile.append([lat, lon])

            acoes = [a[0] for a in step.get('actions', [])]
            tem_coleta, tem_entrega = "COLETAR" in acoes, "ENTREGAR" in acoes
            fundo_marcador = "linear-gradient(90deg, #f59e0b 0 50%, #16a34a 50% 100%)" if (tem_coleta and tem_entrega) else "#f59e0b" if tem_coleta else "#16a34a"
            
            popup_html = f"<b>Parada {p_num_mapa}: {html_escape(str(step['destino']))}</b>"
            folium.Marker([lat, lon], popup=folium.Popup(popup_html, max_width=280), icon=folium.DivIcon(html=f'''<div style="background: {fundo_marcador}; color: white; border: 2px solid white; border-radius: 50%; width: 30px; height: 30px; display: flex; justify-content: center; align-items: center; font-weight: bold; box-shadow: 2px 2px 5px rgba(0,0,0,0.5); font-size: 14px;">{p_num_mapa}</div>''')).add_to(m_mobile)
            p_num_mapa += 1

    if len(geometria_rota) > 1: folium.PolyLine(geometria_rota, color="#2563eb", weight=5, opacity=0.85).add_to(m_mobile)
    if len(path_points_mobile) > 1: m_mobile.fit_bounds(path_points_mobile, padding=(30, 30), max_zoom=14)
    if p_saida in locais_dict: folium.Marker([path_points_mobile[0][0], path_points_mobile[0][1]], popup=folium.Popup(f"<b>Saída: {html_escape(str(p_saida))}</b>", max_width=280), z_index_offset=1000, icon=folium.DivIcon(html=f'''<div style="background: linear-gradient(135deg, #2563eb, #1d4ed8); color: white; border: 3px solid white; border-radius: 50%; width: 34px; height: 34px; display: flex; justify-content: center; align-items: center; box-shadow: 2px 2px 7px rgba(0,0,0,0.6); font-size: 16px;">🏁</div>''')).add_to(m_mobile)

    st_folium(m_mobile, height=400, use_container_width=True, returned_objects=[])
    st.markdown("<div style='text-align: center; font-size: 13px; margin-top: 5px; color: #8da0b8;'><b>Legenda:</b> 🟡 Coleta | 🟢 Entrega | 🏁 Início | 🟡🟢 Ambos</div>", unsafe_allow_html=True)
    st.divider()
    st.caption("Central de Logística APROAR")
    st.stop()

# =====================================================================
# TORRE DE CONTROLE (PC)
# =====================================================================
TRELLO_JSON_URL = "https://trello.com/b/tyR8YgDF.json"
RASTREADOR_LOGIN_URLS = ["https://portal.protegeexpress.com.br/sistema/login.aspx", "http://portal.protegeexpress.com.br/sistema/login.aspx"]
RASTREADOR_VEICULOS_PADRAO = "007046861,807289138"
VELOCIDADE_MEDIA_KMH = 25.0

COLUNAS_DEMANDAS = ["id", "Obra", "Origem", "Destino", "Materiais", "Urgência", "Peso", "Tempo_Coleta", "Tempo_Entrega", "Supervisor"]
UNIDADES_PROPRIAS = ["FIEC", "CENTRO", "MARACANAÚ", "SEBRAE", "UNIFOR", "PARANGABA", "HORIZONTE", "MUSEU", "BARRA", "ESCRITÓRIO", "CASA DA INDÚSTRIA"]

SUPERVISORES_MAP = {
    "BARRA": "Luis Eduardo Rodrigues", "SESI BARRA DO CEARÁ": "Luis Eduardo Rodrigues", "SENAI BARRA DO CEARÁ": "Luis Eduardo Rodrigues",
    "CENTRO": "Victor Bezerra", "SENAI CENTRO": "Victor Bezerra", "ESCOLA CENTRO": "Victor Bezerra", "NR SAÚDE": "Victor Bezerra", "MUSEU": "Victor Bezerra", "SESI MUSEU": "Victor Bezerra",
    "CASA DA INDÚSTRIA": "Gustavo Souza", "FIEC": "Gustavo Souza",
    "MARACANAÚ": "Neto Porto", "SESI ALBANO FRANCO": "Neto Porto", "SESI CLUBE DA PARCERIA": "Neto Porto", "SENAI ISTEMM": "Neto Porto", "SENAI CETAFR": "Neto Porto",
    "HORIZONTE": "Soares Junior", "SESI HORIZONTE": "Soares Junior", "SENAI HORIZONTE": "Soares Junior", "SEBRAE": "Soares Junior",
    "UNIFOR": "Joel Lima", "ESCRITÓRIO": "Sede / Logística", "PARANGABA": "Sede / Logística"
}

TEAMS_SECRET_KEYS = {"Luis Eduardo Rodrigues": "luis_eduardo", "Victor Bezerra": "victor_bezerra", "Gustavo Souza": "gustavo_souza", "Neto Porto": "neto_porto", "Soares Junior": "soares_junior", "Joel Lima": "joel_lima", "Sede / Logística": "sede_logistica", "Geral / Logística": "geral_logistica"}
LOCAL_BASE_ENDERECO = "Rua Professor Mário Rocha, 84 - Joaquim Távora, Fortaleza - CE, 60120-200"
LOCAL_BASE_COORDS = (-3.752270016704, -38.51537298342)
ALIASES_LOCAL_BASE = {"ALMOXARIFADO", "ESCRITÓRIO"}

# ENDEREÇOS FIXOS DO SISTEMA
ENDERECOS_PADRAO = [
    ("CASA DA INDÚSTRIA", "Av. Barão de Studart, 1980 - Aldeota, Fortaleza - CE"), 
    ("SENAI CENTRO", "R. Padre Ibiapina, 1280 - Jacarecanga, Fortaleza - CE"), 
    ("ESCOLA CENTRO", "R. Padre Ibiapina, 1280 - Jacarecanga, Fortaleza - CE"), 
    ("CENTRO", "R. Padre Ibiapina, 1280 - Jacarecanga, Fortaleza - CE"), 
    ("NR SAÚDE", "R. Padre Ibiapina, 1280 - Jacarecanga, Fortaleza - CE"), 
    ("SESI BARRA DO CEARÁ", "Rua Florencio de Alencar, 900 - Barra do Ceará, Fortaleza - CE"), 
    ("SENAI BARRA DO CEARÁ", "Rua Florencio de Alencar, 900 - Barra do Ceará, Fortaleza - CE"), 
    ("BARRA", "Rua Florencio de Alencar, 900 - Barra do Ceará, Fortaleza - CE"),
    ("SESI ALBANO FRANCO", "Av. Sen. Virgílio Távora, 1395 - Distrito Industrial I, Maracanaú - CE"), 
    ("SESI CLUBE DA PARCERIA", "Av. Sen. Virgílio Távora, 1395 - Distrito Industrial I, Maracanaú - CE"), 
    ("SENAI ISTEMM", "Av. Sen. Virgílio Távora, 1395 - Distrito Industrial I, Maracanaú - CE"), 
    ("SENAI CETAFR", "Av. Sen. Virgílio Távora, 1395 - Distrito Industrial I, Maracanaú - CE"), 
    ("MARACANAÚ", "Av. Sen. Virgílio Távora, 1395 - Distrito Industrial I, Maracanaú - CE"),
    ("SESI PARANGABA", "Av. João Pessoa, 6754 - Parangaba, Fortaleza - CE"), 
    ("SENAI PARANGABA", "Av. João Pessoa, 6760 - Damas, Fortaleza - CE"), 
    ("PARANGABA", "Av. João Pessoa, 6760 - Damas, Fortaleza - CE"),
    ("SESI MUSEU", "R. Dr. João Moreira, 143 - Centro, Fortaleza - CE, 60030-000"), 
    ("MUSEU", "R. Dr. João Moreira, 143 - Centro, Fortaleza - CE, 60030-000"), 
    ("SESI SOBRAL", "Av. Dr. José Arimathéa Monte e Silva, 1003 - Junco, Sobral - CE"), 
    ("ESCRITÓRIO", LOCAL_BASE_ENDERECO), 
    ("ALMOXARIFADO", LOCAL_BASE_ENDERECO), 
    ("ESPAÇO SMART", "BR-116, 9370 - Barroso, Fortaleza - CE, 60862-735"), 
    ("ALDEOTA", "Rua Dr. José Lourenço, 1990 - Aldeota, Fortaleza - CE"), 
    ("EDSON QUEIROZ", "Av. Dr. Valmir Pontes, 675 - Edson Queiroz, Fortaleza - CE"), 
    ("FIEC", "Rua Dr. José Lourenço, 1990 - Aldeota, Fortaleza - CE"), 
    ("UNIFOR", "Av. Dr. Valmir Pontes, 675 - Edson Queiroz, Fortaleza - CE"), 
    ("HORIZONTE", "R. Raimunda Pontes - Planalto Horizonte, Horizonte - CE"), 
    ("SEBRAE", "Avenida Monsenhor Tabosa, 777 - Meireles, Fortaleza - CE"), 
    ("LECI FERRAGENS", "Rua Gen. Clarindo de Queiroz, 1668 - Centro, Fortaleza - CE"),
    ("ELÉTRICA FORTALEZA", "Centro, Fortaleza - CE"), 
    ("ELETRICA FORTALEZA", "Centro, Fortaleza - CE"), 
    ("DEPÓSITO JP", "Edson Queiroz, Fortaleza - CE"),
    ("DEPOSITO JP", "Edson Queiroz, Fortaleza - CE"),
    ("JP CONSTRUÇÃO", "Edson Queiroz, Fortaleza - CE"),
    ("JP CONSTRUCOES", "Edson Queiroz, Fortaleza - CE")
]

@st.cache_resource(show_spinner=False)
def inicializar_bd():
    """Prepara a estrutura do banco uma única vez por processo do aplicativo."""
    queries = [
        "CREATE TABLE IF NOT EXISTS locais (apelido TEXT PRIMARY KEY, endereco TEXT, lat REAL, lon REAL)",
        "CREATE TABLE IF NOT EXISTS locais_removidos (apelido TEXT PRIMARY KEY)",
        "CREATE TABLE IF NOT EXISTS config_frota (id SERIAL PRIMARY KEY, consumo REAL, preco_gasolina REAL)",
        "CREATE TABLE IF NOT EXISTS abastecimentos (id SERIAL PRIMARY KEY, data TEXT, litros REAL, valor_litro REAL, manutencao REAL, obs TEXT, veiculo TEXT DEFAULT 'Strada')",
        "CREATE TABLE IF NOT EXISTS registro_km (id SERIAL PRIMARY KEY, data TEXT, km REAL, obs TEXT, veiculo TEXT DEFAULT 'Strada')",
        "CREATE TABLE IF NOT EXISTS historico_concluidos (id TEXT PRIMARY KEY, obra TEXT, origem TEXT, destino TEXT, materiais TEXT, data_conclusao TEXT, hora_conclusao TEXT)",
        "CREATE TABLE IF NOT EXISTS rastreio_paradas (id SERIAL PRIMARY KEY, data TEXT, placa TEXT, local TEXT, hora_chegada TEXT, hora_saida TEXT)",
        "CREATE TABLE IF NOT EXISTS inicio_movimento (placa TEXT, data TEXT, hora_inicio TEXT, PRIMARY KEY(placa, data))",
        "CREATE TABLE IF NOT EXISTS webhooks_teams (setor TEXT PRIMARY KEY, url TEXT)",
        "CREATE TABLE IF NOT EXISTS config_trello (id SERIAL PRIMARY KEY, api_key TEXT, token TEXT, id_lista_concluida TEXT)",
        "CREATE TABLE IF NOT EXISTS rota_ativa (id SERIAL PRIMARY KEY, data_rota TEXT, json_route TEXT, json_locais TEXT, json_geometria TEXT, json_enderecos TEXT, total_km REAL)",
        SQL_TABELA_CHECKINS_DAVI,
        "ALTER TABLE rota_ativa ADD COLUMN IF NOT EXISTS fonte_matriz TEXT",
        "ALTER TABLE rota_ativa ADD COLUMN IF NOT EXISTS horario_matriz TEXT",
        "CREATE INDEX IF NOT EXISTS idx_historico_concluidos_data ON historico_concluidos (data_conclusao)",
        "CREATE INDEX IF NOT EXISTS idx_inicio_movimento_data ON inicio_movimento (data)",
        "CREATE INDEX IF NOT EXISTS idx_rastreio_paradas_data_placa ON rastreio_paradas (data, placa)",
        "CREATE INDEX IF NOT EXISTS idx_rastreio_paradas_abertas ON rastreio_paradas (data, placa, hora_saida)",
    ]

    # Uma única sessão/commit evita dezenas de viagens separadas até o Supabase.
    conn_db = get_conn()
    with conn_db.session as s:
        for query in queries:
            s.execute(text(query))

        s.execute(text("INSERT INTO config_frota (id, consumo, preco_gasolina) VALUES (1, 11.5, 5.90) ON CONFLICT (id) DO NOTHING"))
        s.execute(text("INSERT INTO webhooks_teams (setor, url) VALUES ('Geral / Logística', '') ON CONFLICT (setor) DO NOTHING"))
        for sup in set(SUPERVISORES_MAP.values()):
            s.execute(text("INSERT INTO webhooks_teams (setor, url) VALUES (:sup, '') ON CONFLICT (setor) DO NOTHING"), {"sup": sup})

        locais_existentes = {
            row[0]: row[1]
            for row in s.execute(text("SELECT apelido, endereco FROM locais")).fetchall()
        }
        locais_removidos = {
            row[0]
            for row in s.execute(text("SELECT apelido FROM locais_removidos")).fetchall()
        }

        for apelido, end in ENDERECOS_PADRAO:
            if apelido in locais_existentes:
                if locais_existentes[apelido] != end:
                    s.execute(text("UPDATE locais SET endereco = :end, lat = NULL, lon = NULL WHERE apelido = :apelido"), {"end": end, "apelido": apelido})
            elif apelido not in locais_removidos:
                s.execute(text("INSERT INTO locais (apelido, endereco) VALUES (:apelido, :end)"), {"apelido": apelido, "end": end})

        s.execute(text("DELETE FROM locais WHERE UPPER(TRIM(apelido)) = 'DESCONHECIDO'"))
        for alias in ALIASES_LOCAL_BASE:
            s.execute(text("INSERT INTO locais (apelido, endereco, lat, lon) VALUES (:alias, :end, :lat, :lon) ON CONFLICT (apelido) DO UPDATE SET endereco=EXCLUDED.endereco, lat=EXCLUDED.lat, lon=EXCLUDED.lon"), {"alias": alias, "end": LOCAL_BASE_ENDERECO, "lat": LOCAL_BASE_COORDS[0], "lon": LOCAL_BASE_COORDS[1]})

        s.commit()

    return True

# Garante a inicialização segura do banco Supabase
try:
    inicializar_bd()
    if "rota_gerada" not in st.session_state or not st.session_state.get("rota_gerada"):
        res_rota = fetch_one("SELECT json_route, json_locais, json_geometria, json_enderecos, total_km, fonte_matriz, horario_matriz FROM rota_ativa WHERE id = 1 AND data_rota = :data", {"data": DATA_REF_ROTA_STR})
        if res_rota:
            st.session_state['route_steps'] = json.loads(res_rota[0])
            st.session_state['locais_dict'] = json.loads(res_rota[1])
            st.session_state['geometria_rota'] = json.loads(res_rota[2])
            st.session_state['enderecos_dict'] = json.loads(res_rota[3])
            st.session_state['total_km'] = res_rota[4]
            st.session_state['fonte_matriz_rota'] = res_rota[5] or "OSRM — malha viária sem trânsito ao vivo"
            st.session_state['horario_matriz_rota'] = res_rota[6] or ""
            if st.session_state['route_steps']:
                st.session_state['p_saida'] = st.session_state['route_steps'][0]['destino']
                h, m = map(int, st.session_state['route_steps'][-1]['saida'].split(':'))
                st.session_state['horario_conclusao_min'] = h * 60 + m
            st.session_state['geometria_viaria'] = True
            st.session_state['rota_gerada'] = True
            st.session_state['data_rota'] = DATA_REF_ROTA_STR
except:
    st.error("⚠️ Atenção: Não foi possível conectar ao Banco de Dados Supabase. Verifique se as credenciais estão corretas nos Secrets do Streamlit.")
    st.stop()

# =====================================================================
# LÓGICA DE EXTRAÇÃO E AUTOMAÇÃO DO TRELLO
# =====================================================================
@st.cache_data(ttl=60, show_spinner=False)
def obter_dados_trello():
    try:
        resposta = requests.get(TRELLO_JSON_URL, timeout=20)
        return resposta.json()
    except Exception as e:
        return None

def identificar_grupo_teams(destino, obra=""):
    texto = normalizar_local(f"{obra} {destino}")
    regras = [(("GERAL / LOGÍSTICA",), "geral_logistica"),(("CASA DA INDÚSTRIA", "FIEC"), "casa_industria"),(("MARACANAÚ",), "maracanau"),(("HORIZONTE",), "horizonte"),(("SEBRAE",), "sebrae"),(("MUSEU",), "museu"),(("BARRA",), "barra"),(("CENTRO", "NR SAÚDE"), "centro"),(("UNIFOR",), "unifor"),(("PARANGABA", "ESCRITÓRIO"), "sede_parangaba")]
    for termos, chave in regras:
        if any(termo in texto for termo in termos): return chave
    return ""

def obter_webhook_teams(setor, supervisor=None, obra=""):
    chave_unidade = identificar_grupo_teams(setor, obra)
    if chave_unidade:
        try:
            url_secret = str(st.secrets["teams_unidades"].get(chave_unidade, "")).strip()
            if url_secret: return url_secret, "Secrets — grupo da unidade"
        except: pass
    chave_supervisor = TEAMS_SECRET_KEYS.get(supervisor or setor)
    if chave_supervisor:
        try:
            url_secret = str(st.secrets["teams"].get(chave_supervisor, "")).strip()
            if url_secret: return url_secret, "Secrets — cadastro anterior"
        except: pass
    try:
        registro = fetch_one("SELECT url FROM webhooks_teams WHERE setor = :setor", {"setor": supervisor or setor})
        if registro and registro[0]: return registro[0].strip(), "Banco local"
    except: pass
    return "", "Não configurado"

def disparar_teams(webhook_url, titulo, mensagem):
    if not webhook_url or not webhook_url.lower().startswith("https://"): return False, "O link precisa ser um webhook HTTPS do Teams Workflows."
    payload = {"type": "message", "attachments": [{"contentType": "application/vnd.microsoft.card.adaptive", "contentUrl": None, "content": {"$schema": "http://adaptivecards.io/schemas/adaptive-card.json", "type": "AdaptiveCard", "version": "1.2", "body": [{"type": "TextBlock", "text": titulo, "size": "Medium", "weight": "Bolder", "wrap": True}, {"type": "TextBlock", "text": mensagem, "wrap": True, "spacing": "Medium"}],},}],}
    ultimo_erro = ""
    for tentativa in range(3):
        try:
            resposta = requests.post(webhook_url, json=payload, timeout=15)
            if 200 <= resposta.status_code < 300: return True, "Mensagem aceita pelo Teams."
            ultimo_erro = f"Teams respondeu com o código {resposta.status_code}."
            if resposta.status_code != 429 and resposta.status_code < 500: break
        except requests.RequestException: ultimo_erro = "Não foi possível alcançar o Teams."
        if tentativa < 2: time.sleep(1 + tentativa)
    return False, ultimo_erro or "Falha desconhecida ao enviar a mensagem."

def is_in_ceara(lat, lon): return -7.5 <= lat <= -2.5 and -42.0 <= lon <= -37.0

def buscar_coordenadas(endereco):
    if not endereco: return None, None
    endereco_limpo = endereco.strip()
    match_coords = re.search(r'^(-?\d+\.\d+)[\s,;]+(-?\d+\.\d+)$', endereco_limpo)
    if match_coords:
        lat, lon = float(match_coords.group(1)), float(match_coords.group(2))
        if is_in_ceara(lat, lon): return lat, lon
    try:
        url_arcgis = "https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates?f=json&singleLine=" + urllib.parse.quote(endereco_limpo + ", Ceará, Brasil") + "&maxLocations=1"
        req = urllib.request.Request(url_arcgis, headers={'User-Agent': 'AproarLogisticsWeb/1.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read())
            if data.get('candidates'):
                lat, lon = float(data['candidates'][0]['location']['y']), float(data['candidates'][0]['location']['x'])
                if is_in_ceara(lat, lon): return lat, lon
    except: pass
    return None, None

def normalizar_local(nome):
    if not nome: return ""
    n = nome.upper().strip()
    if "MARACANAU" in n: n = n.replace("MARACANAU", "MARACANAÚ")
    if "ESCRITORIO" in n: n = n.replace("ESCRITORIO", "ESCRITÓRIO")
    if "DEPÓSITO" in n: n = n.replace("DEPÓSITO", "DEPOSITO")
    if "ESPACO" in n: n = n.replace("ESPACO", "ESPAÇO")
    return n

def canonicalizar_ponto_rota(nome):
    texto = normalizar_local(str(nome or ""))
    texto = re.sub(r"[\\*_`]+", "", texto).strip(" :-\t\r\n")
    texto = re.sub(r'^(?:O|A|OS|AS)\s+', '', texto)
    
    texto_limpo = remover_acentos(texto)
    for sin, oficial in DICIONARIO_SINONIMOS.items():
        if texto_limpo == remover_acentos(sin):
            texto = oficial
            
    if texto in ALIASES_LOCAL_BASE: return "ESCRITÓRIO"
    return texto

def garantir_gps_local_base():
    coordenadas = None
    for alias in ("ESCRITÓRIO", "ALMOXARIFADO"):
        registro = fetch_one("SELECT lat, lon FROM locais WHERE apelido = :alias", {"alias": alias})
        if registro and registro[0] is not None and registro[1] is not None:
            coordenadas = (float(registro[0]), float(registro[1]))
            break
    if coordenadas is None: coordenadas = LOCAL_BASE_COORDS
    if coordenadas is not None:
        for alias in ALIASES_LOCAL_BASE: 
            execute_db("INSERT INTO locais (apelido, endereco, lat, lon) VALUES (:alias, :end, :lat, :lon) ON CONFLICT (apelido) DO UPDATE SET endereco=EXCLUDED.endereco, lat=EXCLUDED.lat, lon=EXCLUDED.lon", {"alias": alias, "end": LOCAL_BASE_ENDERECO, "lat": coordenadas[0], "lon": coordenadas[1]})
    return coordenadas

def carregar_chave_google_routes():
    """Lê a chave sem expô-la no código e aceita nomes usuais nos Secrets."""
    caminhos = [
        ("google_routes", "api_key"),
        ("google_maps", "api_key"),
    ]
    for secao, campo in caminhos:
        try:
            chave = str(st.secrets[secao][campo]).strip()
            if chave:
                return chave
        except Exception:
            pass

    for campo in ("GOOGLE_MAPS_API_KEY", "google_maps_api_key"):
        try:
            chave = str(st.secrets[campo]).strip()
            if chave:
                return chave
        except Exception:
            pass
    return ""

def carregar_chave_tomtom():
    """Lê a chave gratuita da TomTom sem expô-la no código."""
    try:
        chave = str(st.secrets["tomtom"]["api_key"]).strip()
        if chave:
            return chave
    except Exception:
        pass
    for campo in ("TOMTOM_API_KEY", "tomtom_api_key"):
        try:
            chave = str(st.secrets[campo]).strip()
            if chave:
                return chave
        except Exception:
            pass
    return ""

def _duracao_google_minutos(valor):
    try:
        return float(str(valor).rstrip("s")) / 60.0
    except (TypeError, ValueError):
        return None

def calcular_matriz_google_trafego(coords, horario_partida):
    """Matriz viária com trânsito ao vivo/preditivo via Google Routes."""
    chave = carregar_chave_google_routes()
    quantidade = len(coords)
    if not chave or quantidade < 2 or quantidade > 100:
        return None

    agora_seguro = datetime.now(FUSO_LOCAL) + timedelta(minutes=1)
    partida = horario_partida if horario_partida and horario_partida > agora_seguro else agora_seguro
    partida_rfc3339 = partida.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    destinos = [
        {"waypoint": {"location": {"latLng": {"latitude": float(lat), "longitude": float(lon)}}}}
        for lat, lon in coords
    ]
    distancias = [[None for _ in range(quantidade)] for _ in range(quantidade)]
    duracoes = [[None for _ in range(quantidade)] for _ in range(quantidade)]
    elementos_por_bloco = 100
    origens_por_bloco = max(1, elementos_por_bloco // quantidade)

    url = "https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": chave,
        "X-Goog-FieldMask": "originIndex,destinationIndex,duration,staticDuration,distanceMeters,status,condition",
    }

    def consultar_bloco(indices_origem):
        origens = [
            {
                "waypoint": {"location": {"latLng": {"latitude": float(coords[i][0]), "longitude": float(coords[i][1])}}},
                "routeModifiers": {"avoidFerries": True},
            }
            for i in indices_origem
        ]
        payload = {
            "origins": origens,
            "destinations": destinos,
            "travelMode": "DRIVE",
            "routingPreference": "TRAFFIC_AWARE_OPTIMAL",
            "trafficModel": "BEST_GUESS",
            "departureTime": partida_rfc3339,
            "languageCode": "pt-BR",
            "regionCode": "br",
            "units": "METRIC",
        }
        resposta = requests.post(url, headers=headers, json=payload, timeout=20)
        resposta.raise_for_status()
        elementos = resposta.json()
        if not isinstance(elementos, list):
            raise ValueError("Resposta inválida da matriz do Google Routes")
        return indices_origem, elementos

    try:
        blocos = [
            list(range(inicio, min(inicio + origens_por_bloco, quantidade)))
            for inicio in range(0, quantidade, origens_por_bloco)
        ]
        # A API limita a matriz de trânsito ótimo a 100 elementos por chamada.
        # Os lotes independentes rodam juntos para não multiplicar a espera.
        with ThreadPoolExecutor(max_workers=min(4, len(blocos))) as executor:
            futuros = [executor.submit(consultar_bloco, indices) for indices in blocos]
            for futuro in as_completed(futuros):
                indices_origem, elementos = futuro.result()
                for elemento in elementos:
                    if elemento.get("condition") != "ROUTE_EXISTS":
                        continue
                    origem_global = indices_origem[int(elemento.get("originIndex", 0))]
                    destino_global = int(elemento.get("destinationIndex", 0))
                    duracao_min = _duracao_google_minutos(elemento.get("duration"))
                    distancia_m = elemento.get("distanceMeters")
                    if duracao_min is None or distancia_m is None:
                        continue
                    distancias[origem_global][destino_global] = float(distancia_m) / 1000.0
                    duracoes[origem_global][destino_global] = duracao_min

        for i in range(quantidade):
            distancias[i][i], duracoes[i][i] = 0.0, 0.0
        if any(valor is None for linha in distancias for valor in linha):
            return None
        if any(valor is None for linha in duracoes for valor in linha):
            return None
        return distancias, duracoes
    except Exception:
        return None

def calcular_matriz_tomtom_trafego(coords, horario_partida):
    """Matriz de distâncias e tempos com trânsito ao vivo no plano gratuito TomTom."""
    chave = carregar_chave_tomtom()
    quantidade = len(coords)
    if not chave or quantidade < 2:
        return None

    agora_seguro = datetime.now(FUSO_LOCAL) + timedelta(minutes=1)
    partida = horario_partida if horario_partida and horario_partida > agora_seguro else agora_seguro
    partida_rfc3339 = partida.isoformat(timespec="seconds")

    pontos = [
        {"point": {"latitude": float(lat), "longitude": float(lon)}}
        for lat, lon in coords
    ]
    payload = {
        "origins": pontos,
        "destinations": pontos,
        "options": {
            "departAt": partida_rfc3339,
            "routeType": "fastest",
            "traffic": "live",
            "travelMode": "car",
        },
    }

    try:
        resposta = requests.post(
            "https://api.tomtom.com/routing/matrix/2",
            params={"key": chave},
            headers={"Content-Type": "application/json", "Accept-Encoding": "gzip"},
            json=payload,
            timeout=35,
        )
        resposta.raise_for_status()
        dados = resposta.json().get("data", [])
        distancias = [[None for _ in range(quantidade)] for _ in range(quantidade)]
        duracoes = [[None for _ in range(quantidade)] for _ in range(quantidade)]

        for celula in dados:
            resumo = celula.get("routeSummary") or {}
            origem = int(celula.get("originIndex", -1))
            destino = int(celula.get("destinationIndex", -1))
            distancia_m = resumo.get("lengthInMeters")
            duracao_s = resumo.get("travelTimeInSeconds")
            if 0 <= origem < quantidade and 0 <= destino < quantidade and distancia_m is not None and duracao_s is not None:
                distancias[origem][destino] = float(distancia_m) / 1000.0
                duracoes[origem][destino] = float(duracao_s) / 60.0

        for i in range(quantidade):
            distancias[i][i], duracoes[i][i] = 0.0, 0.0
        if any(valor is None for linha in distancias for valor in linha):
            return None
        if any(valor is None for linha in duracoes for valor in linha):
            return None
        return distancias, duracoes
    except Exception:
        return None

def calcular_matriz_rotas(coords, horario_partida=None):
    matriz_tomtom = calcular_matriz_tomtom_trafego(coords, horario_partida)
    if matriz_tomtom:
        return matriz_tomtom[0], matriz_tomtom[1], "TomTom Routing — trânsito ao vivo e histórico (gratuito)"

    matriz_google = calcular_matriz_google_trafego(coords, horario_partida)
    if matriz_google:
        return matriz_google[0], matriz_google[1], "Google Routes — trânsito ao vivo e preditivo"

    try:
        coords_str = ";".join([f"{lon},{lat}" for lat, lon in coords])
        url = f"https://router.project-osrm.org/table/v1/driving/{coords_str}?annotations=distance,duration"
        req = urllib.request.Request(url, headers={'User-Agent': 'AproarLogisticsWeb/1.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            res = json.loads(response.read())
            if res.get('code') == 'Ok':
                distancias = [[dist / 1000.0 for dist in row] for row in res['distances']]
                duracoes = [[dur / 60.0 for dur in row] for row in res['durations']]
                return distancias, duracoes, "OSRM — malha viária sem trânsito ao vivo"
    except: pass
    distancias, duracoes = [], []
    for i in range(len(coords)):
        row_d, row_t = [], []
        for j in range(len(coords)):
            dLat, dLon = math.radians(coords[j][0] - coords[i][0]), math.radians(coords[j][1] - coords[i][1])
            a = math.sin(dLat/2)**2 + math.cos(math.radians(coords[i][0]))*math.cos(math.radians(coords[j][0]))*math.sin(dLon/2)**2
            c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
            km = (6371 * c) * 1.3
            row_d.append(km)
            row_t.append((km / VELOCIDADE_MEDIA_KMH) * 60)
        distancias.append(row_d)
        duracoes.append(row_t)
    return distancias, duracoes, "Estimativa geográfica de contingência"

def pontuar_parada_rota(atual, ponto, unpicked, carrying, estrategia, get_dist_dur):
    """Pontua a próxima parada considerando distância, prioridade e retornos evitáveis."""
    distancia, duracao = get_dist_dur(atual, ponto)
    custo_deslocamento = distancia + (duracao * 0.1)

    coletas_aqui = [t for t in unpicked if t['Origem'] == ponto]
    entregas_aqui = [t for t in carrying if t['Destino'] == ponto]
    is_pickup = bool(coletas_aqui)
    is_dropoff = bool(entregas_aqui)
    destinos_no_carro = {t['Destino'] for t in carrying}

    def peso_valido(tarefa):
        try:
            valor = float(tarefa.get('Peso', 1) or 1)
            return 1.0 if math.isnan(valor) else valor
        except (TypeError, ValueError):
            return 1.0

    urgencia_coleta = max([peso_valido(t) for t in coletas_aqui] + [1.0])
    urgencia_entrega = max([peso_valido(t) for t in entregas_aqui] + [1.0])

    # Se ainda há material a coletar para o mesmo destino, entregar agora
    # normalmente cria uma segunda visita e o conhecido efeito de zigue-zague.
    pendentes_mesmo_destino = [
        t for t in unpicked
        if t['Destino'] == ponto and t['Origem'] != ponto
    ]
    penalidade_retorno = 0.0
    if is_dropoff and pendentes_mesmo_destino:
        urgencia_pendente = max([peso_valido(t) for t in pendentes_mesmo_destino] + [1.0])
        entrega_urgente_isolada = (
            "Urgências" in estrategia
            and urgencia_entrega >= 4
            and urgencia_entrega > urgencia_pendente
        )

        if not entrega_urgente_isolada:
            origens_pendentes = {t['Origem'] for t in pendentes_mesmo_destino}
            ciclos_de_retorno = []
            for origem in origens_pendentes:
                ida, _ = get_dist_dur(ponto, origem)
                volta, _ = get_dist_dur(origem, ponto)
                ciclos_de_retorno.append(ida + volta)

            # O piso de 8 km impede que uma pequena vantagem local provoque
            # uma visita duplicada; o ciclo viário mede o prejuízo real.
            penalidade_retorno = max(8.0, min(ciclos_de_retorno or [8.0]) * 1.35)

    coleta_completa_carga = is_pickup and any(
        t['Destino'] in destinos_no_carro for t in coletas_aqui
    )

    if "Menor Distância" in estrategia:
        score = custo_deslocamento
        if coleta_completa_carga:
            score *= 0.85
        score += penalidade_retorno
    else:
        prioridade = 1.0
        if is_dropoff:
            prioridade *= 2.0
        if is_pickup:
            prioridade *= 3.0 if coleta_completa_carga else 1.5
        if "Urgências" in estrategia:
            prioridade *= max(urgencia_coleta, urgencia_entrega) ** 2
        elif "Descarregar" in estrategia and is_dropoff:
            prioridade *= 5.0

        score = (custo_deslocamento / max(prioridade, 0.001)) + penalidade_retorno

    # Ações no local onde o veículo já está devem ocorrer imediatamente.
    if distancia < 0.1:
        score = -1.0

    return score, distancia, duracao

def otimizar_sequencia_rota(tarefas, ponto_inicial, estrategia, get_dist_dur, horario_inicio, retornar_base=False, ponto_base=None):
    """Busca em feixe para o problema de coleta e entrega com precedência.

    Avalia sequências completas, agrupa ações no mesmo endereço e pondera
    trânsito/tempo, distância, urgência, carga no veículo, almoço e hora extra.
    """
    if not tarefas:
        return []

    def numero_seguro(valor, padrao):
        try:
            numero = float(valor)
            return padrao if math.isnan(numero) else numero
        except (TypeError, ValueError):
            return padrao

    total_tarefas = len(tarefas)
    if total_tarefas > 24:
        # Contingência para dias excepcionalmente grandes: mantém as mesmas
        # regras logísticas sem deixar o aplicativo preso em busca combinatória.
        pendentes = list(tarefas)
        no_carro = []
        atual = ponto_inicial
        ordem = []
        for _ in range(total_tarefas * 2 + 5):
            candidatos = {t['Origem'] for t in pendentes} | {t['Destino'] for t in no_carro}
            if not candidatos:
                break
            proximo = min(candidatos, key=lambda p: pontuar_parada_rota(atual, p, pendentes, no_carro, estrategia, get_dist_dur)[0])
            ordem.append(proximo)
            no_carro = [t for t in no_carro if t['Destino'] != proximo]
            coletadas = [t for t in pendentes if t['Origem'] == proximo]
            pendentes = [t for t in pendentes if t['Origem'] != proximo]
            no_carro.extend(coletadas)
            atual = proximo
        return ordem

    origens = [t['Origem'] for t in tarefas]
    destinos = [t['Destino'] for t in tarefas]
    pesos = [numero_seguro(t.get('Peso', 1), 1.0) for t in tarefas]
    tempos_coleta = [numero_seguro(t.get('Tempo_Coleta', 10), 10.0) for t in tarefas]
    tempos_entrega = [numero_seguro(t.get('Tempo_Entrega', 10), 10.0) for t in tarefas]
    mascara_total = (1 << total_tarefas) - 1

    tarefas_por_origem = {}
    tarefas_por_destino = {}
    for indice, (origem, destino) in enumerate(zip(origens, destinos)):
        tarefas_por_origem.setdefault(origem, []).append(indice)
        tarefas_por_destino.setdefault(destino, []).append(indice)

    if total_tarefas <= 8:
        largura_feixe = 700
    elif total_tarefas <= 14:
        largura_feixe = 320
    elif total_tarefas <= 19:
        largura_feixe = 180
    else:
        largura_feixe = 100

    def avancar_relogio(inicio, viagem, servico):
        partida = inicio
        if 12 * 60 <= partida < 13 * 60:
            partida = 13 * 60
        chegada = partida + viagem
        if partida < 12 * 60 < chegada:
            chegada += 60
        if 12 * 60 <= chegada < 13 * 60:
            chegada = 13 * 60
        saida = chegada + servico
        if chegada < 12 * 60 < saida:
            saida += 60
        return chegada, saida

    def pontos_disponiveis(coletadas_mask, entregues_mask):
        pontos = set()
        for i in range(total_tarefas):
            bit = 1 << i
            if not (coletadas_mask & bit):
                pontos.add(origens[i])
            elif not (entregues_mask & bit):
                pontos.add(destinos[i])
        return pontos

    def heuristica_restante(atual, coletadas_mask, entregues_mask):
        pontos = pontos_disponiveis(coletadas_mask, entregues_mask)
        if not pontos:
            return 0.0
        menor_tempo = min(get_dist_dur(atual, p)[1] for p in pontos)
        return menor_tempo * 0.35 + len(pontos) * 0.8

    estado_inicial = {
        "atual": ponto_inicial,
        "hora": float(horario_inicio),
        "coletadas": 0,
        "entregues": 0,
        "ordem": tuple(),
        "custo": 0.0,
        "distancia": 0.0,
        "viagem": 0.0,
    }
    estados = [estado_inicial]
    concluidos = []
    inicio_busca = time.perf_counter()
    max_passos = total_tarefas * 2 + 3

    for _ in range(max_passos):
        proximos_por_estado = {}
        for estado in estados:
            if estado["entregues"] == mascara_total:
                concluidos.append(estado)
                continue

            for ponto in pontos_disponiveis(estado["coletadas"], estado["entregues"]):
                distancia, duracao = get_dist_dur(estado["atual"], ponto)

                ids_entrega = [
                    i for i in tarefas_por_destino.get(ponto, [])
                    if (estado["coletadas"] & (1 << i)) and not (estado["entregues"] & (1 << i))
                ]
                ids_coleta = [
                    i for i in tarefas_por_origem.get(ponto, [])
                    if not (estado["coletadas"] & (1 << i))
                ]
                if not ids_entrega and not ids_coleta:
                    continue

                novas_coletadas = estado["coletadas"]
                novas_entregues = estado["entregues"]
                for i in ids_coleta:
                    novas_coletadas |= 1 << i
                for i in ids_entrega:
                    novas_entregues |= 1 << i
                # Origem e destino idênticos são resolvidos na mesma parada.
                for i in ids_coleta:
                    if destinos[i] == ponto:
                        novas_entregues |= 1 << i
                        ids_entrega.append(i)

                tempo_servico = sum(tempos_coleta[i] for i in ids_coleta) + sum(tempos_entrega[i] for i in ids_entrega)
                _, nova_hora = avancar_relogio(estado["hora"], duracao, tempo_servico)

                if "Menor Distância" in estrategia:
                    incremento = distancia * 3.2 + duracao * 0.35
                else:
                    incremento = duracao + distancia * 0.18

                visitas_anteriores = estado["ordem"].count(ponto)
                if visitas_anteriores:
                    incremento += 75.0 * visitas_anteriores

                # Evita entregar em um destino se ainda falta coletar outro
                # material que também será entregue nele.
                ainda_falta_para_o_ponto = [
                    i for i in tarefas_por_destino.get(ponto, [])
                    if not (novas_coletadas & (1 << i))
                ]
                if ids_entrega and ainda_falta_para_o_ponto:
                    urgente_agora = max([pesos[i] for i in ids_entrega] + [1])
                    urgente_depois = max([pesos[i] for i in ainda_falta_para_o_ponto] + [1])
                    excecao_urgente = "Urgências" in estrategia and urgente_agora >= 4 and urgente_agora > urgente_depois
                    if not excecao_urgente:
                        incremento += 95.0

                tempo_decorrido = max(0.0, nova_hora - horario_inicio)
                if "Menor Distância" not in estrategia:
                    for i in ids_entrega:
                        if "Urgências" in estrategia:
                            fator_urgencia = max(0.0, pesos[i] - 2.0) * 0.75
                        else:
                            fator_urgencia = {5: 0.65, 4: 0.32, 3: 0.10}.get(int(pesos[i]), 0.0)
                        incremento += tempo_decorrido * fator_urgencia

                carga_apos = (novas_coletadas & ~novas_entregues).bit_count()
                if "Descarregar" in estrategia:
                    incremento += carga_apos * (duracao + tempo_servico) * 0.55
                elif "Equilibrada" in estrategia:
                    incremento += carga_apos * (duracao + tempo_servico) * 0.05

                extra_antes = max(0.0, estado["hora"] - 17 * 60)
                extra_depois = max(0.0, nova_hora - 17 * 60)
                incremento += (extra_depois - extra_antes) * 18.0

                novo_estado = {
                    "atual": ponto,
                    "hora": nova_hora,
                    "coletadas": novas_coletadas,
                    "entregues": novas_entregues,
                    "ordem": estado["ordem"] + (ponto,),
                    "custo": estado["custo"] + incremento,
                    "distancia": estado["distancia"] + distancia,
                    "viagem": estado["viagem"] + duracao,
                }
                chave_estado = (ponto, novas_coletadas, novas_entregues)
                anterior = proximos_por_estado.get(chave_estado)
                if anterior is None or (novo_estado["custo"], novo_estado["hora"]) < (anterior["custo"], anterior["hora"]):
                    proximos_por_estado[chave_estado] = novo_estado

        if concluidos:
            break
        if not proximos_por_estado:
            break

        candidatos_ordenados = sorted(
            proximos_por_estado.values(),
            key=lambda e: e["custo"] + heuristica_restante(e["atual"], e["coletadas"], e["entregues"]),
        )
        estados = candidatos_ordenados[:largura_feixe]
        if time.perf_counter() - inicio_busca > 5.0:
            break

    if not concluidos:
        concluidos = [e for e in estados if e["entregues"] == mascara_total]
    if concluidos:
        def custo_final(estado):
            custo = estado["custo"]
            if retornar_base and ponto_base and estado["atual"] != ponto_base:
                distancia, duracao = get_dist_dur(estado["atual"], ponto_base)
                custo += duracao + distancia * 0.18
            return custo
        melhor = min(concluidos, key=custo_final)
        return list(melhor["ordem"])

    # Se a busca atingir o limite de tempo, conclui de forma determinística
    # com o motor guloso seguro, sem travar a geração da rota.
    pendentes = list(tarefas)
    no_carro = []
    atual = ponto_inicial
    ordem = []
    for _ in range(total_tarefas * 2 + 5):
        candidatos = {t['Origem'] for t in pendentes} | {t['Destino'] for t in no_carro}
        if not candidatos:
            break
        proximo = min(candidatos, key=lambda p: pontuar_parada_rota(atual, p, pendentes, no_carro, estrategia, get_dist_dur)[0])
        ordem.append(proximo)
        no_carro = [t for t in no_carro if t['Destino'] != proximo]
        coletadas = [t for t in pendentes if t['Origem'] == proximo]
        pendentes = [t for t in pendentes if t['Origem'] != proximo]
        no_carro.extend(coletadas)
        atual = proximo
    return ordem

def _decodificar_polyline_google(polyline):
    pontos = []
    indice = latitude = longitude = 0
    while indice < len(polyline):
        valores = []
        for _ in range(2):
            resultado = deslocamento = 0
            while indice < len(polyline):
                byte = ord(polyline[indice]) - 63
                indice += 1
                resultado |= (byte & 0x1F) << deslocamento
                deslocamento += 5
                if byte < 0x20:
                    break
            valores.append(~(resultado >> 1) if resultado & 1 else resultado >> 1)
        latitude += valores[0]
        longitude += valores[1]
        pontos.append([latitude / 1e5, longitude / 1e5])
    return pontos

def buscar_geometria_google_trafego(coords_limpas, horario_partida=None):
    chave = carregar_chave_google_routes()
    if not chave or len(coords_limpas) < 2 or len(coords_limpas) > 27:
        return None

    def waypoint(coord, parada=False):
        dado = {"location": {"latLng": {"latitude": float(coord[0]), "longitude": float(coord[1])}}}
        if parada:
            dado["vehicleStopover"] = True
        return dado

    agora_seguro = datetime.now(FUSO_LOCAL) + timedelta(minutes=1)
    partida = horario_partida if horario_partida and horario_partida > agora_seguro else agora_seguro
    payload = {
        "origin": waypoint(coords_limpas[0]),
        "destination": waypoint(coords_limpas[-1]),
        "intermediates": [waypoint(c, parada=True) for c in coords_limpas[1:-1]],
        "travelMode": "DRIVE",
        "routingPreference": "TRAFFIC_AWARE_OPTIMAL",
        "trafficModel": "BEST_GUESS",
        "departureTime": partida.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "polylineQuality": "HIGH_QUALITY",
        "polylineEncoding": "ENCODED_POLYLINE",
        "routeModifiers": {"avoidFerries": True},
        "languageCode": "pt-BR",
        "regionCode": "br",
        "units": "METRIC",
    }
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": chave,
        "X-Goog-FieldMask": "routes.polyline.encodedPolyline",
    }
    try:
        resposta = requests.post("https://routes.googleapis.com/directions/v2:computeRoutes", headers=headers, json=payload, timeout=35)
        resposta.raise_for_status()
        rotas = resposta.json().get("routes", [])
        encoded = rotas[0].get("polyline", {}).get("encodedPolyline", "") if rotas else ""
        pontos = _decodificar_polyline_google(encoded) if encoded else []
        return pontos if len(pontos) > 1 else None
    except Exception:
        return None

def buscar_geometria_tomtom_trafego(coords_limpas, horario_partida=None):
    """Desenha o percurso viário na ordem já otimizada, considerando trânsito TomTom."""
    chave = carregar_chave_tomtom()
    if not chave or len(coords_limpas) < 2 or len(coords_limpas) > 152:
        return None

    agora_seguro = datetime.now(FUSO_LOCAL) + timedelta(minutes=1)
    partida = horario_partida if horario_partida and horario_partida > agora_seguro else agora_seguro
    locais = ":".join(f"{float(lat)},{float(lon)}" for lat, lon in coords_limpas)
    url = f"https://api.tomtom.com/routing/1/calculateRoute/{locais}/json"
    parametros = {
        "key": chave,
        "routeType": "fastest",
        "traffic": "true",
        "travelMode": "car",
        "departAt": partida.isoformat(timespec="seconds"),
        "routeRepresentation": "polyline",
        "computeTravelTimeFor": "all",
        "language": "pt-BR",
    }
    try:
        resposta = requests.get(url, params=parametros, timeout=35)
        resposta.raise_for_status()
        rotas = resposta.json().get("routes", [])
        if not rotas:
            return None
        pontos = []
        for perna in rotas[0].get("legs", []):
            for ponto in perna.get("points", []):
                coordenada = [float(ponto["latitude"]), float(ponto["longitude"])]
                if not pontos or coordenada != pontos[-1]:
                    pontos.append(coordenada)
        return pontos if len(pontos) > 1 else None
    except Exception:
        return None

def buscar_geometria_rota(coords_ordenadas, horario_partida=None):
    coords_limpas = []
    for coord in coords_ordenadas:
        if not coords_limpas or coord != coords_limpas[-1]: coords_limpas.append(coord)
    if len(coords_limpas) < 2: return [[lat, lon] for lat, lon in coords_limpas], False

    geometria_tomtom = buscar_geometria_tomtom_trafego(coords_limpas, horario_partida)
    if geometria_tomtom:
        return geometria_tomtom, True

    geometria_google = buscar_geometria_google_trafego(coords_limpas, horario_partida)
    if geometria_google:
        return geometria_google, True

    try:
        coords_str = ";".join(f"{lon},{lat}" for lat, lon in coords_limpas)
        url = f"https://router.project-osrm.org/route/v1/driving/{coords_str}?overview=full&geometries=geojson&steps=false"
        req = urllib.request.Request(url, headers={'User-Agent': 'AproarLogisticsWeb/1.0'})
        with urllib.request.urlopen(req, timeout=15) as response:
            res = json.loads(response.read())
        if res.get("code") == "Ok" and res.get("routes"): return [[lat, lon] for lat, lon in res["routes"][0]["geometry"]["coordinates"]], True
    except: pass
    return [[lat, lon] for lat, lon in coords_limpas], False

def extrair_dados_completos(texto, card_name):
    num_match = re.search(r'\b(\d{4}(?:\.\d+)?|APR[A-Z0-9]+)\b', card_name, re.IGNORECASE)
    num = num_match.group(1).upper() if num_match else ""
    
    unidade = ""
    for u in UNIDADES_PROPRIAS:
        if normalizar_local(u) in normalizar_local(card_name):
            unidade = normalizar_local(u)
            break
            
    short_name = f"{num} - {unidade}" if (num and unidade) else num if num else unidade if unidade else card_name[:25] + "..."

    origem, destino = "", ""
    materiais = "Ver Trello"
    
    if texto:
        texto_limpo = re.sub(r'[*_`]+', '', texto).strip()
        
        if "TRANSBORDO" in texto_limpo.upper() or "TRANSBORDOS" in texto_limpo.upper():
            if unidade:
                origem = unidade
                destino = "ESCRITÓRIO"
            materiais = texto_limpo
        else:
            mo = re.search(r'(?i)(?:coletar|pegar|retirar|buscar|coleta)\s+(?:no|na|em|o|a|ao|à|aos|às)?\s*([^\:\n\.\-]+)', texto_limpo)
            if mo: origem = normalizar_local(mo.group(1))

            md = re.search(r'(?i)(?:levar|entreg(?:ar|a)|devolver|encaminhar|transportar|deixar|entrega)\s+(?:para|no|na|em|o|a|ao|à|aos|às)?\s*([^\:\n\.]+)', texto_limpo)
            if md: destino = normalizar_local(md.group(1))
            
            if mo and md:
                start_idx = mo.end()
                end_idx = md.start()
                if start_idx < end_idx:
                    mat_text = texto_limpo[start_idx:end_idx].strip()
                    linhas_limpas = [l.strip().lstrip('-').strip() for l in mat_text.split('\n') if len(l.strip()) >= 2 and l.lower() not in ['e', 'e:', 'e -', 'e,', 'para', 'levar para']]
                    if linhas_limpas: materiais = " | ".join(linhas_limpas)

    if not destino and unidade: destino = unidade
    if not origem and destino: origem = "ESCRITÓRIO"

    if "SEBRAE" in destino or "SEBRAE" in short_name:
        if destino and destino not in ["ESCRITÓRIO"]:
            destino = "ESCRITÓRIO"
            materiais += " ⚠️[DEIXAR NO ESCRITÓRIO P/ SOARES]"

    return short_name, origem, destino, materiais

def encontrar_endereco_na_descricao(descricao):
    if not descricao: return None
    mo_link = re.search(r'(https?://(?:www\.)?google\.[a-z\.]+/maps[^\s\n]+|https?://goo\.gl/maps/[^\s\n]+|https?://maps\.app\.goo\.gl/[^\s\n]+)', descricao)
    if mo_link: return mo_link.group(1)
    mo_end = re.search(r'(?i)(?:endere[çc]o|local)\s*(?:\:|-)\s*([^\n]+)', descricao)
    if mo_end: return mo_end.group(1).strip()
    return None

def classificar_prioridade(due_str):
    if not due_str: return 1, "Sem Prazo"
    try:
        due_date = converter_data_trello(due_str).date()
        diff = (due_date - DATA_REF_ROTA_DATE).days
        if diff < 0: return 5, "VENCIDA"
        elif diff == 0: return 4, "HOJE"
        elif diff <= 2: return 3, f"Em {diff} dias"
        else: return 2, "Futuro"
    except: return 1, "Sem Prazo"

def converter_data_trello(valor):
    if not valor: return None
    data = datetime.fromisoformat(valor.replace("Z", "+00:00"))
    if data.tzinfo is None: data = data.replace(tzinfo=timezone.utc)
    return data.astimezone(FUSO_LOCAL)

def lista_esta_concluida(nome_lista):
    nome = normalizar_local(nome_lista or "")
    return "CONCLU" in nome or "ENTREG" in nome

def encontrar_conclusao_de_hoje(card_id, acoes):
    hoje = AGORA_REAL.date()
    conclusoes = []
    for acao in acoes:
        if acao.get("type") != "updateCard": continue
        dados = acao.get("data", {})
        if dados.get("card", {}).get("id") != card_id: continue
        if not lista_esta_concluida(dados.get("listAfter", {}).get("name", "")): continue
        if lista_esta_concluida(dados.get("listBefore", {}).get("name", "")): continue
        try:
            momento = converter_data_trello(acao.get("date"))
            if momento and momento.date() == hoje: conclusoes.append(momento)
        except: continue
    return max(conclusoes) if conclusoes else None

def sincronizar_demandas(manual=False):
    data = obter_dados_trello()
    if not data:
        if manual: st.error("⚠️ Erro ao acessar o Trello.")
        return False
        
    trello_lists = {l['id']: l['name'] for l in data.get('lists', []) if not l.get('closed')}
    demandas_extraidas = []
    
    for c in data.get('cards', []):
        if c.get('closed') or lista_esta_concluida(trello_lists.get(c.get('idList', ''), '').upper()): continue
        short_name, origem, destino, materiais = extrair_dados_completos(c.get('desc', ''), c.get('name', ''))
        peso, status_prazo = classificar_prioridade(c.get('due'))
        endereco_card = encontrar_endereco_na_descricao(c.get('desc', ''))
        if endereco_card:
            lat, lon = buscar_coordenadas(endereco_card)
            if lat:
                if origem and origem not in UNIDADES_PROPRIAS and not fetch_one("SELECT lat FROM locais WHERE apelido = :apelido", {"apelido": origem}): 
                    execute_db("INSERT INTO locais (apelido, endereco, lat, lon) VALUES (:apelido, :end, :lat, :lon) ON CONFLICT (apelido) DO UPDATE SET endereco=EXCLUDED.endereco, lat=EXCLUDED.lat, lon=EXCLUDED.lon", {"apelido": origem, "end": endereco_card, "lat": lat, "lon": lon})
                if destino and destino not in UNIDADES_PROPRIAS and not fetch_one("SELECT lat FROM locais WHERE apelido = :apelido", {"apelido": destino}): 
                    execute_db("INSERT INTO locais (apelido, endereco, lat, lon) VALUES (:apelido, :end, :lat, :lon) ON CONFLICT (apelido) DO UPDATE SET endereco=EXCLUDED.endereco, lat=EXCLUDED.lat, lon=EXCLUDED.lon", {"apelido": destino, "end": endereco_card, "lat": lat, "lon": lon})
        
        tc_val = 20 if origem not in UNIDADES_PROPRIAS else 10
        te_val = 10
        if not st.session_state.demandas.empty and c['id'] in st.session_state.demandas['id'].values:
            linha_antiga = st.session_state.demandas[st.session_state.demandas['id'] == c['id']].iloc[0]
            tc_val, te_val = linha_antiga['Tempo_Coleta'], linha_antiga['Tempo_Entrega']
        
        demandas_extraidas.append({"id": c['id'], "Obra": short_name, "Origem": origem, "Destino": destino, "Materiais": materiais, "Urgência": status_prazo, "Peso": peso, "Tempo_Coleta": tc_val, "Tempo_Entrega": te_val, "Supervisor": SUPERVISORES_MAP.get(destino, "Sede / Logística")})

    st.session_state.demandas = pd.DataFrame(demandas_extraidas, columns=COLUNAS_DEMANDAS)
    st.session_state.ultima_sincronizacao = time.time()
    return True

class FormularioLoginParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.action = None
        self.inputs = []
    def handle_starttag(self, tag, attrs):
        atributos = {k: (v or "") for k, v in attrs}
        if tag.lower() == "form" and self.action is None: self.action = atributos.get("action", "")
        elif tag.lower() == "input": self.inputs.append(atributos)

def _escolher_campo(campos, palavras):
    if not campos: return None
    for campo in campos:
        identificador = f"{campo.get('name', '')} {campo.get('id', '')}".lower()
        if any(palavra in identificador for palavra in palavras): return campo
    return campos[0]

def _montar_formulario_login(html, usuario, senha):
    parser = FormularioLoginParser()
    parser.feed(html)
    campos_com_nome = [c for c in parser.inputs if c.get("name")]
    campo_usuario = _escolher_campo([c for c in campos_com_nome if c.get("type", "text").lower() in ("text", "email")], ("usu", "user", "login", "email"))
    campo_senha = _escolher_campo([c for c in campos_com_nome if c.get("type", "").lower() == "password"], ("senha", "password", "pass"))
    if not campo_usuario or not campo_senha: raise RuntimeError("Não foi possível identificar os campos de acesso do portal.")
    dados = {c["name"]: c.get("value", "") for c in campos_com_nome if c.get("type", "").lower() == "hidden"}
    dados[campo_usuario["name"]] = usuario
    dados[campo_senha["name"]] = senha
    botao = _escolher_campo([c for c in campos_com_nome if c.get("type", "").lower() in ("submit", "button")], ("entr", "acess", "login", "logar"))
    if botao: dados[botao["name"]] = botao.get("value", "Entrar")
    imagens = [c for c in campos_com_nome if c.get("type", "").lower() == "image"]
    if imagens: dados[f"{imagens[0]['name']}.x"] = "10"; dados[f"{imagens[0]['name']}.y"] = "10"
    return parser.action, dados

def _parsear_resposta_rastreador(texto):
    posicoes = []
    for registro in texto.replace("\r", "").split(";"):
        registro = registro.strip()
        if not registro: continue
        partes = registro.split("|", 8)
        if len(partes) < 9: continue
        try:
            latitude, longitude, velocidade = float(partes[3]), float(partes[4]), float(partes[5].replace(",", "."))
        except: continue
        codigo_status = partes[6].strip().upper()
        
        placa = partes[1].strip().upper()
        if placa.startswith("TIF"): placa = "TIF-2123"
        elif placa.startswith("OSC"): placa = "OSC-3842"
        
        posicoes.append({"ID": partes[0].strip(), "Placa": placa, "Última atualização": partes[2].strip(), "Latitude": latitude, "Longitude": longitude, "Velocidade (km/h)": velocidade, "Situação": {"P": "Parado", "M": "Em movimento", "L": "Ligado", "D": "Desligado"}.get(codigo_status, codigo_status or "Não informado"), "Código": codigo_status, "Ícone": partes[7].strip(), "Endereço": partes[8].strip()})
    return posicoes

def consultar_posicoes_protege(sessao, pagina_atual, veiculos):
    url = urllib.parse.urljoin(pagina_atual, "consultaajax_all.aspx")
    resposta = sessao.post(url, params={"p1": veiculos}, headers={"X-Requested-With": "XMLHttpRequest", "Referer": pagina_atual}, timeout=20)
    resposta.raise_for_status()
    posicoes = _parsear_resposta_rastreador(resposta.text)
    if not posicoes: raise RuntimeError("O portal não devolveu posições. A sessão pode ter expirado.")
    return posicoes

def autenticar_protege(usuario, senha, veiculos):
    ultimo_erro = None
    for login_url in RASTREADOR_LOGIN_URLS:
        try:
            sessao = requests.Session()
            sessao.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151.0 Safari/537.36"})
            pagina_login = sessao.get(login_url, timeout=20)
            pagina_login.raise_for_status()
            action, dados = _montar_formulario_login(pagina_login.text, usuario, senha)
            url_post = urllib.parse.urljoin(pagina_login.url, action or pagina_login.url)
            resposta_login = sessao.post(url_post, data=dados, timeout=20, allow_redirects=True)
            resposta_login.raise_for_status()
            pagina_atual = resposta_login.url
            return sessao, pagina_atual, consultar_posicoes_protege(sessao, pagina_atual, veiculos)
        except Exception as erro: ultimo_erro = erro
    raise RuntimeError("Não foi possível autenticar ou consultar o rastreador.") from ultimo_erro

def carregar_config_protege():
    try:
        config = st.secrets["protege"]
        usuario, senha, veiculos = str(config.get("usuario", "")).strip(), str(config.get("senha", "")).strip(), config.get("veiculos", RASTREADOR_VEICULOS_PADRAO)
        return usuario, senha, ",".join(str(v).strip() for v in veiculos) if isinstance(veiculos, (list, tuple)) else str(veiculos).strip()
    except: return "", "", RASTREADOR_VEICULOS_PADRAO

def loop_automacoes_background():
    agora_loop = datetime.now(FUSO_LOCAL)
    try:
        data = obter_dados_trello()
        if data:
            trello_lists = {l['id']: l['name'] for l in data.get('lists', []) if not l.get('closed')}
            cards = data.get('cards', [])
            acoes = data.get('actions', [])
            
            ids_ja_notificados = {str(r[0]) for r in fetch_all("SELECT id FROM historico_concluidos WHERE data_conclusao = :data", {"data": DATA_HOJE_REAL_STR})}
            
            novas_entregas = 0
            for c in cards:
                if c.get('closed'): continue
                if lista_esta_concluida(trello_lists.get(c.get('idList', ''), '').upper()):
                    momento_conclusao = encontrar_conclusao_de_hoje(c['id'], acoes)
                    if momento_conclusao and str(c['id']) not in ids_ja_notificados and momento_conclusao.strftime("%d/%m/%Y") == DATA_HOJE_REAL_STR:
                        short_name, origem, destino, materiais = extrair_dados_completos(c.get('desc', ''), c.get('name', ''))
                        url_webhook, _ = obter_webhook_teams(destino, supervisor=SUPERVISORES_MAP.get(destino, "Sede / Logística"), obra=short_name)
                        hora_str = momento_conclusao.strftime("%H:%M")

                        if (agora_loop - momento_conclusao).total_seconds() / 60 <= 5 and url_webhook:
                            disparar_teams(url_webhook, f"✅ Entrega concluída — {destino}", f"✅ **Os materiais foram entregues na obra e a demanda tomou baixa no Trello.**\n\n**Obra:** {short_name}\n\n**Local:** {destino}\n\n**Materiais:** {materiais}\n\n**Data e Hora:** {momento_conclusao.strftime('%d/%m/%Y às %H:%M')}")

                        execute_db("INSERT INTO historico_concluidos (id, obra, origem, destino, materiais, data_conclusao, hora_conclusao) VALUES (:id, :obra, :origem, :destino, :mat, :data, :hora) ON CONFLICT (id) DO UPDATE SET hora_conclusao=EXCLUDED.hora_conclusao", {"id": c['id'], "obra": short_name, "origem": origem, "destino": destino, "mat": materiais, "data": DATA_HOJE_REAL_STR, "hora": hora_str})
                        novas_entregas += 1
            if novas_entregas > 0: st.toast(f"🔔 {novas_entregas} nova(s) baixa(s) no Trello registrada(s)!", icon="✅")
    except: pass

    try:
        sessao, pagina = st.session_state.get("protege_sessao"), st.session_state.get("protege_pagina")
        usuario_protege, senha_protege, ids_veiculos = carregar_config_protege()
        if sessao and pagina and ids_veiculos:
            posicoes = consultar_posicoes_protege(sessao, pagina, ids_veiculos)
            
            # 1. Inteligência de Início de Rota (>500m do escritório)
            lat_base, lon_base = LOCAL_BASE_COORDS
            for p in posicoes:
                if p["Velocidade (km/h)"] > 0:
                    dist_base_km = calcular_distancia_km(lat_base, lon_base, p["Latitude"], p["Longitude"])
                    if dist_base_km > 0.5:
                        if not fetch_one("SELECT hora_inicio FROM inicio_movimento WHERE placa=:placa AND data=:data", {"placa": p["Placa"], "data": DATA_HOJE_REAL_STR}):
                            match_time = re.search(r'(\d{2}:\d{2})', p['Última atualização'])
                            execute_db("INSERT INTO inicio_movimento (placa, data, hora_inicio) VALUES (:placa, :data, :hora) ON CONFLICT (placa, data) DO NOTHING", {"placa": p["Placa"], "data": DATA_HOJE_REAL_STR, "hora": match_time.group(1) if match_time else agora_loop.strftime("%H:%M")})
            
            # 2. Inteligência de GEOFENCE (Medidor de tempo nas paradas ativas da Rota)
            try:
                res_rota = fetch_one("SELECT json_locais FROM rota_ativa WHERE id=1 AND data_rota=:data", {"data": DATA_HOJE_REAL_STR})
                if res_rota and posicoes:
                    locais_rota = json.loads(res_rota[0])
                    for p in posicoes:
                        lat_v, lon_v = p['Latitude'], p['Longitude']
                        placa_v = p['Placa']
                        vel_v = p['Velocidade (km/h)']
                        
                        local_proximo = None
                        menor_dist = 999
                        for nome_loc, coords in locais_rota.items():
                            if nome_loc == "ESCRITÓRIO": continue
                            dist_km = calcular_distancia_km(coords[0], coords[1], lat_v, lon_v)
                            if dist_km <= 0.25 and dist_km < menor_dist: 
                                local_proximo = nome_loc
                                menor_dist = dist_km
                        
                        agora_hm = agora_loop.strftime("%H:%M")
                        parada_ativa = fetch_one("SELECT id, local, hora_chegada FROM rastreio_paradas WHERE data=:data AND placa=:placa AND hora_saida IS NULL ORDER BY id DESC LIMIT 1", {"data": DATA_HOJE_REAL_STR, "placa": placa_v})
                        
                        if local_proximo and vel_v < 5:
                            if parada_ativa:
                                if parada_ativa[1] != local_proximo:
                                    execute_db("UPDATE rastreio_paradas SET hora_saida=:hora WHERE id=:id", {"hora": agora_hm, "id": parada_ativa[0]})
                                    execute_db("INSERT INTO rastreio_paradas (data, placa, local, hora_chegada) VALUES (:data, :placa, :local, :hora)", {"data": DATA_HOJE_REAL_STR, "placa": placa_v, "local": local_proximo, "hora": agora_hm})
                            else:
                                execute_db("INSERT INTO rastreio_paradas (data, placa, local, hora_chegada) VALUES (:data, :placa, :local, :hora)", {"data": DATA_HOJE_REAL_STR, "placa": placa_v, "local": local_proximo, "hora": agora_hm})
                        else:
                            if parada_ativa and (not local_proximo or vel_v >= 5):
                                execute_db("UPDATE rastreio_paradas SET hora_saida=:hora WHERE id=:id", {"hora": agora_hm, "id": parada_ativa[0]})
            except Exception as e:
                pass
    except: pass

# =====================================================================
# INTERFACE STREAMLIT
# =====================================================================
try:
    with open("logo.png", "rb") as image_file: encoded_string = base64.b64encode(image_file.read()).decode()
    st.markdown(f'<div style="display: flex; align-items: center; gap: 30px; margin-bottom: 25px; margin-top: -20px;"><img src="data:image/png;base64,{encoded_string}" width="260" style="flex-shrink: 0;"><h1 style="margin: 0; padding: 0; line-height: 1.2; color: #e4e8f4;">TORRE DE CONTROLE LOGÍSTICO</h1></div>', unsafe_allow_html=True)
except: st.title("🚚 TORRE DE CONTROLE LOGÍSTICO")

if "demandas" not in st.session_state: st.session_state.demandas = pd.DataFrame(columns=COLUNAS_DEMANDAS)

with st.sidebar:
    st.header("⚙️ Painel de Operações")
    st.caption(f"📅 Planejamento ativo para: **{DATA_REF_ROTA_STR}**")
    
    # Atualiza as demandas silenciosamente a cada 10 min
    if "ultima_sincronizacao" not in st.session_state:
        st.session_state.ultima_sincronizacao = 0
        sincronizar_demandas()
    
    if hasattr(st, "fragment"):
        @st.fragment(run_every="60s")
        def _loop_operacoes():
            loop_automacoes_background()
            if time.time() - st.session_state.get("ultima_sincronizacao", 0) > 600:
                demandas_antes = st.session_state.demandas.copy(deep=True)
                if sincronizar_demandas():
                    # O Trello continua sendo consultado a cada 10 minutos, mas
                    # a tela inteira só recarrega quando os dados realmente mudam.
                    if not demandas_antes.equals(st.session_state.demandas):
                        st.rerun()
        _loop_operacoes()

    st.markdown("---")
    st.markdown("📱 **App do Motorista**")
    st.components.v1.html("""<script>function copyLink() { try { var tempInput = document.createElement("input"); tempInput.value = window.parent.location.origin + window.parent.location.pathname + "?davi=true"; document.body.appendChild(tempInput); tempInput.select(); document.execCommand("copy"); document.body.removeChild(tempInput); var btn = document.getElementById("btn"); btn.innerText = "✅ Copiado!"; btn.style.background = "linear-gradient(135deg, #16a34a, #15803d)"; btn.style.color = "white"; btn.style.border = "none"; setTimeout(() => { btn.innerText = "🔗 Copiar Link do Davi"; btn.style.background = "transparent"; btn.style.color = "#8da0b8"; btn.style.border = "1px solid rgba(64,116,146,.35)"; }, 2500); } catch (err) { alert("Erro ao copiar."); } }</script><button id="btn" onclick="copyLink()" style="width:100%; padding:10px; background-color:transparent; color:#8da0b8; border:1px solid rgba(64,116,146,.35); border-radius:8px; font-family:sans-serif; font-size:14px; font-weight:bold; cursor:pointer; transition: all 0.2s;">🔗 Copiar Link do Davi</button>""", height=50)
    st.markdown("---")

    if st.button("🔄 Sincronizar Manualmente (Trello)", use_container_width=True, type="primary"):
        with st.spinner("Puxando demandas ao vivo..."):
            obter_dados_trello.clear() # Limpa o cache para forçar a versão mais nova
            if sincronizar_demandas(manual=True):
                st.success("✅ Trello Sincronizado e Demandas Importadas!")
    
    @fragmento_independente
    def controles_planejamento_rota():
        st.divider()
        st.radio("🚗 Tipo de Custeio da Rota", ["Frota da Empresa (Calcula Gasolina)", "Carro Próprio/Frete (R$ 1,50/km)"], key="cfg_veiculo_rota")
        st.divider()
        st.selectbox("🏁 Ponto de Saída", ["ESCRITÓRIO", "CASA DA INDÚSTRIA", "SENAI CENTRO", "MARACANAÚ"], key="cfg_ponto_saida")
        estrategia_atual = st.selectbox("🎯 Estratégia da Rota", ["⚖️ Equilibrada", "🏢 Foco em Descarregar", "⛽ Menor Distância", "🚨 Priorizar Urgências"], key="cfg_estrategia_rota")
        st.caption(f"ℹ️ *{ {'⚖️ Equilibrada': 'Mescla urgência com proximidade para fazer a rota mais lógica e eficiente.', '🏢 Foco em Descarregar': 'Prioriza entregar os materiais o quanto antes para esvaziar a caçamba.', '⛽ Menor Distância': 'Foca 100% no menor KM percorrido (Economia de combustível).', '🚨 Priorizar Urgências': 'Foca 100% nas demandas Vencidas ou programadas para Hoje.'}[estrategia_atual] }*")
        st.checkbox("Retornar à base no fim do dia", value=True, key="cfg_retornar_base")

    controles_planejamento_rota()

veiculo_selecionado = st.session_state.get("cfg_veiculo_rota", "Frota da Empresa (Calcula Gasolina)")
ponto_saida = st.session_state.get("cfg_ponto_saida", "ESCRITÓRIO")
estrategia = st.session_state.get("cfg_estrategia_rota", "⚖️ Equilibrada")
retornar_base = st.session_state.get("cfg_retornar_base", True)

if st.session_state.demandas.empty: st.info("👋 Bem-vindo(a) à Torre de Controle! Clique no botão **'🔄 Sincronizar Manualmente'** no menu lateral para puxar as demandas ao vivo e começar.")

tab_roteiro, tab_rastreador, tab_demandas, tab_historico, tab_enderecos, tab_custos, tab_registros = st.tabs(["🗺️ Roteiro do Davi", "📡 Rastreador ao Vivo", "📦 Demandas Ativas", "📋 Histórico & Concluídos", "📍 Endereços", "💰 Dashboard & Custos", "🗂️ Registros da Frota"])

with tab_rastreador:
    st.subheader("📡 Rastreador ao Vivo — Protege Express")
    st.caption("Posições consultadas diretamente no portal. Atualização automática a cada 30 segundos.")

    usuario_protege, senha_protege, ids_veiculos = carregar_config_protege()

    if not usuario_protege or not senha_protege:
        st.warning("Configure o usuário e a senha da Protege Express nos Secrets do aplicativo para ativar o login automático.")
    else:
        def exibir_painel_rastreador():
            col_status, col_atualizar = st.columns([4, 1])
            col_status.success("🔒 Login automático configurado")
            if col_atualizar.button("🔄 Reconectar", key="btn_reconectar_protege", use_container_width=True): st.session_state.pop("protege_sessao", None); st.session_state.pop("protege_pagina", None)

            try:
                sessao, pagina = st.session_state.get("protege_sessao"), st.session_state.get("protege_pagina")
                if not sessao or not pagina:
                    sessao, pagina, posicoes = autenticar_protege(usuario_protege, senha_protege, ids_veiculos)
                    st.session_state["protege_sessao"], st.session_state["protege_pagina"] = sessao, pagina
                else:
                    try: posicoes = consultar_posicoes_protege(sessao, pagina, ids_veiculos)
                    except:
                        sessao, pagina, posicoes = autenticar_protege(usuario_protege, senha_protege, ids_veiculos)
                        st.session_state["protege_sessao"], st.session_state["protege_pagina"] = sessao, pagina

                start_times = {row[0]: row[1] for row in fetch_all("SELECT placa, hora_inicio FROM inicio_movimento WHERE data=:data", {"data": DATA_HOJE_REAL_STR})}

                for p in posicoes: p['🟢 Início da Rota (Hoje)'] = start_times.get(p['Placa'], "Ainda não saiu (Raio 500m)")

                velocidades = [p["Velocidade (km/h)"] for p in posicoes]
                met1, met2, met3 = st.columns(3)
                met1.metric("Veículos localizados", len(posicoes))
                met2.metric("Em movimento", sum(1 for v in velocidades if v > 0))
                met3.metric("Última leitura", datetime.now(FUSO_LOCAL).strftime("%H:%M:%S"))

                # MAPA CLARO (OPENSTREETMAP) NO RASTREADOR
                mapa = folium.Map(location=[sum(p["Latitude"] for p in posicoes) / len(posicoes), sum(p["Longitude"] for p in posicoes) / len(posicoes)], zoom_start=11, tiles="OpenStreetMap")
                limites = []
                for p in posicoes:
                    cor, icone = ("green", "play") if p["Velocidade (km/h)"] > 0 else ("red", "stop")
                    limites.append([p["Latitude"], p["Longitude"]])
                    folium.Marker([p["Latitude"], p["Longitude"]], popup=folium.Popup(f"<b>{p['Placa']}</b><br>{p['Situação']} — {p['Velocidade (km/h)']:.0f} km/h<br>Atualização: {p['Última atualização']}<br>{p['Endereço']}", max_width=360), tooltip=f"{p['Placa']} — {p['Situação']}", icon=folium.Icon(color=cor, icon=icone, prefix="fa")).add_to(mapa)

                if len(limites) > 1: mapa.fit_bounds(limites, padding=(35, 35))
                st_folium(mapa, height=520, use_container_width=True, returned_objects=[], key="mapa_rastreador_protege")
                df_posicoes_exportacao = pd.DataFrame(posicoes)[["Placa", "🟢 Início da Rota (Hoje)", "Última atualização", "Velocidade (km/h)", "Situação", "Endereço"]]
                st.dataframe(df_posicoes_exportacao, use_container_width=True, hide_index=True)
                _conteudo_exportador(
                    "Rastreador ao Vivo — Protege Express", df_posicoes_exportacao,
                    "rastreador_ao_vivo", "rastreador",
                )

            except:
                st.session_state.pop("protege_sessao", None); st.session_state.pop("protege_pagina", None)
                st.error("Não consegui entrar automaticamente no rastreador. Confira as credenciais.")

        if hasattr(st, "fragment"): st.fragment(run_every="30s")(exibir_painel_rastreador)()
        else: exibir_painel_rastreador()

with tab_demandas:
    st.subheader(f"Gerenciamento de Cargas da Rota ({DATA_REF_ROTA_STR})")

    @fragmento_independente
    def editor_tempos_demandas():
        st.session_state.demandas = st.data_editor(st.session_state.demandas, column_config={"Tempo_Coleta": st.column_config.NumberColumn("Tempo Coleta (min)", min_value=1, max_value=120), "Tempo_Entrega": st.column_config.NumberColumn("Tempo Entrega (min)", min_value=1, max_value=120), "Peso": None, "id": None, "Supervisor": None}, disabled=["Obra", "Origem", "Destino", "Materiais", "Urgência"], hide_index=True, use_container_width=True, key="editor_tempos_demandas")

    editor_tempos_demandas()
    st.divider()
    st.subheader("📣 Monitoramento da Rota Atual (Status Trello)")
    st.caption("Acompanhe em tempo real as entregas da rota gerada.")

    df_entregues_hoje = get_df("SELECT id, hora_conclusao FROM historico_concluidos WHERE data_conclusao = :data", {"data": DATA_REF_ROTA_STR})
    dict_concluidos_monitor = dict(zip(df_entregues_hoje['id'].astype(str), df_entregues_hoje['hora_conclusao']))
    demandas_na_rota = {str(t.get('id', '')): t for step in st.session_state.get('route_steps', []) for acao, t in step.get('actions', [])}

    if not demandas_na_rota: st.info("Gere uma rota na aba 'Roteiro do Davi' para monitorar o status das entregas aqui.")
    else:
        for card_id, row in demandas_na_rota.items():
            c1, c_status = st.columns([3.2, 2.5])
            c1.markdown(f"📦 **{row.get('Obra', '')} — {row.get('Destino', '')}** (Resp: {row.get('Supervisor', 'Sede')}) <br><span style='font-size:12px; color:gray;'>{row.get('Materiais', '')}</span>", unsafe_allow_html=True)
            if card_id in dict_concluidos_monitor: c_status.success(f"✅ **Entregue às {dict_concluidos_monitor[card_id]}**")
            else: c_status.warning("⏳ Pendente / No Carro")
            st.write("---")

    df_relatorio_demandas = st.session_state.demandas.copy()
    if not df_relatorio_demandas.empty:
        df_relatorio_demandas["Status da rota"] = df_relatorio_demandas["id"].astype(str).map(
            lambda card_id: f"Entregue às {dict_concluidos_monitor[card_id]}" if card_id in dict_concluidos_monitor else "Pendente"
        )
    renderizar_exportador(
        f"Demandas Ativas — {DATA_REF_ROTA_STR}", df_relatorio_demandas,
        "demandas_ativas", "demandas",
    )

with tab_historico:
    st.subheader(f"📋 Entregas Fisicamente Concluídas ({DATA_HOJE_REAL_STR})")
    df_hist = get_df("SELECT * FROM historico_concluidos WHERE data_conclusao = :data ORDER BY id DESC", {"data": DATA_HOJE_REAL_STR})
    if df_hist.empty: st.info("Nenhuma entrega foi registrada como finalizada no Trello no dia de hoje.")
    else: st.dataframe(df_hist, use_container_width=True, hide_index=True)
    renderizar_exportador(
        f"Entregas Concluídas — {DATA_HOJE_REAL_STR}", df_hist,
        "entregas_concluidas", "historico",
    )

with tab_enderecos:
    @fragmento_independente
    def painel_enderecos():
        st.subheader("Locais e Coordenadas GPS")
        mensagem_local = st.session_state.pop("mensagem_local", "")
        if mensagem_local:
            st.success(mensagem_local)

        col1, col2 = st.columns(2)
        with col1: apelido_input = st.text_input("Nome da Loja/Local (ex: LECI FERRAGENS)").upper().strip()
        with col2: endereco_input = st.text_input("Endereço Completo ou Link do Google Maps").strip()
        if st.button("Salvar Endereço Definitivo / Extrair GPS"):
            if apelido_input and endereco_input:
                lat, lon = buscar_coordenadas(endereco_input)
                if lat:
                    execute_db("DELETE FROM locais_removidos WHERE apelido = :apelido", {"apelido": apelido_input})
                    execute_db("INSERT INTO locais (apelido, endereco, lat, lon) VALUES (:apelido, :end, :lat, :lon) ON CONFLICT (apelido) DO UPDATE SET endereco=EXCLUDED.endereco, lat=EXCLUDED.lat, lon=EXCLUDED.lon", {"apelido": apelido_input, "end": endereco_input, "lat": lat, "lon": lon})
                    st.success(f"✅ GPS de '{apelido_input}' salvo com sucesso na Nuvem!")
                else: st.error("❌ Não consegui achar as coordenadas com esse texto. Cole o Link Direto do Google Maps!")
            else: st.warning("Preencha o nome e o endereço.")

        df_locais = get_df("SELECT * FROM locais ORDER BY apelido")
        st.dataframe(df_locais, use_container_width=True, hide_index=True)
        _conteudo_exportador(
            "Locais e Coordenadas GPS", df_locais,
            "locais_e_enderecos", "enderecos",
        )
        st.divider()
        st.markdown("#### Remover local")
        locais_removiveis = [apelido for apelido in df_locais["apelido"].tolist() if apelido not in ALIASES_LOCAL_BASE]
        if locais_removiveis:
            local_remover = st.selectbox("Selecione o local que deseja remover", locais_removiveis, index=None, placeholder="Escolha um local...")
            confirmar_remocao = st.checkbox("Confirmo que desejo remover este local e seu GPS", key="confirmar_remocao_local")
            if st.button("🗑️ Remover local selecionado", disabled=not (local_remover and confirmar_remocao)):
                execute_db("INSERT INTO locais_removidos (apelido) VALUES (:apelido) ON CONFLICT (apelido) DO NOTHING", {"apelido": local_remover})
                execute_db("DELETE FROM locais WHERE apelido = :apelido", {"apelido": local_remover})
                st.session_state["mensagem_local"] = f"✅ Local '{local_remover}' removido."
                if hasattr(st, "fragment"):
                    st.rerun(scope="fragment")
                else:
                    st.rerun()

    painel_enderecos()

with tab_custos:
    st.subheader("💰 Fechamento Mensal e Controle de Frota")
    cfg = get_df("SELECT consumo, preco_gasolina FROM config_frota WHERE id=1").iloc[0]

    @fragmento_independente
    def configuracao_base_frota():
        st.markdown("#### ⚙️ Estimativa Base do Carro")
        cc1, cc2 = st.columns(2)
        novo_consumo_cfg = cc1.number_input("Consumo Médio (km/L)", value=float(cfg['consumo']), step=0.1, key="cfg_consumo_frota")
        novo_preco_cfg = cc2.number_input("Preço da Gasolina Base (R$/L)", value=float(cfg['preco_gasolina']), step=0.01, key="cfg_preco_gasolina")
        if st.button("Atualizar Base"):
            execute_db("UPDATE config_frota SET consumo=:c, preco_gasolina=:p WHERE id=1", {"c": novo_consumo_cfg, "p": novo_preco_cfg})
            st.success("✅ Base de cálculo atualizada!")

    configuracao_base_frota()
    novo_preco = float(st.session_state.get("cfg_preco_gasolina", cfg['preco_gasolina']))
    
    st.divider()
    col_recibo, col_km = st.columns(2)
    with col_recibo:
        st.markdown("#### ⛽ Lançar Recibo de Gasto")

        @fragmento_independente
        def formulario_recibo():
            with st.form("form_recibo", clear_on_submit=True):
                f_data = st.date_input("Data do Recibo")
                fc_veic = st.selectbox("Veículo do Gasto", ["Strada", "L200"])
                fc1, fc2 = st.columns(2)
                f_litros = fc1.number_input("Litros Abastecidos", min_value=0.0, step=0.1)
                f_valor = fc2.number_input("Preço pago (R$/L)", value=novo_preco, step=0.01)
                f_manut = st.number_input("Gastos c/ Manutenção (R$)", min_value=0.0, step=10.0)
                f_obs = st.text_input("Observação (Ex: Posto Ipiranga, Troca de Óleo)")
                if st.form_submit_button("Lançar no Caixa"):
                    execute_db("INSERT INTO abastecimentos (data, litros, valor_litro, manutencao, obs, veiculo) VALUES (:data, :litros, :valor, :manut, :obs, :veic)", {"data": f_data.strftime("%d/%m/%Y"), "litros": f_litros, "valor": f_valor, "manut": f_manut, "obs": f_obs, "veic": fc_veic})
                    carregar_abastecimentos_df.clear()
                    st.success("Recibo salvo com sucesso!")

        formulario_recibo()

    with col_km:
        st.markdown("#### 🛣️ Lançar KMs Avulsos")

        @fragmento_independente
        def formulario_km_avulso():
            with st.form("form_km", clear_on_submit=True):
                k_data = st.date_input("Data da Corrida")
                k_veic = st.selectbox("Veículo Utilizado", ["Strada", "L200"])
                k_km = st.number_input("Total de KM Rodado", min_value=0.1, step=1.0)
                k_obs = st.text_input("Motivo (Ex: Ida ao banco, Frete extra)")
                if st.form_submit_button("Lançar KMs"):
                    execute_db("INSERT INTO registro_km (data, km, obs, veiculo) VALUES (:data, :km, :obs, :veic)", {"data": k_data.strftime("%d/%m/%Y"), "km": k_km, "obs": k_obs, "veic": k_veic})
                    carregar_registro_km_df.clear()
                    st.success(f"{k_km} km salvos com sucesso!")

        formulario_km_avulso()

    st.divider()
    st.markdown("#### 📅 Lançamento de Fechamento de KM (Período)")

    @fragmento_independente
    def formulario_fechamento_km():
        with st.form("form_fechamento_km", clear_on_submit=True):
            col_f1, col_f2 = st.columns([1, 2])
            f_veic = col_f1.selectbox("Veículo do Fechamento", ["Strada", "L200"])
            f_obs = col_f2.text_input("Observação (Ex: Quinzena 1, Fechamento Mensal)")
            
            col_f3, col_f4, col_f5, col_f6 = st.columns(4)
            f_data_ini = col_f3.date_input("Data Inicial")
            f_km_ini = col_f4.number_input("KM Inicial", min_value=0.0, step=1.0)
            f_data_fin = col_f5.date_input("Data Final")
            f_km_fin = col_f6.number_input("KM Final", min_value=0.0, step=1.0)
            
            if st.form_submit_button("Calcular e Lançar Fechamento"):
                km_rodado = f_km_fin - f_km_ini
                if km_rodado > 0:
                    obs_final = f"Fechamento ({f_data_ini.strftime('%d/%m')} a {f_data_fin.strftime('%d/%m')}) - {f_obs}"
                    execute_db("INSERT INTO registro_km (data, km, obs, veiculo) VALUES (:data, :km, :obs, :veic)", {"data": f_data_fin.strftime("%d/%m/%Y"), "km": km_rodado, "obs": obs_final, "veic": f_veic})
                    carregar_registro_km_df.clear()
                    st.success(f"✅ Conta fechou em {km_rodado:.1f} km! Lançamento salvo com sucesso para a {f_veic}.")
                else:
                    st.warning("⚠️ O KM Final precisa ser maior que o KM Inicial para calcular o trecho.")

    formulario_fechamento_km()

    st.divider()
    st.markdown("#### 📊 Painel de Fechamento Individualizado (Mês Atual)")
    mes_atual_str = AGORA_REAL.strftime("%m/%Y")
    
    df_km = carregar_registro_km_df()
    if 'veiculo' not in df_km.columns: df_km['veiculo'] = 'Strada'
    df_km['data_dt'] = pd.to_datetime(df_km['data'], format="%d/%m/%Y", errors='coerce')
    df_km_mes = df_km.dropna(subset=['data_dt'])[df_km.dropna(subset=['data_dt'])['data_dt'].dt.strftime('%m/%Y') == mes_atual_str].copy()
    
    km_strada = df_km_mes[df_km_mes['veiculo'] == 'Strada']['km'].sum() if not df_km_mes.empty else 0.0
    km_l200 = df_km_mes[df_km_mes['veiculo'] == 'L200']['km'].sum() if not df_km_mes.empty else 0.0
    
    df_abastec = carregar_abastecimentos_df()
    if 'veiculo' not in df_abastec.columns: df_abastec['veiculo'] = 'Strada'
    df_abastec['data_dt'] = pd.to_datetime(df_abastec['data'], format="%d/%m/%Y", errors='coerce')
    df_abastec_mes = df_abastec.dropna(subset=['data_dt'])[df_abastec.dropna(subset=['data_dt'])['data_dt'].dt.strftime('%m/%Y') == mes_atual_str].copy()
    if not df_abastec_mes.empty:
        df_abastec_mes['custo_combustivel'] = pd.to_numeric(df_abastec_mes['litros'], errors='coerce').fillna(0) * pd.to_numeric(df_abastec_mes['valor_litro'], errors='coerce').fillna(0)
        df_abastec_mes['custo_total'] = df_abastec_mes['custo_combustivel'] + pd.to_numeric(df_abastec_mes['manutencao'], errors='coerce').fillna(0)
    
    df_gas_strada = df_abastec_mes[df_abastec_mes['veiculo'] == 'Strada']
    gas_strada = (df_gas_strada['litros'] * df_gas_strada['valor_litro']).sum() if not df_gas_strada.empty else 0.0
    manut_strada = df_gas_strada['manutencao'].sum() if not df_gas_strada.empty else 0.0

    df_gas_l200 = df_abastec_mes[df_abastec_mes['veiculo'] == 'L200']
    gas_l200 = (df_gas_l200['litros'] * df_gas_l200['valor_litro']).sum() if not df_gas_l200.empty else 0.0
    manut_l200 = df_gas_l200['manutencao'].sum() if not df_gas_l200.empty else 0.0

    custo_km_strada = (gas_strada + manut_strada) / km_strada if km_strada > 0 else 0.0
    custo_km_l200 = (gas_l200 + manut_l200) / km_l200 if km_l200 > 0 else 0.0

    def tabelas_fechamento_veiculo(veiculo):
        gastos = df_abastec_mes[df_abastec_mes['veiculo'] == veiculo].copy()
        quilometragem = df_km_mes[df_km_mes['veiculo'] == veiculo].copy()
        if not gastos.empty:
            gastos = gastos[["data", "litros", "valor_litro", "custo_combustivel", "manutencao", "custo_total", "obs"]].rename(columns={
                "data": "Data", "litros": "Litros", "valor_litro": "Valor/L (R$)",
                "custo_combustivel": "Combustível (R$)", "manutencao": "Manutenção (R$)",
                "custo_total": "Total (R$)", "obs": "Observação",
            })
            for coluna in ["Valor/L (R$)", "Combustível (R$)", "Manutenção (R$)", "Total (R$)"]:
                gastos[coluna] = pd.to_numeric(gastos[coluna], errors="coerce").fillna(0).round(2)
        if not quilometragem.empty:
            quilometragem = quilometragem[["data", "km", "obs"]].rename(columns={"data": "Data", "km": "KM", "obs": "Observação"})
        return gastos, quilometragem

    gastos_strada_mes, kms_strada_mes = tabelas_fechamento_veiculo("Strada")
    gastos_l200_mes, kms_l200_mes = tabelas_fechamento_veiculo("L200")

    col_strada, col_l200 = st.columns(2)
    with col_strada:
        s1, s2 = st.columns(2)
        s1.metric("🚗 Strada (KM)", f"{km_strada:.1f} km", delta_color="off")
        s2.metric("Custo / KM", f"R$ {custo_km_strada:.2f}", "Ideal <= R$ 1.50" if custo_km_strada <= 1.50 else "Atenção!", delta_color="normal" if custo_km_strada <= 1.50 else "inverse")
        st.markdown(f"<p style='text-align:center; font-size:14px; color:#8da0b8; margin-top:-10px;'>⛽ R$ {gas_strada:.2f} &nbsp;|&nbsp; 🔧 R$ {manut_strada:.2f}</p>", unsafe_allow_html=True)
        renderizar_detalhes_fechamento("Strada", gastos_strada_mes, kms_strada_mes, "strada")

    with col_l200:
        l1, l2 = st.columns(2)
        l1.metric("🚙 L200 (KM)", f"{km_l200:.1f} km", delta_color="off")
        l2.metric("Custo / KM", f"R$ {custo_km_l200:.2f}", "Ideal <= R$ 1.50" if custo_km_l200 <= 1.50 else "Atenção!", delta_color="normal" if custo_km_l200 <= 1.50 else "inverse")
        st.markdown(f"<p style='text-align:center; font-size:14px; color:#8da0b8; margin-top:-10px;'>⛽ R$ {gas_l200:.2f} &nbsp;|&nbsp; 🔧 R$ {manut_l200:.2f}</p>", unsafe_allow_html=True)
        renderizar_detalhes_fechamento("L200", gastos_l200_mes, kms_l200_mes, "l200")

    df_resumo_fechamento = pd.DataFrame([
        {"Veículo": "Strada", "KM": round(km_strada, 2), "Combustível (R$)": round(gas_strada, 2), "Manutenção (R$)": round(manut_strada, 2), "Custo total (R$)": round(gas_strada + manut_strada, 2), "Custo/KM (R$)": round(custo_km_strada, 2)},
        {"Veículo": "L200", "KM": round(km_l200, 2), "Combustível (R$)": round(gas_l200, 2), "Manutenção (R$)": round(manut_l200, 2), "Custo total (R$)": round(gas_l200 + manut_l200, 2), "Custo/KM (R$)": round(custo_km_l200, 2)},
    ])
    renderizar_exportador(
        f"Fechamento Individualizado — {mes_atual_str}",
        {
            "Resumo": df_resumo_fechamento,
            "Gastos Strada": gastos_strada_mes,
            "KM Strada": kms_strada_mes,
            "Gastos L200": gastos_l200_mes,
            "KM L200": kms_l200_mes,
        },
        "fechamento_mensal_frota", "custos",
    )

# --- NOVA ABA: REGISTROS DA FROTA ---
with tab_registros:
    st.subheader("🗂️ Registros e Histórico da Frota")
    st.caption("Acompanhe os horários de operação, as rotas e edite os gastos detalhados dos veículos.")
    
    st.markdown("#### 🕒 Horários da Operação (Rastreador)")
    c_inicio, c_paradas = st.columns([1, 1.8])
    
    with c_inicio:
        st.markdown("**🏁 Início da Rota (Saídas do Pátio)**")
        st.caption("Marcado quando o carro afasta > 500m do escritório.")
        df_inicio = get_df("SELECT data as Data, placa as Placa, hora_inicio as \"Hora Saída\" FROM inicio_movimento ORDER BY data DESC, hora_inicio DESC")
        if not df_inicio.empty:
            st.dataframe(df_inicio, use_container_width=True, hide_index=True)
        else:
            st.info("Nenhum registro de início encontrado.")
            
    with c_paradas:
        st.markdown("**📍 Paradas Realizadas nas Obras (Geofence)**")
        st.caption("Registra tempo parado no raio de 250m do destino.")
        df_paradas_tbl = get_df("SELECT data as Data, placa as Placa, local as Local, hora_chegada as Chegada, hora_saida as Saída FROM rastreio_paradas ORDER BY id DESC LIMIT 150")
        if not df_paradas_tbl.empty:
            st.dataframe(df_paradas_tbl, use_container_width=True, hide_index=True)
        else:
            st.info("Nenhum registro de parada do rastreador encontrado.")

    st.divider()
    st.markdown("#### 💰 Histórico de Custos e Abastecimentos (Editável)")
    st.caption("Você pode alterar os valores nas tabelas abaixo ou apagar linhas inteiras. Para salvar, clique no botão azul correspondente.")
    
    cx_abast, cx_km = st.columns(2)
    with cx_abast:
        st.markdown("**⛽ Combustível e Manutenções**")

        @fragmento_independente
        def editor_abastecimentos():
            df_abastec_all = carregar_abastecimentos_df().sort_values("id", ascending=False).reset_index(drop=True)
            if not df_abastec_all.empty:
                edited_abastec = st.data_editor(df_abastec_all, num_rows="dynamic", use_container_width=True, hide_index=True, key="edit_abastec")
                if st.button("💾 Salvar Alterações (Abastecimentos)", type="primary"):
                    edited_abastec_clean = edited_abastec.drop(columns=['id'], errors='ignore')
                    save_df_to_db(edited_abastec_clean, "abastecimentos")
                    carregar_abastecimentos_df.clear()
                    st.success("Abastecimentos atualizados na Nuvem com sucesso!")
            else:
                st.info("Nenhum abastecimento ou manutenção registrada.")

        editor_abastecimentos()
            
    with cx_km:
        st.markdown("**🛣️ Quilometragem Rodada**")

        @fragmento_independente
        def editor_quilometragem():
            df_km_all = carregar_registro_km_df().sort_values("id", ascending=False).reset_index(drop=True)
            if not df_km_all.empty:
                edited_km = st.data_editor(df_km_all, num_rows="dynamic", use_container_width=True, hide_index=True, key="edit_km")
                if st.button("💾 Salvar Alterações (KM)", type="primary"):
                    edited_km_clean = edited_km.drop(columns=['id'], errors='ignore')
                    save_df_to_db(edited_km_clean, "registro_km")
                    carregar_registro_km_df.clear()
                    st.success("KMs atualizados na Nuvem com sucesso!")
            else:
                st.info("Nenhuma quilometragem registrada.")

        editor_quilometragem()

    df_abastecimentos_relatorio = carregar_abastecimentos_df().sort_values("id", ascending=False).reset_index(drop=True)
    df_quilometragens_relatorio = carregar_registro_km_df().sort_values("id", ascending=False).reset_index(drop=True)
    renderizar_exportador(
        "Registros e Histórico da Frota",
        {
            "Inícios de rota": df_inicio,
            "Paradas rastreadas": df_paradas_tbl,
            "Abastecimentos e manutenção": df_abastecimentos_relatorio,
            "Quilometragens": df_quilometragens_relatorio,
        },
        "registros_da_frota", "registros",
    )

with tab_roteiro:
    if (st.session_state.get('rota_gerada', False) and st.session_state.get('data_rota') != DATA_REF_ROTA_STR): st.session_state['rota_gerada'] = False

    df_ativos = st.session_state.demandas.copy()
    if not df_ativos.empty:
        df_ativos["Origem"] = df_ativos["Origem"].apply(canonicalizar_ponto_rota)
        df_ativos["Destino"] = df_ativos["Destino"].apply(canonicalizar_ponto_rota)

        origem_invalida, destino_invalido = df_ativos["Origem"].fillna("").isin(["", "DESCONHECIDO"]), df_ativos["Destino"].fillna("").isin(["", "DESCONHECIDO"])
        if not df_ativos[origem_invalida | destino_invalido].empty:
            st.warning(f"⚠️ Estas demandas estão sem origem ou destino legível no Trello e ficaram fora da rota: **{', '.join(df_ativos[origem_invalida | destino_invalido]['Obra'].astype(str).tolist())}**.")
            df_ativos = df_ativos[~(origem_invalida | destino_invalido)].copy()

    rota_ativa_hoje = st.session_state.get('rota_gerada', False) and st.session_state.get('data_rota') == DATA_REF_ROTA_STR

    if rota_ativa_hoje:
        st.warning("⚠️ **Atenção:** Já existe uma rota em andamento para hoje. Se você recalcular agora, o sistema apagará do mapa o histórico do que o motorista já entregou. Use este botão apenas no início do dia ou em caso de emergência total na rota.")
        txt_botao = "⚠️ Recalcular Rota do Zero (Apaga o Histórico)"
    else:
        txt_botao = "🚀 Calcular Rota Otimizada / Atualizar Rota"

    if st.button(txt_botao, type="primary", disabled=df_ativos.empty):
        with st.spinner("Analisando histórico e inteligência de nomes para traçar rota..."):
            st.session_state['demandas_adiadas'] = []
            garantir_gps_local_base()
            
            df_torre = get_df("SELECT id, hora_conclusao FROM historico_concluidos WHERE data_conclusao = :data", {"data": DATA_REF_ROTA_STR})
            dict_concluidos_torre = dict(zip(df_torre['id'].astype(str), df_torre['hora_conclusao']))
            
            past_route_steps = []
            
            res_inicio = fetch_one("SELECT MIN(hora_inicio) FROM inicio_movimento WHERE data=:data", {"data": DATA_REF_ROTA_STR})
            current_time_tsp = parse_time_to_mins(res_inicio[0]) if res_inicio and res_inicio[0] else (7 * 60 + 30)
            current_point = ponto_saida

            rota_salva = fetch_one("SELECT json_route FROM rota_ativa WHERE id = 1 AND data_rota = :data", {"data": DATA_REF_ROTA_STR})
            if rota_salva and len(dict_concluidos_torre) > 0:
                old_steps = json.loads(rota_salva[0])
                for step in old_steps:
                    if step['type'] == 'stop':
                        c_acts = [(a, t) for a, t in step.get('actions',[]) if str(t.get('id','')) in dict_concluidos_torre]
                        if c_acts:
                            new_s = step.copy()
                            new_s['actions'] = c_acts
                            past_route_steps.append(new_s)
                
                if past_route_steps:
                    current_point = past_route_steps[-1]['destino']
                    try:
                        h, m = map(int, past_route_steps[-1]['saida'].split(':'))
                        current_time_tsp = h * 60 + m
                    except: pass
            
            unpicked = [t for t in df_ativos.to_dict('records') if str(t['id']) not in dict_concluidos_torre]
            
            pontos_brutos = ([ponto_saida] + [s['destino'] for s in past_route_steps] + [t['Origem'] for t in unpicked] + [t['Destino'] for t in unpicked])
            pontos_necessarios = {canonicalizar_ponto_rota(p) for p in pontos_brutos if canonicalizar_ponto_rota(p) not in {"", "DESCONHECIDO", "NAN", "NONE"}}
            
            locais_dict, enderecos_dict = {}, {}
            
            locais_db_raw = fetch_all("SELECT apelido, endereco, lat, lon FROM locais")
            locais_db = {row[0]: (row[1], row[2], row[3]) for row in locais_db_raw}
            
            for p in pontos_necessarios:
                alvo = p
                if alvo not in locais_db:
                    p_sem_acento = remover_acentos(p)
                    encontrado = next((loc for loc in locais_db.keys() if remover_acentos(loc) == p_sem_acento), None)
                    if not encontrado:
                        matches = difflib.get_close_matches(p, locais_db.keys(), n=1, cutoff=0.8)
                        if matches: encontrado = matches[0]
                    if encontrado: alvo = encontrado

                if alvo in locais_db:
                    end_str, lat_db, lon_db = locais_db[alvo]
                    if lat_db is not None and lon_db is not None:
                        locais_dict[p] = (lat_db, lon_db)
                        enderecos_dict[p] = end_str
                    elif end_str:
                        lat, lon = buscar_coordenadas(end_str)
                        if lat is not None and lon is not None:
                            execute_db("UPDATE locais SET lat=:lat, lon=:lon WHERE apelido=:apelido", {"lat": lat, "lon": lon, "apelido": alvo})
                            locais_dict[p] = (lat, lon)
                            enderecos_dict[p] = end_str
                            
            st.session_state['enderecos_dict'] = enderecos_dict
            
            faltando = sorted(p for p in pontos_necessarios if p not in locais_dict and p not in {"", "DESCONHECIDO", "NAN", "NONE"})
            if faltando: st.warning(f"⚠️ Faltam endereços na Aba 2 para: **{', '.join(faltando)}**"); st.stop()

            pontos_unicos = list(locais_dict.keys())
            coords = [locais_dict[p] for p in pontos_unicos]
            horario_partida_matriz = datetime.combine(DATA_REF_ROTA_DATE, datetime.min.time()).replace(tzinfo=FUSO_LOCAL) + timedelta(minutes=current_time_tsp)
            if DATA_REF_ROTA_DATE == AGORA_REAL.date() and horario_partida_matriz < AGORA_REAL:
                horario_partida_matriz = AGORA_REAL + timedelta(minutes=1)

            dist_matrix, dur_matrix, fonte_matriz = calcular_matriz_rotas(coords, horario_partida_matriz)
            def get_dist_dur(p1, p2): return (0.0, 0.0) if p1 == p2 else (dist_matrix[pontos_unicos.index(p1)][pontos_unicos.index(p2)], dur_matrix[pontos_unicos.index(p1)][pontos_unicos.index(p2)])

            ordem_otimizada = otimizar_sequencia_rota(
                unpicked,
                current_point,
                estrategia,
                get_dist_dur,
                current_time_tsp,
                retornar_base=retornar_base,
                ponto_base=ponto_saida,
            )
            st.session_state['fonte_matriz_rota'] = fonte_matriz
            st.session_state['horario_matriz_rota'] = horario_partida_matriz.strftime("%d/%m/%Y %H:%M")

            carrying = []
            current = current_point
            route_steps_new = []
            total_km = sum(p_step.get('dist', 0.0) for p_step in past_route_steps)
            
            current_time = current_time_tsp
            lunch_taken = any(s.get('type') == 'lunch' for s in past_route_steps)

            while unpicked or carrying:
                if current_time >= 15 * 60 + 30: 
                    for t in [t for t in unpicked if t['Peso'] < 4]: unpicked.remove(t); st.session_state['demandas_adiadas'].append(t)

                candidates = set([t['Origem'] for t in unpicked] + [t['Destino'] for t in carrying])
                if not candidates: break

                best_point = None
                while ordem_otimizada:
                    ponto_planejado = ordem_otimizada.pop(0)
                    if ponto_planejado in candidates:
                        best_point = ponto_planejado
                        break

                if best_point is None:
                    best_point = min(candidates, key=lambda p: pontuar_parada_rota(current, p, unpicked, carrying, estrategia, get_dist_dur)[0])

                best_dist, best_dur = get_dist_dur(current, best_point)

                if 12*60 <= current_time < 13*60 and not lunch_taken:
                    route_steps_new.append({"type": "lunch", "chegada": "12:00", "saida": "13:00"})
                    current_time = 13 * 60
                    lunch_taken = True
                    
                arr_time = current_time + best_dur
                
                if current_time <= 12*60 and arr_time > 12*60 and not lunch_taken:
                    route_steps_new.append({"type": "lunch", "chegada": "12:00", "saida": "13:00"})
                    arr_time = max(arr_time + 60, 13 * 60)
                    lunch_taken = True
                    
                current_time = arr_time
                total_km += best_dist
                actions_here, service_mins = [], 0

                for t in [t for t in carrying if t['Destino'] == best_point]:
                    actions_here.append(("ENTREGAR", t)); carrying.remove(t); service_mins += t['Tempo_Entrega']
                for t in [t for t in unpicked if t['Origem'] == best_point]:
                    actions_here.append(("COLETAR", t)); unpicked.remove(t); carrying.append(t); service_mins += t['Tempo_Coleta']

                is_start_load = (best_point == ponto_saida and current_time == current_time_tsp and not any(a[0] == "ENTREGAR" for a in actions_here) and len(past_route_steps) == 0)
                
                if is_start_load:
                    chegada_str, saida_str, tempo_local_exibicao = format_time(current_time_tsp - 30), format_time(current_time_tsp), 30
                    service_mins = 0
                    dep_time = current_time_tsp
                else:
                    dep_time = current_time + service_mins
                    if current_time <= 12*60 and dep_time > 12*60 and not lunch_taken:
                        dep_time = max(dep_time + 60, 13 * 60)
                        lunch_taken = True
                        
                    chegada_str, saida_str, tempo_local_exibicao = format_time(current_time), format_time(dep_time), service_mins

                route_steps_new.append({"type": "stop", "destino": best_point, "dist": best_dist, "travel_mins": best_dur, "tempo_local": tempo_local_exibicao, "chegada": chegada_str, "saida": saida_str, "actions": actions_here})
                current_time = dep_time
                current = best_point

            if retornar_base and current != ponto_saida:
                d, dur = get_dist_dur(current, ponto_saida)
                total_km += d
                route_steps_new.append({"type": "return", "destino": ponto_saida, "dist": d, "travel_mins": dur, "chegada": format_time(current_time + dur), "saida": format_time(current_time + dur), "actions": []})
                current_time += dur

            route_steps = past_route_steps + route_steps_new

            coords_ordenadas_rota = [locais_dict[ponto_saida]]
            for step in route_steps:
                if step.get("destino") in locais_dict: coords_ordenadas_rota.append(locais_dict[step.get("destino")])
            geometria_rota, geometria_viaria = buscar_geometria_rota(coords_ordenadas_rota, horario_partida_matriz)
            
            st.session_state['rota_gerada'] = True
            st.session_state['route_steps'] = route_steps
            st.session_state['total_km'] = total_km
            st.session_state['locais_dict'] = locais_dict
            st.session_state['p_saida'] = ponto_saida
            st.session_state['horario_conclusao_min'] = current_time
            st.session_state['geometria_rota'] = geometria_rota
            st.session_state['geometria_viaria'] = geometria_viaria
            st.session_state['data_rota'] = DATA_REF_ROTA_STR

            execute_db("INSERT INTO rota_ativa (id, data_rota, json_route, json_locais, json_geometria, json_enderecos, total_km, fonte_matriz, horario_matriz) VALUES (1, :data, :route, :locs, :geom, :end, :km, :fonte, :horario) ON CONFLICT (id) DO UPDATE SET data_rota=EXCLUDED.data_rota, json_route=EXCLUDED.json_route, json_locais=EXCLUDED.json_locais, json_geometria=EXCLUDED.json_geometria, json_enderecos=EXCLUDED.json_enderecos, total_km=EXCLUDED.total_km, fonte_matriz=EXCLUDED.fonte_matriz, horario_matriz=EXCLUDED.horario_matriz", {"data": DATA_REF_ROTA_STR, "route": json.dumps(route_steps), "locs": json.dumps(locais_dict), "geom": json.dumps(geometria_rota), "end": json.dumps(enderecos_dict), "km": total_km, "fonte": fonte_matriz, "horario": horario_partida_matriz.strftime("%d/%m/%Y %H:%M")})

    if st.session_state.get('rota_gerada', False):
        route_steps, total_km, locais_dict = st.session_state['route_steps'], st.session_state['total_km'], st.session_state['locais_dict']
        enderecos_dict, p_saida = st.session_state.get('enderecos_dict', {}), st.session_state['p_saida']

        if st.session_state.get('demandas_adiadas'): st.warning(f"⚠️ **Capacidade Atingida:** {len(st.session_state['demandas_adiadas'])} demanda(s) com prazo folgado foi(ram) deixada(s) para amanhã.")
        
        df_torre = get_df("SELECT id, hora_conclusao FROM historico_concluidos WHERE data_conclusao = :data", {"data": DATA_REF_ROTA_STR})
        dict_concluidos_torre = dict(zip(df_torre['id'].astype(str), df_torre['hora_conclusao']))
        try:
            dict_checkins_torre = filtrar_checkins_da_rota(route_steps, carregar_checkins_davi(DATA_REF_ROTA_STR))
        except Exception:
            dict_checkins_torre = {}
        
        res_inicio = fetch_one("SELECT MIN(hora_inicio) FROM inicio_movimento WHERE data=:data", {"data": DATA_REF_ROTA_STR})
        hora_inicio_real = res_inicio[0] if res_inicio and res_inicio[0] else "07:30"
        
        df_paradas = get_df("SELECT local, hora_chegada, hora_saida FROM rastreio_paradas WHERE data=:data", {"data": DATA_REF_ROTA_STR})

        route_steps, final_dyn_min = aplicar_tempos_dinamicos(route_steps, dict_concluidos_torre, hora_inicio_real)

        col_esq, col_dir = st.columns([1.2, 0.8])
        with col_esq:
            st.subheader(f"📋 Roteiro de Viagem do Davi — {DATA_REF_ROTA_STR}")
            st.caption(f"🕖 Expediente: 07:00 às 17:00  •  Início da Rota do Veículo: {hora_inicio_real}")

            # A marca invisível colocada dentro de uma etapa concluída pelo Davi
            # acende a borda do próprio cartão, sem criar um painel separado.
            st.markdown("""
                <style>
                    div[data-testid="stVerticalBlockBorderWrapper"]:has(.davi-etapa-feita) {
                        border: 2px solid #39ff88 !important;
                        background: linear-gradient(145deg, rgba(34,197,94,.10), rgba(13,16,37,.78)) !important;
                        outline: 1px solid rgba(134,239,172,.85);
                        outline-offset: 1px;
                        box-shadow: 0 0 8px rgba(57,255,136,.95),
                                    0 0 22px rgba(34,197,94,.55),
                                    inset 0 0 18px rgba(34,197,94,.08);
                        animation: pulso-davi 2.2s ease-in-out infinite;
                    }
                    .davi-etapa-feita { display:none; }
                    .selo-davi-feita {
                        display:inline-block; margin:7px 0 11px; padding:5px 10px;
                        color:#d1fae5; background:rgba(22,163,74,.24);
                        border:1px solid rgba(74,222,128,.65); border-radius:999px;
                        font-size:12px; font-weight:800;
                    }
                    @keyframes pulso-davi {
                        0%, 100% { box-shadow:0 0 7px rgba(57,255,136,.75), 0 0 18px rgba(34,197,94,.38), inset 0 0 18px rgba(34,197,94,.06); }
                        50% { box-shadow:0 0 12px rgba(57,255,136,1), 0 0 30px rgba(34,197,94,.68), inset 0 0 22px rgba(34,197,94,.12); }
                    }
                </style>
            """, unsafe_allow_html=True)

            fonte_matriz_exibicao = st.session_state.get('fonte_matriz_rota', 'OSRM — malha viária sem trânsito ao vivo')
            horario_matriz_exibicao = st.session_state.get('horario_matriz_rota', '')
            if "Google Routes" in fonte_matriz_exibicao or "TomTom Routing" in fonte_matriz_exibicao:
                st.caption(f"🚦 Otimização viária: **{fonte_matriz_exibicao}** • referência {horario_matriz_exibicao}")
            else:
                st.caption(f"🛣️ Otimização viária: **{fonte_matriz_exibicao}** • para trânsito real gratuito, configure `tomtom.api_key` nos Secrets.")

            hora_atual_str = AGORA_REAL.strftime("%H:%M")
            nova_previsao_str = format_mins_to_time(final_dyn_min)
            renderizar_banner_eta(hora_atual_str, nova_previsao_str, final_dyn_min)
            
            texto_whatsapp = f"🚚 *ROTEIRO DE LOGÍSTICA - DAVI*\n📅 Data: {DATA_REF_ROTA_STR}\n🕖 Expediente: 07:00 às 17:00\n🏁 Saída do Pátio: {hora_inicio_real}\n🚗 Veículo: {veiculo_selecionado.split('(')[0].strip()}\n\n"
            
            num_parada = 1
            for i, step in enumerate(route_steps):
                if step['type'] == 'lunch':
                    st.warning(f"🍔 **Pausa para Almoço** (Previsão: {step['dyn_chegada']} às {step['dyn_saida']})")
                    texto_whatsapp += f"🍔 Almoço: {step['dyn_chegada']} às {step['dyn_saida']}\n\n"
                    continue
                if step['type'] == 'return':
                    st.info(f"🏁 **Retorno à Base:** {step['destino']} (Chegada prevista: {step['dyn_chegada']})")
                    texto_whatsapp += f"🏁 Retorno: {step['destino']} ({step['dyn_chegada']})\n"
                    continue

                is_start = (i == 0 and step['destino'] == p_saida)
                endereco_db = enderecos_dict.get(step['destino'], "")
                link_parada = endereco_db if endereco_db.startswith("http") else f"https://www.google.com/maps/dir/?api=1&destination={urllib.parse.quote(endereco_db)}" if endereco_db else f"https://www.google.com/maps/dir/?api=1&destination={locais_dict[step['destino']][0]},{locais_dict[step['destino']][1]}"

                with st.container(border=True):
                    status_tempo = f"<span style='color: #16a34a; font-weight: 600;'>✅ Concluído às {step['dyn_saida']}</span>" if step.get('is_concluded') else f"<span style='color: #f59e0b; font-weight: 600;'>⏳ Atualizado: {step['dyn_chegada']} às {step['dyn_saida']}</span>"

                    if is_start:
                        st.markdown(f"<h3 style='margin:0; color:#e4e8f4;'>🏁 PREPARAÇÃO: {step['destino']}</h3>", unsafe_allow_html=True)
                        st.caption(f"{status_tempo} | Base original: {step['chegada']} às {step['saida']}", unsafe_allow_html=True)
                        texto_whatsapp += f"🏁 *PREPARAÇÃO: {step['destino']}* ({step['dyn_chegada']} às {step['dyn_saida']})\n"
                    else:
                        st.markdown(f"<h3 style='margin:0; color:#e4e8f4;'>📍 PARADA {num_parada}: {step['destino']}</h3>", unsafe_allow_html=True)
                        st.caption(f"{status_tempo} | Base: {step['chegada']} às {step['saida']} | Trecho: {step['dist']:.1f} km", unsafe_allow_html=True)
                        texto_whatsapp += f"📍 *PARADA {num_parada}: {step['destino']}* ({step['dyn_chegada']} às {step['dyn_saida']})\n🧭 *GPS:* {link_parada}\n"

                    checkin_davi = dict_checkins_torre.get(i)
                    if checkin_davi:
                        st.markdown(
                            f"<span class='davi-etapa-feita'></span>"
                            f"<span class='selo-davi-feita'>✓ Feita pelo Davi às {html_escape(checkin_davi['hora'])}</span>",
                            unsafe_allow_html=True,
                        )
                    
                    for acao, t in step['actions']:
                        cor, icone = ("orange", "📦 COLETAR:") if acao == "COLETAR" else ("green", "📬 ENTREGAR:")
                        card_id_torre = str(t.get('id', ''))
                        concluida = card_id_torre in dict_concluidos_torre
                        check_ui = f"&nbsp;<span style='color: #16a34a; font-size: 0.95em; font-weight: bold;'>✅ (Baixa às {dict_concluidos_torre[card_id_torre]})</span>" if concluida else ""
                        
                        col_demanda, col_status = st.columns([9, 1])
                        col_demanda.markdown(f":{cor}[**{icone}**] {t['Materiais']} *(Obra: {t['Obra']})*{check_ui}", unsafe_allow_html=True)
                        texto_whatsapp += f" - {'✅ ' if concluida else ''}{acao.capitalize()}: {t['Materiais']} (Obra: {t['Obra']})\n"
                    
                    texto_paradas_reais = ""
                    paradas_local = df_paradas[df_paradas['local'] == step['destino']]
                    if not paradas_local.empty:
                        for _, rp in paradas_local.iterrows():
                            h_c = rp['hora_chegada']
                            h_s = rp['hora_saida'] if rp['hora_saida'] else ""
                            if h_s:
                                duracao = max(0, parse_time_to_mins(h_s) - parse_time_to_mins(h_c))
                                texto_paradas_reais += f"⏱️ **Tempo no local:** Chegou às {h_c} • Saiu às {h_s} <b>({duracao} min)</b><br>"
                            else:
                                texto_paradas_reais += f"📡 **Rastreador:** Chegou às {h_c} • (Ainda no local)<br>"
                                
                    if texto_paradas_reais:
                        st.markdown(f"<div style='background-color:rgba(37, 99, 235, 0.15); border-left:4px solid #2563eb; padding:10px 15px; margin-top:10px; margin-bottom:5px; font-size:14px; border-radius:6px; color:#bfdbfe;'>{texto_paradas_reais}</div>", unsafe_allow_html=True)
                        
                    texto_whatsapp += "\n"
                    if not is_start: num_parada += 1

            horario_base_fim = format_time(st.session_state.get('horario_conclusao_min', 17*60))
            horario_dyn_fim = format_mins_to_time(final_dyn_min)
            
            st.success(f"📍 **Planejamento Original (Se saísse no horário):** Término às {horario_base_fim}.")
            if final_dyn_min <= 17 * 60: st.info(f"🟢 **Previsão Real Atualizada:** Término às {horario_dyn_fim} (Dentro do expediente).")
            else: st.warning(f"⚠️ **Previsão Real Atualizada:** Término às {horario_dyn_fim} (Vai gerar hora extra!).")

            st.success(f"🛣️ **Total Rodado Planejado:** {total_km:.1f} km")

            if len(route_steps) > 1:
                waypts_addr = []
                for s in route_steps:
                    if s['type'] != 'lunch':
                        addr = enderecos_dict.get(s['destino'], "")
                        waypts_addr.append(urllib.parse.quote(addr) if addr and not addr.startswith("http") else f"{locais_dict[s['destino']][0]},{locais_dict[s['destino']][1]}")
                link_maps = f"https://www.google.com/maps/dir/?api=1&origin={waypts_addr[0]}&destination={waypts_addr[-1]}&travelmode=driving"
                if len(waypts_addr) > 2: link_maps += f"&waypoints={'|'.join(waypts_addr[1:-1][:9])}"
                texto_whatsapp += f"\n🗺️ *LINK DO ROTEIRO COMPLETO:*\n{link_maps}\n"

            st.divider()
            @fragmento_independente
            def formulario_fechamento_rota():
                with st.form("fechamento_km_rota"):
                    st.markdown("#### 💾 Fechamento de KM da Rota do Dia")
                    total_acoes = sum(len(step.get('actions', [])) for step in route_steps if step['type'] != 'lunch')
                    acoes_concluidas = sum(1 for step in route_steps for acao, t in step.get('actions', []) if str(t.get('id', '')) in dict_concluidos_torre)
                    
                    if acoes_concluidas < total_acoes: st.warning(f"⚠️ **Atenção:** Apenas **{acoes_concluidas} de {total_acoes}** demandas da rota foram concluídas hoje.")
                    else: st.success("✅ Todas as demandas desta rota foram devidamente concluídas hoje!")
                        
                    km_real = st.number_input("KM Efetivamente Rodado na Rota", value=float(total_km), step=1.0)
                    veiculo_fechamento = st.selectbox("Qual carro rodou esta rota?", ["Strada", "L200"])
                    if st.form_submit_button("Gravar KM no Painel de Custos"):
                        execute_db("INSERT INTO registro_km (data, km, obs, veiculo) VALUES (:data, :km, :obs, :veic)", {"data": DATA_REF_ROTA_STR, "km": km_real, "obs": f"Fechamento Automático ({acoes_concluidas}/{total_acoes})", "veic": veiculo_fechamento})
                        carregar_registro_km_df.clear()
                        st.success(f"✅ {km_real:.1f} km registrados para o veículo {veiculo_fechamento} na Nuvem!")

            formulario_fechamento_rota()

            url_geral, _ = obter_webhook_teams("Geral / Logística")

            @fragmento_independente
            def compartilhamento_rota():
                if url_geral:
                    if st.button("📢 Mandar Roteiro no Grupo Geral (Teams)", use_container_width=True):
                        resumo = f"O roteiro do Davi já está pronto.\n\n**Data da rota:** {DATA_REF_ROTA_STR}\n\n**Saída Real do Pátio (TIF-2123 - Strada):** {hora_inicio_real}\n\n**Previsão Dinâmica de Conclusão:** {nova_previsao_str}\n\n**Total de paradas:** {num_parada-1}\n\n**Quilometragem:** {total_km:.1f} km\n\n[Abrir GPS da Rota Completa]({link_maps})"
                        enviado, detalhe = disparar_teams(url_geral, "🚚 Roteiro Diário Atualizado!", resumo)
                        if enviado: st.success("✅ Roteiro enviado!")
                        else: st.error(f"Erro ao enviar: {detalhe}")

                st.text_area("📋 Texto Pronto para WhatsApp", value=texto_whatsapp, height=150)

            compartilhamento_rota()

        with col_dir:
            st.subheader("🗺️ Mapa da Rota")
            # MAPA CLARO (OPENSTREETMAP) RESTAURADO AQUI
            m = folium.Map(location=[-3.7319, -38.5267], zoom_start=12, tiles="OpenStreetMap")
            path_points, offsets_dict = [], {}
            
            def apply_offset(lat, lon):
                key = (round(lat, 4), round(lon, 4))
                offsets_dict[key] = offsets_dict.get(key, 0) + 1
                if offsets_dict[key] > 1: return lat - 0.00035 * (offsets_dict[key] - 1), lon + 0.00035 * (offsets_dict[key] - 1)
                return lat, lon

            p_num = 1
            if p_saida in locais_dict: path_points.append(list(apply_offset(*locais_dict[p_saida])))

            for i, step in enumerate(route_steps):
                if step.get('destino') in locais_dict and step['type'] not in ['lunch', 'return'] and not (i == 0 and step['destino'] == p_saida):
                    lat, lon = apply_offset(*locais_dict[step['destino']])
                    path_points.append([lat, lon])

                    acoes = [a[0] for a in step.get('actions', [])]
                    tem_coleta, tem_entrega = "COLETAR" in acoes, "ENTREGAR" in acoes
                    fundo_marcador = "linear-gradient(90deg, #f59e0b 0 50%, #16a34a 50% 100%)" if (tem_coleta and tem_entrega) else "#f59e0b" if tem_coleta else "#16a34a"
                    
                    popup_html = f"<b>Parada {p_num}: {html_escape(str(step['destino']))}</b><br>Previsão: {step['dyn_chegada']}<br>Ação: {html_escape(' e '.join(sorted(set(acoes))).title())}"
                    folium.Marker([lat, lon], popup=folium.Popup(popup_html, max_width=280), tooltip=f"Parada {p_num}", icon=folium.DivIcon(html=f'''<div style="background: {fundo_marcador}; color: white; border: 2px solid white; border-radius: 50%; width: 30px; height: 30px; display: flex; justify-content: center; align-items: center; font-weight: bold; box-shadow: 2px 2px 5px rgba(0,0,0,0.5); font-size: 14px;">{p_num}</div>''')).add_to(m)
                    p_num += 1

            geometria_rota, geometria_viaria = st.session_state.get('geometria_rota'), st.session_state.get('geometria_viaria', False)
            if not geometria_rota: geometria_rota, geometria_viaria = buscar_geometria_rota([locais_dict[p_saida]] + [locais_dict[s['destino']] for s in route_steps if s.get('destino') in locais_dict])

            if geometria_viaria and len(geometria_rota) > 1: folium.PolyLine(geometria_rota, color="#2563eb", weight=5, opacity=0.85).add_to(m)
            if len(path_points) > 1: m.fit_bounds(path_points, padding=(45, 45), max_zoom=14)
            if p_saida in locais_dict: folium.Marker([path_points[0][0], path_points[0][1]], popup=folium.Popup(f"<b>Saída/retorno: {html_escape(str(p_saida))}</b>", max_width=280), z_index_offset=1000, icon=folium.DivIcon(html=f'''<div style="background: linear-gradient(135deg, #2563eb, #1d4ed8); color: white; border: 3px solid white; border-radius: 50%; width: 34px; height: 34px; display: flex; justify-content: center; align-items: center; box-shadow: 2px 2px 7px rgba(0,0,0,0.6); font-size: 16px;">🏁</div>''')).add_to(m)

            st_folium(m, width=450, height=550, returned_objects=[])
            st.markdown("<div style='text-align: center; font-size: 14px; margin-top: 10px; color: #8da0b8;'><b>Legenda:</b> 🟡 Coleta | 🟢 Entrega | 🏁 Início/Retorno | 🟡🟢 Ambos</div>", unsafe_allow_html=True)

        df_relatorio_rota = montar_relatorio_rota(route_steps, dict_concluidos_torre)
        df_resumo_rota = pd.DataFrame([{
            "Data": DATA_REF_ROTA_STR,
            "Ponto de saída": p_saida,
            "Veículo": veiculo_selecionado.split('(')[0].strip(),
            "Estratégia": estrategia,
            "Distância planejada (km)": round(float(total_km), 2),
            "Início": hora_inicio_real,
            "Término previsto": format_mins_to_time(final_dyn_min),
            "Fonte viária": st.session_state.get('fonte_matriz_rota', 'OSRM — malha viária sem trânsito ao vivo'),
        }])
        renderizar_exportador(
            f"Roteiro do Davi — {DATA_REF_ROTA_STR}",
            {"Resumo": df_resumo_rota, "Paradas e demandas": df_relatorio_rota},
            "roteiro_do_davi", "roteiro",
        )
