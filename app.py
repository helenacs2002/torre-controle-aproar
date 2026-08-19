import os
import re
import json
import math
import sqlite3
import time
import base64
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta
from html import escape as html_escape
from html.parser import HTMLParser
from zoneinfo import ZoneInfo
import pandas as pd
import requests
import streamlit as st
import folium
from streamlit_folium import st_folium

# =====================================================================
# CONFIGURAÇÕES DE TELA E RELÓGIO (VIRADA DE TURNO)
# =====================================================================
st.set_page_config(page_title="Aproar - Organizador de Rota", page_icon="🚚", layout="wide")

FUSO_LOCAL = ZoneInfo("America/Fortaleza")
AGORA_REAL = datetime.now(FUSO_LOCAL)

if AGORA_REAL.hour >= 18:
    DATA_REF_ROTA_DATE = AGORA_REAL.date() + timedelta(days=1)
    DATA_REF_ROTA_STR = (AGORA_REAL + timedelta(days=1)).strftime("%d/%m/%Y")
else:
    DATA_REF_ROTA_DATE = AGORA_REAL.date()
    DATA_REF_ROTA_STR = AGORA_REAL.strftime("%d/%m/%Y")

DATA_HOJE_REAL_STR = AGORA_REAL.strftime("%d/%m/%Y")
DB_FILE = "enderecos_logistica.db"

# --- INJEÇÃO DE CSS CUSTOMIZADO (VISUAL PREMIUM DARK) ---
def aplicar_estilo_customizado():
    st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
        html, body, [class*="css"], .stMarkdown, .stText, p, span, div, h1, h2, h3, h4, h5, h6 { font-family: 'Inter', sans-serif !important; color: #e4e8f4; }
        [data-testid="stAppViewContainer"] { background-color: #080b1a !important; }
        [data-testid="stSidebar"] { background-color: #0d1025 !important; border-right: 1px solid rgba(64,116,146,.2) !important; }
        [data-testid="stHeader"] { background-color: rgba(8, 11, 26, 0.8) !important; backdrop-filter: blur(5px); }
        
        button[kind="primary"], [data-testid="baseButton-primary"] { 
            background-color: #2563eb !important; 
            color: #ffffff !important; 
            border-radius: 5px !important; 
            border: 1px solid #2563eb !important;
            font-weight: 700 !important; 
            transition: all .15s;
        }
        button[kind="primary"]:hover { 
            background-color: #1d4ed8 !important; 
            border-color: #1d4ed8 !important;
            transform: translateY(-1px); 
        }
        button[kind="primary"] *, [data-testid="baseButton-primary"] * { color: #ffffff !important; }
        
        button[kind="primary"]:disabled, [data-testid="baseButton-primary"]:disabled {
            background-color: #1e293b !important;
            border-color: #1e293b !important;
            color: #64748b !important;
            cursor: not-allowed !important;
            transform: none !important;
        }
        button[kind="primary"]:disabled *, [data-testid="baseButton-primary"]:disabled * {
            color: #64748b !important;
        }

        [data-testid="baseButton-secondary"] { background-color: transparent !important; color: #8da0b8 !important; border: 1px solid rgba(64,116,146,.35) !important; border-radius: 5px !important; }
        [data-testid="baseButton-secondary"]:hover { background-color: rgba(64,116,146,.1) !important; color: #ffffff !important; }
        div[data-baseweb="input"] > div, div[data-baseweb="select"] > div, div[data-baseweb="textarea"] > div { background-color: #171c3a !important; border: 1px solid rgba(64,116,146,.2) !important; color: #e4e8f4 !important; border-radius: 5px !important; }
        [data-testid="stDataFrame"], [data-testid="stVerticalBlockBorderWrapper"], [data-testid="stAlert"] { background-color: #121530 !important; border: 1px solid rgba(64,116,146,.2) !important; border-radius: 7px !important; }
    </style>
    """, unsafe_allow_html=True)

aplicar_estilo_customizado()

# =====================================================================
# FUNÇÕES DE FORMATAÇÃO E ETA DINÂMICO Waze (COM ALMOÇO TRAVADO)
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

def aplicar_tempos_dinamicos(route_steps, dict_concluidos, start_time_str):
    agora_min = AGORA_REAL.hour * 60 + AGORA_REAL.minute
    current_min = parse_time_to_mins(start_time_str) if start_time_str else (7 * 60 + 30)
    
    for step in route_steps:
        if step['type'] == 'lunch':
            step['dyn_chegada'] = "12:00"
            step['dyn_saida'] = "13:00"
            step['is_concluded'] = False
            current_min = max(current_min, 13 * 60)
            continue
            
        if step['type'] == 'return':
            step['dyn_chegada'] = format_mins_to_time(current_min + step.get('travel_mins', 0))
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
            travel = step.get('travel_mins', 0)
            
            # Trava do horário de almoço na linha do tempo dinâmica
            if 12*60 <= current_min < 13*60:
                current_min = 13*60
                
            arr_min = current_min + travel
            
            if current_min < 12*60 and arr_min >= 12*60:
                arr_min += 60 # Empurra chegada pra depois do almoço
            
            if arr_min < agora_min: 
                arr_min = agora_min
                
            service = step.get('tempo_local', 0)
            dep_min = arr_min + service
            
            step['dyn_chegada'] = format_mins_to_time(arr_min)
            step['dyn_saida'] = format_mins_to_time(dep_min)
            current_min = dep_min
            step['is_concluded'] = False
            
    return route_steps, current_min

def renderizar_banner_eta(hora_atual_str, nova_previsao_str, final_dyn_min):
    if not hora_atual_str: return
    
    cor_previsao = "#16a34a" if final_dyn_min <= (17 * 60) else "#f59e0b" if final_dyn_min <= (17 * 60 + 30) else "#ef4444"
            
    st.markdown(f'''
    <div style="background-color: #121530; padding: 12px 20px; border-radius: 8px; border: 1px solid rgba(64,116,146,.4); display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
       <div style="font-size: 13px; color: #8da0b8; text-align: left;">
            <span style="font-size: 18px;">⏰</span> Atualizada:<br>
            <b style="color: #e4e8f4; font-size: 18px;">{hora_atual_str}</b>
       </div>
       <div style="font-size: 13px; color: #8da0b8; text-align: right;">
            <span style="font-size: 18px;">🏁</span> Previsão de Término:<br>
            <b style="color: {cor_previsao}; font-size: 18px;">{nova_previsao_str}</b>
       </div>
    </div>
    ''', unsafe_allow_html=True)

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
    st.caption(f"<div style='text-align:center; font-size: 14px; margin-bottom: 15px;'>Rota Oficial de: <b>{DATA_REF_ROTA_STR}</b></div>", unsafe_allow_html=True)

    if st.button("🔄 ATUALIZAR ROTA", use_container_width=True, type="primary"): st.rerun()

    conn = sqlite3.connect(DB_FILE)
    try:
        res = conn.execute("SELECT json_route, json_locais, json_geometria, json_enderecos, total_km FROM rota_ativa WHERE id = 1 AND data_rota = ?", (DATA_REF_ROTA_STR,)).fetchone()
        df_mobile = pd.read_sql_query("SELECT id, hora_conclusao FROM historico_concluidos WHERE data_conclusao = ?", conn, params=(DATA_HOJE_REAL_STR,))
        dict_concluidos_mobile = dict(zip(df_mobile['id'].astype(str), df_mobile['hora_conclusao']))
        res_inicio = conn.execute("SELECT MIN(hora_inicio) FROM inicio_movimento WHERE data=?", (DATA_HOJE_REAL_STR,)).fetchone()
        hora_inicio_real = res_inicio[0] if res_inicio and res_inicio[0] else "07:30"
    except: res, dict_concluidos_mobile, hora_inicio_real = None, {}, "07:30"
    conn.close()

    if not res:
        st.info("Nenhuma rota foi liberada pela Torre de Controle para hoje ainda. Aguarde a central calcular e tente atualizar a tela.")
        st.stop()

    route_steps = json.loads(res[0])
    locais_dict = json.loads(res[1])
    geometria_rota = json.loads(res[2])
    enderecos_dict = json.loads(res[3])
    total_km = res[4]
    p_saida = route_steps[0]['destino'] if route_steps else ""

    route_steps, final_dyn_min = aplicar_tempos_dinamicos(route_steps, dict_concluidos_mobile, hora_inicio_real)
    renderizar_banner_eta(AGORA_REAL.strftime("%H:%M"), format_mins_to_time(final_dyn_min), final_dyn_min)

    st.markdown(f"#### Roteiro Passo a Passo ({total_km:.1f} km)")
    p_num = 1

    for i, step in enumerate(route_steps):
        if step['type'] == 'lunch':
            st.warning(f"🍔 **Pausa para Almoço** (12:00 às 13:00)")
            continue
        if step['type'] == 'return':
            st.info(f"🏁 **Retorno à Base:** {step['destino']} (Chegada prevista: {step['dyn_chegada']})")
            continue

        is_start = (i == 0 and step['destino'] == p_saida)
        endereco_db = enderecos_dict.get(step['destino'], "")
        link_gps = endereco_db if endereco_db.startswith("http") else f"https://www.google.com/maps/dir/?api=1&destination={urllib.parse.quote(endereco_db)}" if endereco_db else f"https://www.google.com/maps/dir/?api=1&destination={locais_dict[step['destino']][0]},{locais_dict[step['destino']][1]}"

        with st.container(border=True):
            status_tempo = f"<span style='color: #16a34a;'>✅ Concluído às {step['dyn_saida']}</span>" if step.get('is_concluded') else f"<span style='color: #f59e0b;'>⏳ Atualizado: {step['dyn_chegada']} às {step['dyn_saida']}</span>"
            
            if is_start:
                st.markdown(f"**🏁 PREPARAÇÃO: {step['destino']}**")
                st.caption(f"{status_tempo} | Base: {step['chegada']} às {step['saida']}", unsafe_allow_html=True)
            else:
                st.markdown(f"**📍 PARADA {p_num}: {step['destino']}**")
                st.caption(f"{status_tempo} | Base: {step['chegada']} às {step['saida']} | Trecho: {step['dist']:.1f} km", unsafe_allow_html=True)
            
            for acao, t in step['actions']:
                cor, icone = ("orange", "📦") if acao == "COLETAR" else ("green", "📬")
                card_id = str(t.get('id', ''))
                texto_check = f" &nbsp;<span style='font-size: 1.1em; color: #16a34a;'>✅ {dict_concluidos_mobile[card_id]}</span>" if card_id in dict_concluidos_mobile else ""
                st.markdown(f":{cor}[**{icone} {acao}**] {t['Materiais']} <br>*(Obra: {t['Obra']})*{texto_check}", unsafe_allow_html=True)
                
            if not is_start:
                st.markdown(f"<a href='{link_gps}' target='_blank'><button style='width:100%; padding:15px; background-color:#2563eb; color:white; font-size:16px; font-weight:bold; border-radius:8px; border:none; margin-top:10px; cursor: pointer;'>🧭 ABRIR GPS DA PARADA {p_num}</button></a>", unsafe_allow_html=True)
                p_num += 1

    st.divider()
    st.markdown("#### 🗺️ Visão Geral da Rota")
    m_mobile = folium.Map(location=[-3.7319, -38.5267], zoom_start=12)
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
    if p_saida in locais_dict: folium.Marker([path_points_mobile[0][0], path_points_mobile[0][1]], popup=folium.Popup(f"<b>Saída: {html_escape(str(p_saida))}</b>", max_width=280), z_index_offset=1000, icon=folium.DivIcon(html=f'''<div style="background-color: #2563eb; color: white; border: 3px solid white; border-radius: 50%; width: 34px; height: 34px; display: flex; justify-content: center; align-items: center; box-shadow: 2px 2px 7px rgba(0,0,0,0.6); font-size: 16px;">🏁</div>''')).add_to(m_mobile)

    st_folium(m_mobile, height=400, use_container_width=True, returned_objects=[])
    st.markdown("<div style='text-align: center; font-size: 13px; margin-top: 5px;'><b>Legenda:</b> 🟡 Coleta | 🟢 Entrega | 🏁 Início | 🟡🟢 Ambos</div>", unsafe_allow_html=True)
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
INICIO_EXPEDIENTE_MIN = 7 * 60
INICIO_ROTA_MIN = 7 * 60 + 30  
FIM_EXPEDIENTE_MIN = 17 * 60
INICIO_ALMOCO_MIN = 12 * 60
DURACAO_ALMOCO_MIN = 60

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

ENDERECOS_PADRAO = [
    ("CASA DA INDÚSTRIA", "Av. Barão de Studart, 1980 - Aldeota, Fortaleza - CE"), ("SENAI CENTRO", "R. Padre Ibiapina, 1280 - Jacarecanga, Fortaleza - CE"), ("ESCOLA CENTRO", "R. Padre Ibiapina, 1280 - Jacarecanga, Fortaleza - CE"), ("CENTRO", "R. Padre Ibiapina, 1280 - Jacarecanga, Fortaleza - CE"), ("NR SAÚDE", "R. Padre Ibiapina, 1280 - Jacarecanga, Fortaleza - CE"), ("SESI BARRA DO CEARÁ", "Rua Florencio de Alencar, 900 - Barra do Ceará, Fortaleza - CE"), ("SENAI BARRA DO CEARÁ", "Rua Florencio de Alencar, 900 - Barra do Ceará, Fortaleza - CE"), ("BARRA", "Rua Florencio de Alencar, 900 - Barra do Ceará, Fortaleza - CE"),
    ("SESI ALBANO FRANCO", "Av. Sen. Virgílio Távora, 1395 - Distrito Industrial I, Maracanaú - CE"), ("SESI CLUBE DA PARCERIA", "Av. Sen. Virgílio Távora, 1395 - Distrito Industrial I, Maracanaú - CE"), ("SENAI ISTEMM", "Av. Sen. Virgílio Távora, 1395 - Distrito Industrial I, Maracanaú - CE"), ("SENAI CETAFR", "Av. Sen. Virgílio Távora, 1395 - Distrito Industrial I, Maracanaú - CE"), ("MARACANAÚ", "Av. Sen. Virgílio Távora, 1395 - Distrito Industrial I, Maracanaú - CE"),
    ("SESI PARANGABA", "Av. João Pessoa, 6754 - Parangaba, Fortaleza - CE"), ("SENAI PARANGABA", "Av. João Pessoa, 6760 - Damas, Fortaleza - CE"), ("PARANGABA", "Av. João Pessoa, 6760 - Damas, Fortaleza - CE"),
    ("SESI MUSEU", "R. Dr. João Moreira, 143 - Centro, Fortaleza - CE, 60030-000"), ("MUSEU", "R. Dr. João Moreira, 143 - Centro, Fortaleza - CE, 60030-000"), ("SESI SOBRAL", "Av. Dr. José Arimathéa Monte e Silva, 1003 - Junco, Sobral - CE"), ("ESCRITÓRIO", LOCAL_BASE_ENDERECO), ("ALMOXARIFADO", LOCAL_BASE_ENDERECO), ("ESPAÇO SMART", "BR-116, 9370 - Barroso, Fortaleza - CE, 60862-735"), ("ALDEOTA", "Rua Dr. José Lourenço, 1990 - Aldeota, Fortaleza - CE"), ("EDSON QUEIROZ", "Av. Dr. Valmir Pontes, 675 - Edson Queiroz, Fortaleza - CE"), ("FIEC", "Rua Dr. José Lourenço, 1990 - Aldeota, Fortaleza - CE"), ("UNIFOR", "Av. Dr. Valmir Pontes, 675 - Edson Queiroz, Fortaleza - CE"), ("HORIZONTE", "R. Raimunda Pontes - Planalto Horizonte, Horizonte - CE"), ("SEBRAE", "Avenida Monsenhor Tabosa, 777 - Meireles, Fortaleza - CE"), ("LECI FERRAGENS", "Rua Gen. Clarindo de Queiroz, 1668 - Centro, Fortaleza - CE")
]

def inicializar_bd():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS locais (apelido TEXT PRIMARY KEY, endereco TEXT, lat REAL, lon REAL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS locais_removidos (apelido TEXT PRIMARY KEY)''')
    c.execute('''CREATE TABLE IF NOT EXISTS config_frota (id INTEGER PRIMARY KEY, consumo REAL, preco_gasolina REAL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS abastecimentos (id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT, litros REAL, valor_litro REAL, manutencao REAL, obs TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS registro_km (id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT, km REAL, obs TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS historico_concluidos (id TEXT PRIMARY KEY, obra TEXT, origem TEXT, destino TEXT, materiais TEXT, data_conclusao TEXT, hora_conclusao TEXT)''')
    try: c.execute("ALTER TABLE historico_concluidos ADD COLUMN hora_conclusao TEXT")
    except: pass 
    c.execute('''CREATE TABLE IF NOT EXISTS inicio_movimento (placa TEXT, data TEXT, hora_inicio TEXT, PRIMARY KEY(placa, data))''')
    
    # === INJEÇÃO DA HORA DE PARTIDA CONFORME SEU PEDIDO ===
    c.execute("INSERT OR IGNORE INTO inicio_movimento (placa, data, hora_inicio) VALUES ('TIF', ?, '08:44')", (DATA_HOJE_REAL_STR,))
    c.execute("INSERT OR IGNORE INTO inicio_movimento (placa, data, hora_inicio) VALUES ('OSC-3842', ?, '08:35')", (DATA_HOJE_REAL_STR,))
    
    c.execute('''CREATE TABLE IF NOT EXISTS webhooks_teams (setor TEXT PRIMARY KEY, url TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS config_trello (id INTEGER PRIMARY KEY, api_key TEXT, token TEXT, id_lista_concluida TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS rota_ativa (id INTEGER PRIMARY KEY, data_rota TEXT, json_route TEXT, json_locais TEXT, json_geometria TEXT, json_enderecos TEXT, total_km REAL)''')
    c.execute("INSERT OR IGNORE INTO config_frota (id, consumo, preco_gasolina) VALUES (1, 11.5, 5.90)")
    c.execute("INSERT OR IGNORE INTO webhooks_teams (setor, url) VALUES ('Geral / Logística', '')")
    for sup in set(SUPERVISORES_MAP.values()): c.execute("INSERT OR IGNORE INTO webhooks_teams (setor, url) VALUES (?, '')", (sup,))
    for apelido, end in ENDERECOS_PADRAO:
        registro = c.execute("SELECT endereco FROM locais WHERE apelido = ?", (apelido,)).fetchone()
        if registro:
            if registro[0] != end: c.execute("UPDATE locais SET endereco = ?, lat = NULL, lon = NULL WHERE apelido = ?", (end, apelido))
        else: c.execute("INSERT INTO locais (apelido, endereco) SELECT ?, ? WHERE NOT EXISTS (SELECT 1 FROM locais_removidos WHERE apelido = ?)", (apelido, end, apelido))
    c.execute("DELETE FROM locais WHERE UPPER(TRIM(apelido)) = 'DESCONHECIDO'")
    for alias in ALIASES_LOCAL_BASE: c.execute("INSERT OR REPLACE INTO locais (apelido, endereco, lat, lon) VALUES (?, ?, ?, ?)", (alias, LOCAL_BASE_ENDERECO, LOCAL_BASE_COORDS[0], LOCAL_BASE_COORDS[1]))
    conn.commit()
    conn.close()

inicializar_bd()

if "rota_gerada" not in st.session_state or not st.session_state.get("rota_gerada"):
    conn = sqlite3.connect(DB_FILE)
    try:
        res_rota = conn.execute("SELECT json_route, json_locais, json_geometria, json_enderecos, total_km FROM rota_ativa WHERE id = 1 AND data_rota = ?", (DATA_REF_ROTA_STR,)).fetchone()
        if res_rota:
            st.session_state['route_steps'] = json.loads(res_rota[0])
            st.session_state['locais_dict'] = json.loads(res_rota[1])
            st.session_state['geometria_rota'] = json.loads(res_rota[2])
            st.session_state['enderecos_dict'] = json.loads(res_rota[3])
            st.session_state['total_km'] = res_rota[4]
            if st.session_state['route_steps']:
                st.session_state['p_saida'] = st.session_state['route_steps'][0]['destino']
                h, m = map(int, st.session_state['route_steps'][-1]['saida'].split(':'))
                st.session_state['horario_conclusao_min'] = h * 60 + m
            st.session_state['geometria_viaria'] = True
            st.session_state['rota_gerada'] = True
            st.session_state['data_rota'] = DATA_REF_ROTA_STR
    except: pass
    finally: conn.close()

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
        conn = sqlite3.connect(DB_FILE)
        registro = conn.execute("SELECT url FROM webhooks_teams WHERE setor = ?", (supervisor or setor,)).fetchone()
        conn.close()
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
    if texto in ALIASES_LOCAL_BASE: return "ESCRITÓRIO"
    return texto

def garantir_gps_local_base(conn):
    coordenadas = None
    for alias in ("ESCRITÓRIO", "ALMOXARIFADO"):
        registro = conn.execute("SELECT lat, lon FROM locais WHERE apelido = ?", (alias,)).fetchone()
        if registro and registro[0] is not None and registro[1] is not None:
            coordenadas = (float(registro[0]), float(registro[1]))
            break
    if coordenadas is None: coordenadas = LOCAL_BASE_COORDS
    if coordenadas is not None:
        for alias in ALIASES_LOCAL_BASE: conn.execute("INSERT OR REPLACE INTO locais (apelido, endereco, lat, lon) VALUES (?, ?, ?, ?)", (alias, LOCAL_BASE_ENDERECO, coordenadas[0], coordenadas[1]))
        conn.commit()
    return coordenadas

def calcular_matriz_rotas(coords):
    try:
        coords_str = ";".join([f"{lon},{lat}" for lat, lon in coords])
        url = f"https://router.project-osrm.org/table/v1/driving/{coords_str}?annotations=distance,duration"
        req = urllib.request.Request(url, headers={'User-Agent': 'AproarLogisticsWeb/1.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            res = json.loads(response.read())
            if res.get('code') == 'Ok':
                distancias = [[dist / 1000.0 for dist in row] for row in res['distances']]
                duracoes = [[dur / 60.0 for dur in row] for row in res['durations']]
                return distancias, duracoes
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
    return distancias, duracoes

def buscar_geometria_rota(coords_ordenadas):
    coords_limpas = []
    for coord in coords_ordenadas:
        if not coords_limpas or coord != coords_limpas[-1]: coords_limpas.append(coord)
    if len(coords_limpas) < 2: return [[lat, lon] for lat, lon in coords_limpas], False
    try:
        coords_str = ";".join(f"{lon},{lat}" for lat, lon in coords_limpas)
        url = f"https://router.project-osrm.org/route/v1/driving/{coords_str}?overview=full&geometries=geojson&steps=false"
        req = urllib.request.Request(url, headers={'User-Agent': 'AproarLogisticsWeb/1.0'})
        with urllib.request.urlopen(req, timeout=15) as response:
            res = json.loads(response.read())
        if res.get("code") == "Ok" and res.get("routes"): return [[lat, lon] for lat, lon in res["routes"][0]["geometry"]["coordinates"]], True
    except: pass
    return [[lat, lon] for lat, lon in coords_limpas], False

# === LÓGICA DE EXTRAÇÃO COM TRANSBORDOS ===
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
        
        # Inteligência de Transbordo
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
        posicoes.append({"ID": partes[0].strip(), "Placa": partes[1].strip(), "Última atualização": partes[2].strip(), "Latitude": latitude, "Longitude": longitude, "Velocidade (km/h)": velocidade, "Situação": {"P": "Parado", "M": "Em movimento", "L": "Ligado", "D": "Desligado"}.get(codigo_status, codigo_status or "Não informado"), "Código": codigo_status, "Ícone": partes[7].strip(), "Endereço": partes[8].strip()})
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
        req = urllib.request.Request(TRELLO_JSON_URL, headers={'User-Agent': 'AproarLogisticsWeb/1.0'})
        with urllib.request.urlopen(req, timeout=15) as response: data = json.loads(response.read())
        trello_lists = {l['id']: l['name'] for l in data.get('lists', []) if not l.get('closed')}
        cards = data.get('cards', [])
        acoes = data.get('actions', [])
        
        conn = sqlite3.connect(DB_FILE)
        ids_ja_notificados = {str(r[0]) for r in conn.execute("SELECT id FROM historico_concluidos WHERE data_conclusao = ?", (DATA_HOJE_REAL_STR,)).fetchall()}
        
        novas_entregas = 0
        for c in cards:
            if c.get('closed'): continue
            if lista_esta_concluida(trello_lists.get(c.get('idList', ''), '').upper()):
                momento_conclusao = encontrar_conclusao_de_hoje(c['id'], acoes)
                if momento_conclusao and str(c['id']) not in ids_ja_notificados and momento_conclusao.strftime("%d/%m/%Y") == DATA_HOJE_REAL_STR:
                    short_name, origem, destino, materiais = extrair_dados_completos(c.get('desc', ''), c.get('name', ''))
                    url_webhook, _ = obter_webhook_teams(destino, supervisor=SUPERVISORES_MAP.get(destino, "Sede / Logística"), obra=short_name)
                    hora_str = momento_conclusao.strftime("%H:%M")

                    # ANTI-SPAM (MÁXIMO 5 MINUTOS DE ATRASO PARA AVISAR NO TEAMS)
                    if (agora_loop - momento_conclusao).total_seconds() / 60 <= 5 and url_webhook:
                        disparar_teams(url_webhook, f"✅ Entrega concluída — {destino}", "✅ **Os materiais foram entregues na obra e a demanda tomou baixa no Trello.**\n\n" + f"**Obra:** {short_name}\n\n**Local:** {destino}\n\n**Materiais:** {materiais}\n\n**Data e Hora:** {momento_conclusao.strftime('%d/%m/%Y às %H:%M')}")

                    conn.execute("INSERT OR REPLACE INTO historico_concluidos (id, obra, origem, destino, materiais, data_conclusao, hora_conclusao) VALUES (?, ?, ?, ?, ?, ?, ?)", (c['id'], short_name, origem, destino, materiais, DATA_HOJE_REAL_STR, hora_str))
                    novas_entregas += 1
        conn.commit()
        conn.close()
        if novas_entregas > 0: st.toast(f"🔔 {novas_entregas} nova(s) baixa(s) no Trello registrada(s)!", icon="✅")
    except: pass

    try:
        sessao, pagina = st.session_state.get("protege_sessao"), st.session_state.get("protege_pagina")
        usuario_protege, senha_protege, ids_veiculos = carregar_config_protege()
        if sessao and pagina and ids_veiculos:
            posicoes = consultar_posicoes_protege(sessao, pagina, ids_veiculos)
            conn = sqlite3.connect(DB_FILE)
            for p in posicoes:
                if p["Velocidade (km/h)"] > 0:
                    if not conn.execute("SELECT hora_inicio FROM inicio_movimento WHERE placa=? AND data=?", (p["Placa"], DATA_HOJE_REAL_STR)).fetchone():
                        match_time = re.search(r'(\d{2}:\d{2})', p['Última atualização'])
                        conn.execute("INSERT INTO inicio_movimento (placa, data, hora_inicio) VALUES (?, ?, ?)", (p["Placa"], DATA_HOJE_REAL_STR, match_time.group(1) if match_time else agora_loop.strftime("%H:%M")))
            conn.commit()
            conn.close()
    except: pass

# =====================================================================
# INTERFACE STREAMLIT
# =====================================================================
try:
    with open("logo.png", "rb") as image_file: encoded_string = base64.b64encode(image_file.read()).decode()
    st.markdown(f'<div style="display: flex; align-items: center; gap: 30px; margin-bottom: 25px; margin-top: -20px;"><img src="data:image/png;base64,{encoded_string}" width="260" style="flex-shrink: 0;"><h1 style="margin: 0; padding: 0; line-height: 1.2;">ORGANIZADOR DE ROTA - SUPRIMENTOS</h1></div>', unsafe_allow_html=True)
except: st.title("🚚 ORGANIZADOR DE ROTA - SUPRIMENTOS")

if "demandas" not in st.session_state: st.session_state.demandas = pd.DataFrame(columns=COLUNAS_DEMANDAS)

with st.sidebar:
    st.header("⚙️ Painel de Operações")
    st.caption(f"📅 Planejamento ativo para: **{DATA_REF_ROTA_STR}**")
    
    if hasattr(st, "fragment"):
        @st.fragment(run_every="60s")
        def _loop_operacoes(): loop_automacoes_background()
        _loop_operacoes()

    st.markdown("---")
    st.markdown("📱 **App do Motorista**")
    st.components.v1.html("""<script>function copyLink() { try { var tempInput = document.createElement("input"); tempInput.value = window.parent.location.origin + window.parent.location.pathname + "?davi=true"; document.body.appendChild(tempInput); tempInput.select(); document.execCommand("copy"); document.body.removeChild(tempInput); var btn = document.getElementById("btn"); btn.innerText = "✅ Copiado!"; btn.style.backgroundColor = "#16a34a"; btn.style.color = "white"; btn.style.border = "1px solid #16a34a"; setTimeout(() => { btn.innerText = "🔗 Copiar Link do Davi"; btn.style.backgroundColor = "transparent"; btn.style.color = "#8da0b8"; btn.style.border = "1px solid rgba(64,116,146,.35)"; }, 2500); } catch (err) { alert("Erro ao copiar."); } }</script><button id="btn" onclick="copyLink()" style="width:100%; padding:8px; background-color:transparent; color:#8da0b8; border:1px solid rgba(64,116,146,.35); border-radius:5px; font-family:sans-serif; font-size:14px; font-weight:bold; cursor:pointer;">🔗 Copiar Link do Davi</button>""", height=45)
    st.markdown("---")

    if st.button("🔄 Sincronizar Manualmente com Trello", use_container_width=True, type="primary"):
        with st.spinner("Puxando demandas ao vivo..."):
            try:
                loop_automacoes_background()
                req = urllib.request.Request(TRELLO_JSON_URL, headers={'User-Agent': 'AproarLogisticsWeb/1.0'})
                with urllib.request.urlopen(req, timeout=60) as response: data = json.loads(response.read())
                
                trello_lists = {l['id']: l['name'] for l in data.get('lists', []) if not l.get('closed')}
                demandas_extraidas = []
                conn = sqlite3.connect(DB_FILE)
                
                for c in data.get('cards', []):
                    if c.get('closed') or lista_esta_concluida(trello_lists.get(c.get('idList', ''), '').upper()): continue
                    short_name, origem, destino, materiais = extrair_dados_completos(c.get('desc', ''), c.get('name', ''))
                    peso, status_prazo = classificar_prioridade(c.get('due'))
                    endereco_card = encontrar_endereco_na_descricao(c.get('desc', ''))
                    if endereco_card:
                        lat, lon = buscar_coordenadas(endereco_card)
                        if lat:
                            if origem and origem not in UNIDADES_PROPRIAS and not conn.execute("SELECT lat FROM locais WHERE apelido = ?", (origem,)).fetchone(): conn.execute("INSERT OR REPLACE INTO locais (apelido, endereco, lat, lon) VALUES (?, ?, ?, ?)", (origem, endereco_card, lat, lon))
                            if destino and destino not in UNIDADES_PROPRIAS and not conn.execute("SELECT lat FROM locais WHERE apelido = ?", (destino,)).fetchone(): conn.execute("INSERT OR REPLACE INTO locais (apelido, endereco, lat, lon) VALUES (?, ?, ?, ?)", (destino, endereco_card, lat, lon))
                    
                    tc_val = 20 if origem not in UNIDADES_PROPRIAS else 10
                    te_val = 10
                    if not st.session_state.demandas.empty and c['id'] in st.session_state.demandas['id'].values:
                        linha_antiga = st.session_state.demandas[st.session_state.demandas['id'] == c['id']].iloc[0]
                        tc_val, te_val = linha_antiga['Tempo_Coleta'], linha_antiga['Tempo_Entrega']
                    
                    demandas_extraidas.append({"id": c['id'], "Obra": short_name, "Origem": origem, "Destino": destino, "Materiais": materiais, "Urgência": status_prazo, "Peso": peso, "Tempo_Coleta": tc_val, "Tempo_Entrega": te_val, "Supervisor": SUPERVISORES_MAP.get(destino, "Sede / Logística")})

                conn.commit()
                conn.close()
                st.session_state.demandas = pd.DataFrame(demandas_extraidas, columns=COLUNAS_DEMANDAS)
                st.success("✅ Trello Sincronizado e Demandas Importadas!")
            except Exception as e: st.error(f"⚠️ Erro ao acessar o Trello: {e}")
    
    st.divider()
    veiculo_selecionado = st.radio("🚗 Tipo de Custeio da Rota", ["Frota da Empresa (Calcula Gasolina)", "Carro Próprio/Frete (R$ 1,50/km)"])
    st.divider()
    ponto_saida = st.selectbox("🏁 Ponto de Saída", ["ESCRITÓRIO", "CASA DA INDÚSTRIA", "SENAI CENTRO", "MARACANAÚ"])
    estrategia = st.selectbox("🎯 Estratégia da Rota", ["⚖️ Equilibrada", "🏢 Foco em Descarregar", "⛽ Menor Distância", "🚨 Priorizar Urgências"])
    st.caption(f"ℹ️ *{ {'⚖️ Equilibrada': 'Mescla urgência com proximidade para fazer a rota mais lógica e eficiente.', '🏢 Foco em Descarregar': 'Prioriza entregar os materiais o quanto antes para esvaziar a caçamba.', '⛽ Menor Distância': 'Foca 100% no menor KM percorrido (Economia de combustível).', '🚨 Priorizar Urgências': 'Foca 100% nas demandas Vencidas ou programadas para Hoje.'}[estrategia] }*")
    retornar_base = st.checkbox("Retornar à base no fim do dia", value=True)

if st.session_state.demandas.empty: st.info("👋 Bem-vindo(a) à Torre de Controle! Clique no botão **'🔄 Sincronizar com Trello'** no menu lateral para puxar as demandas ao vivo e começar.")

tab_roteiro, tab_rastreador, tab_demandas, tab_historico, tab_enderecos, tab_custos, tab_integ = st.tabs(["🗺️ Roteiro do Davi", "📡 Rastreador ao Vivo", "📦 Demandas Ativas", "📋 Histórico & Concluídos", "📍 Endereços", "💰 Dashboard & Custos", "⚙️ Integrações"])

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

                conn = sqlite3.connect(DB_FILE)
                try:
                    for p in posicoes:
                        if p["Velocidade (km/h)"] > 0 and not conn.execute("SELECT hora_inicio FROM inicio_movimento WHERE placa=? AND data=?", (p["Placa"], DATA_HOJE_REAL_STR)).fetchone():
                            match_time = re.search(r'(\d{2}:\d{2})', p['Última atualização'])
                            conn.execute("INSERT INTO inicio_movimento (placa, data, hora_inicio) VALUES (?, ?, ?)", (p["Placa"], DATA_HOJE_REAL_STR, match_time.group(1) if match_time else datetime.now(FUSO_LOCAL).strftime("%H:%M")))
                            conn.commit()
                    start_times = {row[0]: row[1] for row in conn.execute("SELECT placa, hora_inicio FROM inicio_movimento WHERE data=?", (DATA_HOJE_REAL_STR,)).fetchall()}
                except: start_times = {}
                finally: conn.close()

                for p in posicoes: p['🟢 Início (Hoje)'] = start_times.get(p['Placa'], "Ainda não andou")

                velocidades = [p["Velocidade (km/h)"] for p in posicoes]
                met1, met2, met3 = st.columns(3)
                met1.metric("Veículos localizados", len(posicoes))
                met2.metric("Em movimento", sum(1 for v in velocidades if v > 0))
                met3.metric("Última leitura", datetime.now(FUSO_LOCAL).strftime("%H:%M:%S"))

                mapa = folium.Map(location=[sum(p["Latitude"] for p in posicoes) / len(posicoes), sum(p["Longitude"] for p in posicoes) / len(posicoes)], zoom_start=11, tiles="OpenStreetMap")
                limites = []
                for p in posicoes:
                    cor, icone = ("green", "play") if p["Velocidade (km/h)"] > 0 else ("red", "stop")
                    limites.append([p["Latitude"], p["Longitude"]])
                    folium.Marker([p["Latitude"], p["Longitude"]], popup=folium.Popup(f"<b>{p['Placa']}</b><br>{p['Situação']} — {p['Velocidade (km/h)']:.0f} km/h<br>Atualização: {p['Última atualização']}<br>{p['Endereço']}", max_width=360), tooltip=f"{p['Placa']} — {p['Situação']}", icon=folium.Icon(color=cor, icon=icone, prefix="fa")).add_to(mapa)

                if len(limites) > 1: mapa.fit_bounds(limites, padding=(35, 35))
                st_folium(mapa, height=520, use_container_width=True, returned_objects=[], key="mapa_rastreador_protege")
                st.dataframe(pd.DataFrame(posicoes)[["Placa", "🟢 Início (Hoje)", "Última atualização", "Velocidade (km/h)", "Situação", "Endereço"]], use_container_width=True, hide_index=True)

            except:
                st.session_state.pop("protege_sessao", None); st.session_state.pop("protege_pagina", None)
                st.error("Não consegui entrar automaticamente no rastreador. Confira as credenciais.")

        if hasattr(st, "fragment"): st.fragment(run_every="30s")(exibir_painel_rastreador)()
        else: exibir_painel_rastreador()

with tab_demandas:
    st.subheader(f"Gerenciamento de Cargas da Rota ({DATA_REF_ROTA_STR})")
    st.session_state.demandas = st.data_editor(st.session_state.demandas, column_config={"Tempo_Coleta": st.column_config.NumberColumn("Tempo Coleta (min)", min_value=1, max_value=120), "Tempo_Entrega": st.column_config.NumberColumn("Tempo Entrega (min)", min_value=1, max_value=120), "Peso": None, "id": None, "Supervisor": None}, disabled=["Obra", "Origem", "Destino", "Materiais", "Urgência"], hide_index=True, use_container_width=True)
    st.divider()
    st.subheader("📣 Monitoramento da Rota Atual (Status Trello)")
    st.caption("Acompanhe em tempo real as entregas da rota gerada.")

    conn = sqlite3.connect(DB_FILE)
    df_entregues_hoje = pd.read_sql_query("SELECT id, hora_conclusao FROM historico_concluidos WHERE data_conclusao = ?", conn, params=(DATA_HOJE_REAL_STR,))
    conn.close()

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

with tab_historico:
    st.subheader(f"📋 Entregas Fisicamente Concluídas ({DATA_HOJE_REAL_STR})")
    conn = sqlite3.connect(DB_FILE)
    df_hist = pd.read_sql_query("SELECT * FROM historico_concluidos WHERE data_conclusao = ? ORDER BY rowid DESC", conn, params=(DATA_HOJE_REAL_STR,))
    conn.close()
    if df_hist.empty: st.info("Nenhuma entrega foi registrada como finalizada no Trello no dia de hoje.")
    else: st.dataframe(df_hist, use_container_width=True, hide_index=True)

with tab_enderecos:
    st.subheader("Locais e Coordenadas GPS")
    col1, col2 = st.columns(2)
    with col1: apelido_input = st.text_input("Nome da Loja/Local (ex: LECI FERRAGENS)").upper().strip()
    with col2: endereco_input = st.text_input("Endereço Completo ou Link do Google Maps").strip()
    if st.button("Salvar Endereço Definitivo / Extrair GPS"):
        if apelido_input and endereco_input:
            lat, lon = buscar_coordenadas(endereco_input)
            if lat:
                conn = sqlite3.connect(DB_FILE)
                conn.execute("DELETE FROM locais_removidos WHERE apelido = ?", (apelido_input,))
                conn.execute("INSERT OR REPLACE INTO locais (apelido, endereco, lat, lon) VALUES (?, ?, ?, ?)", (apelido_input, endereco_input, lat, lon))
                conn.commit(); conn.close()
                st.success(f"✅ GPS de '{apelido_input}' salvo com sucesso!")
            else: st.error("❌ Não consegui achar as coordenadas com esse texto. Cole o Link Direto do Google Maps!")
        else: st.warning("Preencha o nome e o endereço.")

    conn = sqlite3.connect(DB_FILE)
    df_locais = pd.read_sql_query("SELECT * FROM locais ORDER BY apelido", conn)
    conn.close()
    st.dataframe(df_locais, use_container_width=True, hide_index=True)
    st.divider()
    st.markdown("#### Remover local")
    locais_removiveis = [apelido for apelido in df_locais["apelido"].tolist() if apelido not in ALIASES_LOCAL_BASE]
    if locais_removiveis:
        local_remover = st.selectbox("Selecione o local que deseja remover", locais_removiveis, index=None, placeholder="Escolha um local...")
        confirmar_remocao = st.checkbox("Confirmo que desejo remover este local e seu GPS", key="confirmar_remocao_local")
        if st.button("🗑️ Remover local selecionado", disabled=not (local_remover and confirmar_remocao)):
            conn = sqlite3.connect(DB_FILE)
            conn.execute("INSERT OR REPLACE INTO locais_removidos (apelido) VALUES (?)", (local_remover,))
            conn.execute("DELETE FROM locais WHERE apelido = ?", (local_remover,))
            conn.commit(); conn.close()
            st.success(f"✅ Local '{local_remover}' removido."); st.rerun()

with tab_custos:
    st.subheader("💰 Fechamento Mensal e Controle de Frota")
    conn = sqlite3.connect(DB_FILE)
    cfg = pd.read_sql_query("SELECT consumo, preco_gasolina FROM config_frota WHERE id=1", conn).iloc[0]
    
    st.markdown("#### ⚙️ Estimativa Base do Carro")
    cc1, cc2 = st.columns(2)
    novo_consumo = cc1.number_input("Consumo Médio (km/L)", value=float(cfg['consumo']), step=0.1)
    novo_preco = cc2.number_input("Preço da Gasolina Base (R$/L)", value=float(cfg['preco_gasolina']), step=0.01)
    if st.button("Atualizar Base"):
        conn.execute("UPDATE config_frota SET consumo=?, preco_gasolina=? WHERE id=1", (novo_consumo, novo_preco))
        conn.commit(); st.success("✅ Base de cálculo atualizada!")
    
    st.divider()
    col_recibo, col_km = st.columns(2)
    with col_recibo:
        st.markdown("#### ⛽ Lançar Recibo de Gasto")
        with st.form("form_recibo", clear_on_submit=True):
            f_data = st.date_input("Data do Recibo")
            fc1, fc2 = st.columns(2)
            f_litros, f_valor = fc1.number_input("Litros Abastecidos", min_value=0.0, step=0.1), fc2.number_input("Preço pago (R$/L)", value=novo_preco, step=0.01)
            f_manut = st.number_input("Gastos c/ Manutenção (R$)", min_value=0.0, step=10.0)
            f_obs = st.text_input("Observação (Ex: Posto Ipiranga, Troca de Óleo)")
            if st.form_submit_button("Lançar no Caixa"):
                conn.execute("INSERT INTO abastecimentos (data, litros, valor_litro, manutencao, obs) VALUES (?, ?, ?, ?, ?)", (f_data.strftime("%d/%m/%Y"), f_litros, f_valor, f_manut, f_obs))
                conn.commit(); st.success("Recibo salvo com sucesso!")

    with col_km:
        st.markdown("#### 🛣️ Lançar KMs Avulsos")
        with st.form("form_km", clear_on_submit=True):
            k_data, k_km, k_obs = st.date_input("Data da Corrida"), st.number_input("Total de KM Rodado", min_value=0.1, step=1.0), st.text_input("Motivo (Ex: Ida ao banco, Frete extra)")
            if st.form_submit_button("Lançar KMs"):
                conn.execute("INSERT INTO registro_km (data, km, obs) VALUES (?, ?, ?)", (k_data.strftime("%d/%m/%Y"), k_km, k_obs))
                conn.commit(); st.success(f"{k_km} km salvos com sucesso!")

    st.divider()
    st.markdown("#### 📊 Painel de Fechamento (Mês Atual)")
    mes_atual_str = AGORA_REAL.strftime("%m/%Y")
    
    df_km = pd.read_sql_query("SELECT data, km FROM registro_km", conn)
    df_km['data_dt'] = pd.to_datetime(df_km['data'], format="%d/%m/%Y", errors='coerce')
    km_mes = df_km.dropna(subset=['data_dt'])[df_km.dropna(subset=['data_dt'])['data_dt'].dt.strftime('%m/%Y') == mes_atual_str]['km'].sum()
    
    df_abastec = pd.read_sql_query("SELECT data, litros, valor_litro, manutencao FROM abastecimentos", conn)
    df_abastec['data_dt'] = pd.to_datetime(df_abastec['data'], format="%d/%m/%Y", errors='coerce')
    df_abastec_mes = df_abastec.dropna(subset=['data_dt'])[df_abastec.dropna(subset=['data_dt'])['data_dt'].dt.strftime('%m/%Y') == mes_atual_str].copy()
    
    gasto_gasolina_mes = (df_abastec_mes['litros'] * df_abastec_mes['valor_litro']).sum() if not df_abastec_mes.empty else 0.0
    gasto_manutencao_mes = df_abastec_mes['manutencao'].sum() if not df_abastec_mes.empty else 0.0
    custo_real_por_km = ((gasto_gasolina_mes + gasto_manutencao_mes) / km_mes) if km_mes > 0 else 0.0

    met1, met2, met3, met4 = st.columns(4)
    met1.metric("KM Total Rodado", f"{km_mes:.1f} km", f"Mês: {mes_atual_str}", delta_color="off")
    met2.metric("Gasto com Gasolina", f"R$ {gasto_gasolina_mes:.2f}", "Pelo recibo", delta_color="inverse")
    met3.metric("Gasto em Manutenção", f"R$ {gasto_manutencao_mes:.2f}", "Pelo recibo", delta_color="inverse")
    met4.metric("CUSTO REAL / KM", f"R$ {custo_real_por_km:.2f}", "Mais barato que frete!" if custo_real_por_km <= 1.50 else "Atenção: Carro caro!", delta_color="normal" if custo_real_por_km <= 1.50 else "inverse")
    conn.close()

with tab_integ:
    st.subheader("⚙️ Configurações de Integrações e APIs")
    st.markdown("### Integração dos Grupos no Teams")
    conn = sqlite3.connect(DB_FILE)
    for index, row in pd.read_sql_query("SELECT * FROM webhooks_teams ORDER BY setor", conn).iterrows():
        setor = row['setor']
        nova_url = st.text_input(f"👤 {setor}", value=row['url'], key=f"tms_db_{setor}")
        if st.button(f"Salvar {setor}"):
            conn.execute("UPDATE webhooks_teams SET url=? WHERE setor=?", (nova_url, setor))
            conn.commit(); st.success(f"Link de '{setor}' salvo no banco local!")
    conn.close()

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
        with st.spinner("Analisando histórico e traçando rota a partir de onde o motorista está..."):
            st.session_state['demandas_adiadas'] = []
            conn = sqlite3.connect(DB_FILE)
            garantir_gps_local_base(conn)
            
            df_torre = pd.read_sql_query("SELECT id, hora_conclusao FROM historico_concluidos WHERE data_conclusao = ?", conn, params=(DATA_HOJE_REAL_STR,))
            dict_concluidos_torre = dict(zip(df_torre['id'].astype(str), df_torre['hora_conclusao']))
            
            past_route_steps = []
            
            res_inicio = conn.execute("SELECT MIN(hora_inicio) FROM inicio_movimento WHERE data=?", (DATA_HOJE_REAL_STR,)).fetchone()
            current_time_tsp = parse_time_to_mins(res_inicio[0]) if res_inicio and res_inicio[0] else (8 * 60 + 44)
            current_point = ponto_saida

            rota_salva = conn.execute("SELECT json_route FROM rota_ativa WHERE id = 1 AND data_rota = ?", (DATA_HOJE_REAL_STR,)).fetchone()
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
            for p in pontos_necessarios:
                res = conn.execute("SELECT endereco, lat, lon FROM locais WHERE apelido = ?", (p,)).fetchone()
                if res and res[1] is not None and res[2] is not None:
                    locais_dict[p] = (res[1], res[2])
                    enderecos_dict[p] = res[0]
                    continue
                if res and res[0]:
                    lat, lon = buscar_coordenadas(res[0])
                    if lat is not None and lon is not None:
                        conn.execute("UPDATE locais SET lat = ?, lon = ? WHERE apelido = ?", (lat, lon, p))
                        locais_dict[p], enderecos_dict[p] = (lat, lon), res[0]
            conn.commit(); conn.close()
            st.session_state['enderecos_dict'] = enderecos_dict
            
            faltando = sorted(p for p in pontos_necessarios if p not in locais_dict and p not in {"", "DESCONHECIDO", "NAN", "NONE"})
            if faltando: st.warning(f"⚠️ Faltam endereços na Aba 2 para: **{', '.join(faltando)}**"); st.stop()

            pontos_unicos = list(locais_dict.keys())
            coords = [locais_dict[p] for p in pontos_unicos]
            dist_matrix, dur_matrix = calcular_matriz_rotas(coords)
            def get_dist_dur(p1, p2): return (0.0, 0.0) if p1 == p2 else (dist_matrix[pontos_unicos.index(p1)][pontos_unicos.index(p2)], dur_matrix[pontos_unicos.index(p1)][pontos_unicos.index(p2)])

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

                best_point, min_score, best_dist, best_dur = None, float('inf'), 0, 0
                destinos_no_carro = set(t['Destino'] for t in carrying)

                for p in candidates:
                    d, dur = get_dist_dur(current, p)
                    is_dropoff, is_pickup = any(t['Destino'] == p for t in carrying), any(t['Origem'] == p for t in unpicked)
                    urgency = max([t['Peso'] for t in unpicked if t['Origem'] == p] + [1])
                    
                    if "Menor Distância" in estrategia: score = d + (dur * 0.1)
                    else:
                        prio = 1.0
                        if is_dropoff: prio = 2.0 if sum(1 for t in unpicked if t['Destino'] == p) == 0 else 0.1
                        if is_pickup: prio *= 3.0 if set(t['Destino'] for t in unpicked if t['Origem'] == p).intersection(destinos_no_carro) else 1.5
                        if "Urgências" in estrategia: prio *= urgency ** 2
                        elif "Descarregar" in estrategia and is_dropoff: prio *= 5.0
                        score = (d + (dur * 0.1)) / max(prio, 0.001)
                    
                    if d < 0.1: score = -1.0
                    if score < min_score: min_score, best_point, best_dist, best_dur = score, p, d, dur

                # INJEÇÃO ESTRITA DO HORÁRIO DE ALMOÇO NA CRIAÇÃO DA ROTA
                if current_time < (12 * 60) and (current_time + best_dur) >= (12 * 60) and not lunch_taken:
                    route_steps_new.append({"type": "lunch", "chegada": "12:00", "saida": "13:00"})
                    current_time = 13 * 60
                    lunch_taken = True
                elif current_time >= (12 * 60) and current_time < (13 * 60) and not lunch_taken:
                    route_steps_new.append({"type": "lunch", "chegada": "12:00", "saida": "13:00"})
                    current_time = 13 * 60
                    lunch_taken = True

                current_time += best_dur
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
                else:
                    chegada_str, saida_str, tempo_local_exibicao = format_time(current_time), format_time(current_time + service_mins), service_mins

                route_steps_new.append({"type": "stop", "destino": best_point, "dist": best_dist, "travel_mins": best_dur, "tempo_local": tempo_local_exibicao, "chegada": chegada_str, "saida": saida_str, "actions": actions_here})
                current_time += service_mins
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
            geometria_rota, geometria_viaria = buscar_geometria_rota(coords_ordenadas_rota)
            
            st.session_state['rota_gerada'] = True
            st.session_state['route_steps'] = route_steps
            st.session_state['total_km'] = total_km
            st.session_state['locais_dict'] = locais_dict
            st.session_state['p_saida'] = ponto_saida
            st.session_state['horario_conclusao_min'] = current_time
            st.session_state['geometria_rota'] = geometria_rota
            st.session_state['geometria_viaria'] = geometria_viaria
            st.session_state['data_rota'] = DATA_REF_ROTA_STR

            conn = sqlite3.connect(DB_FILE)
            conn.execute("INSERT OR REPLACE INTO rota_ativa (id, data_rota, json_route, json_locais, json_geometria, json_enderecos, total_km) VALUES (1, ?, ?, ?, ?, ?, ?)", (DATA_REF_ROTA_STR, json.dumps(route_steps), json.dumps(locais_dict), json.dumps(geometria_rota), json.dumps(enderecos_dict), total_km))
            conn.commit(); conn.close()

    if st.session_state.get('rota_gerada', False):
        route_steps, total_km, locais_dict = st.session_state['route_steps'], st.session_state['total_km'], st.session_state['locais_dict']
        enderecos_dict, p_saida = st.session_state.get('enderecos_dict', {}), st.session_state['p_saida']

        if st.session_state.get('demandas_adiadas'): st.warning(f"⚠️ **Capacidade Atingida:** {len(st.session_state['demandas_adiadas'])} demanda(s) com prazo folgado foi(ram) deixada(s) para amanhã.")
        
        conn = sqlite3.connect(DB_FILE)
        cfg = pd.read_sql_query("SELECT consumo, preco_gasolina FROM config_frota WHERE id=1", conn).iloc[0]
        custo_rota = (total_km / float(cfg['consumo'])) * float(cfg['preco_gasolina']) if "Empresa" in veiculo_selecionado else total_km * 1.50
        
        df_torre = pd.read_sql_query("SELECT id, hora_conclusao FROM historico_concluidos WHERE data_conclusao = ?", conn, params=(DATA_HOJE_REAL_STR,))
        dict_concluidos_torre = dict(zip(df_torre['id'].astype(str), df_torre['hora_conclusao']))
        res_inicio = conn.execute("SELECT MIN(hora_inicio) FROM inicio_movimento WHERE data=?", (DATA_HOJE_REAL_STR,)).fetchone()
        hora_inicio_real = res_inicio[0] if res_inicio and res_inicio[0] else "07:30"
        conn.close()

        route_steps, final_dyn_min = aplicar_tempos_dinamicos(route_steps, dict_concluidos_torre, hora_inicio_real)

        col_esq, col_dir = st.columns([1.2, 0.8])
        with col_esq:
            st.subheader(f"📋 Roteiro de Viagem do Davi — {DATA_REF_ROTA_STR}")
            st.caption(f"🕖 Expediente: 07:00 às 17:00  •  Início da Rota do Veículo: {hora_inicio_real}")

            hora_atual_str, nova_previsao_str, nova_previsao_dt = calcular_eta_dinamico(route_steps, dict_concluidos_torre, p_saida)
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
                    status_tempo = f"<span style='color: #16a34a;'>✅ Concluído às {step['dyn_saida']}</span>" if step.get('is_concluded') else f"<span style='color: #f59e0b;'>⏳ Atualizado: {step['dyn_chegada']} às {step['dyn_saida']}</span>"

                    if is_start:
                        st.markdown(f"**🏁 PREPARAÇÃO: {step['destino']}**")
                        st.caption(f"{status_tempo} | Base original: {step['chegada']} às {step['saida']}", unsafe_allow_html=True)
                        texto_whatsapp += f"🏁 *PREPARAÇÃO: {step['destino']}* ({step['dyn_chegada']} às {step['dyn_saida']})\n"
                    else:
                        st.markdown(f"**📍 PARADA {num_parada}: {step['destino']}**")
                        st.caption(f"{status_tempo} | Base: {step['chegada']} às {step['saida']} | Trecho: {step['dist']:.1f} km", unsafe_allow_html=True)
                        texto_whatsapp += f"📍 *PARADA {num_parada}: {step['destino']}* ({step['dyn_chegada']} às {step['dyn_saida']})\n🧭 *GPS:* {link_parada}\n"
                    
                    for acao, t in step['actions']:
                        cor, icone = ("orange", "📦 COLETAR:") if acao == "COLETAR" else ("green", "📬 ENTREGAR:")
                        card_id_torre = str(t.get('id', ''))
                        concluida = card_id_torre in dict_concluidos_torre
                        check_ui = f"&nbsp;<span style='color: #16a34a; font-size: 0.95em;'>✅ (Baixa às {dict_concluidos_torre[card_id_torre]})</span>" if concluida else ""
                        
                        col_demanda, col_status = st.columns([9, 1])
                        col_demanda.markdown(f":{cor}[**{icone}**] {t['Materiais']} *(Obra: {t['Obra']})*{check_ui}", unsafe_allow_html=True)
                        texto_whatsapp += f" - {'✅ ' if concluida else ''}{acao.capitalize()}: {t['Materiais']} (Obra: {t['Obra']})\n"
                        
                    texto_whatsapp += "\n"
                    if not is_start: num_parada += 1

            horario_base_fim = format_time(st.session_state.get('horario_conclusao_min', 17*60))
            horario_dyn_fim = format_mins_to_time(final_dyn_min)
            
            st.success(f"📍 **Planejamento Original (Se saísse no horário):** Término às {horario_base_fim}.")
            if final_dyn_min <= 17 * 60: st.info(f"🟢 **Previsão Real Atualizada:** Término às {horario_dyn_fim} (Dentro do expediente).")
            else: st.warning(f"⚠️ **Previsão Real Atualizada:** Término às {horario_dyn_fim} (Vai gerar hora extra!).")

            st.success(f"🛣️ **Total Rodado Planejado:** {total_km:.1f} km | 💰 **Custo:** R$ {custo_rota:.2f}")

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
            with st.form("fechamento_km_rota"):
                st.markdown("#### 💾 Fechamento de KM da Rota do Dia")
                total_acoes = sum(len(step.get('actions', [])) for step in route_steps if step['type'] != 'lunch')
                acoes_concluidas = sum(1 for step in route_steps for acao, t in step.get('actions', []) if str(t.get('id', '')) in dict_concluidos_torre)
                
                if acoes_concluidas < total_acoes: st.warning(f"⚠️ **Atenção:** Apenas **{acoes_concluidas} de {total_acoes}** demandas da rota foram concluídas hoje.")
                else: st.success("✅ Todas as demandas desta rota foram devidamente concluídas hoje!")
                    
                km_real = st.number_input("KM Efetivamente Rodado na Rota", value=float(total_km), step=1.0)
                if st.form_submit_button("Gravar KM no Painel de Custos"):
                    conn = sqlite3.connect(DB_FILE)
                    conn.execute("INSERT INTO registro_km (data, km, obs) VALUES (?, ?, ?)", (DATA_REF_ROTA_STR, km_real, f"Fechamento Automático ({acoes_concluidas}/{total_acoes})"))
                    conn.commit(); conn.close()
                    st.success(f"✅ {km_real:.1f} km registrados!")

            url_geral, _ = obter_webhook_teams("Geral / Logística")
            if url_geral:
                if st.button("📢 Mandar Roteiro no Grupo Geral (Teams)", use_container_width=True):
                    resumo = f"O roteiro do Davi já está pronto.\n\n**Data da rota:** {DATA_REF_ROTA_STR}\n\n**Saída Real do Pátio:** {hora_inicio_real}\n\n**Previsão Dinâmica de Conclusão:** {nova_previsao_str}\n\n**Total de paradas:** {num_parada-1}\n\n**Quilometragem:** {total_km:.1f} km\n\n[Abrir GPS da Rota Completa]({link_maps})"
                    enviado, detalhe = disparar_teams(url_geral, "🚚 Roteiro Diário Atualizado!", resumo)
                    if enviado: st.success("✅ Roteiro enviado!")
                    else: st.error(f"Erro ao enviar: {detalhe}")

            st.text_area("📋 Texto Pronto para WhatsApp", value=texto_whatsapp, height=150)

        with col_dir:
            st.subheader("🗺️ Mapa da Rota")
            m = folium.Map(location=[-3.7319, -38.5267], zoom_start=12)
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
            if p_saida in locais_dict: folium.Marker([path_points[0][0], path_points[0][1]], popup=folium.Popup(f"<b>Saída/retorno: {html_escape(str(p_saida))}</b>", max_width=280), z_index_offset=1000, icon=folium.DivIcon(html=f'''<div style="background-color: #2563eb; color: white; border: 3px solid white; border-radius: 50%; width: 34px; height: 34px; display: flex; justify-content: center; align-items: center; box-shadow: 2px 2px 7px rgba(0,0,0,0.6); font-size: 16px;">🏁</div>''')).add_to(m)

            st_folium(m, width=450, height=550, returned_objects=[])
            st.markdown("<div style='text-align: center; font-size: 14px; margin-top: 10px;'><b>Legenda:</b> 🟡 Coleta | 🟢 Entrega | 🏁 Início/Retorno | 🟡🟢 Ambos</div>", unsafe_allow_html=True)
