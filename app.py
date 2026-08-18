import os
import re
import json
import math
import sqlite3
import urllib.request
import urllib.parse
from datetime import datetime
import pandas as pd
import streamlit as st
import folium
from streamlit_folium import st_folium

# =====================================================================
# CONFIGURAÇÕES DE TELA E BANCO DE DADOS
# =====================================================================
st.set_page_config(
    page_title="Aproar - Torre de Controle Logística",
    page_icon="🚚",
    layout="wide"
)

TRELLO_JSON_URL = "https://trello.com/b/tyR8YgDF.json"
DB_FILE = "enderecos_logistica.db"
CUSTO_KM_PADRAO = 1.50
VELOCIDADE_MEDIA_KMH = 25.0

UNIDADES_PROPRIAS = [
    "FIEC", "CENTRO", "MARACANAÚ", "MARACANAU", "SEBRAE", 
    "UNIFOR", "PARANGABA", "HORIZONTE", "MUSEU", "BARRA", 
    "ESCRITÓRIO", "ESCRITORIO", "CASA DA INDÚSTRIA"
]

ENDERECOS_PADRAO = [
    ("CASA DA INDÚSTRIA", "Av. Barão de Studart, 1980 - Aldeota, Fortaleza - CE"),
    ("SENAI CENTRO", "R. Padre Ibiapina, 1280 - Jacarecanga, Fortaleza - CE"),
    ("ESCOLA CENTRO", "R. Agapito dos Santos, 750 - Centro, Fortaleza - CE"),
    ("CENTRO", "R. Agapito dos Santos, 750 - Centro, Fortaleza - CE"),
    ("NR SAÚDE", "R. Padre Ibiapina, 1449 - Jacarecanga, Fortaleza - CE"),
    ("SESI BARRA DO CEARÁ", "R. Florêncio de Alencar, 900 - Barra do Ceará, Fortaleza - CE"),
    ("SENAI BARRA DO CEARÁ", "Av. Francisco Sá, 7221 - Barra do Ceará, Fortaleza - CE"),
    ("BARRA", "Av. Francisco Sá, 7221 - Barra do Ceará, Fortaleza - CE"),
    ("SESI ALBANO FRANCO", "Av. Sen. Virgílio Távora, 1103 - Distrito Industrial, Maracanaú - CE"),
    ("SESI CLUBE DA PARCERIA", "Av. Sen. Virgílio Távora, 1102 - Distrito Industrial, Maracanaú - CE"),
    ("SENAI ISTEMM", "Av. Sen. Virgílio Távora, 1395 - Distrito Industrial I, Maracanaú - CE"),
    ("SENAI CETAFR", "Av. Sen. Virgílio Távora, 1395 - Distrito Industrial I, Maracanaú - CE"),
    ("MARACANAÚ", "Av. Sen. Virgílio Távora, 1395 - Distrito Industrial I, Maracanaú - CE"),
    ("SESI PARANGABA", "Av. João Pessoa, 6754 - Parangaba, Fortaleza - CE"),
    ("SENAI PARANGABA", "Av. João Pessoa, 6760 - Damas, Fortaleza - CE"),
    ("PARANGABA", "Av. João Pessoa, 6760 - Damas, Fortaleza - CE"),
    ("SESI MUSEU", "R. Dr. João Moreira, 143 - Centro, Fortaleza - CE"),
    ("MUSEU", "R. Dr. João Moreira, 143 - Centro, Fortaleza - CE"),
    ("SESI SOBRAL", "Av. Dr. José Arimathéa Monte e Silva, 1003 - Junco, Sobral - CE"),
    ("ESCRITÓRIO", "R. Professor Mário Rocha, 84 - Joaquim Távora, Fortaleza - CE"),
    ("ESCRITORIO", "R. Professor Mário Rocha, 84 - Joaquim Távora, Fortaleza - CE"),
    ("FIEC", "Av. Barão de Studart, 1980 - Aldeota, Fortaleza - CE"),
    ("UNIFOR", "Av. Washington Soares, 1321 - Edson Queiroz, Fortaleza - CE"),
    ("HORIZONTE", "Av. Presidente Castelo Branco, 4260 - Centro, Horizonte - CE")
]

def inicializar_bd():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS locais (
                    apelido TEXT PRIMARY KEY, 
                    endereco TEXT, 
                    lat REAL, 
                    lon REAL)''')
    for apelido, end in ENDERECOS_PADRAO:
        c.execute("INSERT OR IGNORE INTO locais (apelido, endereco) VALUES (?, ?)", (apelido, end))
    conn.commit()
    conn.close()

inicializar_bd()

# =====================================================================
# MOTORES DE GEOLOCALIZAÇÃO E CÁLCULOS OSRM
# =====================================================================
def buscar_coordenadas(endereco):
    endereco_limpo = endereco.strip()
    
    # 1. Checa se o texto já possui coordenadas diretas
    match_coords = re.search(r'^(-?\d+\.\d+)[\s,;]+(-?\d+\.\d+)$', endereco_limpo)
    if match_coords:
        return float(match_coords.group(1)), float(match_coords.group(2))
        
    # 2. Extrai Coordenadas de Links do Google Maps
    if "http" in endereco_limpo or "google" in endereco_limpo.lower() or "goo.gl" in endereco_limpo.lower():
        match_at = re.search(r'@(-?\d+\.\d+),(-?\d+\.\d+)', endereco_limpo)
        if match_at: return float(match_at.group(1)), float(match_at.group(2))
        match_3d = re.search(r'3d(-?\d+\.\d+)!4d(-?\d+\.\d+)', endereco_limpo)
        if match_3d: return float(match_3d.group(1)), float(match_3d.group(2))
        try:
            req = urllib.request.Request(endereco_limpo, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as response:
                final_url = response.geturl()
            match_at = re.search(r'@(-?\d+\.\d+),(-?\d+\.\d+)', final_url)
            if match_at: return float(match_at.group(1)), float(match_at.group(2))
            match_3d = re.search(r'3d(-?\d+\.\d+)!4d(-?\d+\.\d+)', final_url)
            if match_3d: return float(match_3d.group(1)), float(match_3d.group(2))
        except: pass

    # 3. ArcGIS Geocoding (O SEGREDO: Funciona muito bem para Lojas e Comércios)
    try:
        url_arcgis = "https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates?f=json&singleLine=" + urllib.parse.quote(endereco_limpo + ", Ceará, Brasil") + "&maxLocations=1"
        req = urllib.request.Request(url_arcgis, headers={'User-Agent': 'AproarLogisticsWeb/1.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read())
            if data.get('candidates'):
                lat = data['candidates'][0]['location']['y']
                lon = data['candidates'][0]['location']['x']
                return float(lat), float(lon)
    except: pass

    # 4. Fallback Nominatim (Para ruas e endereços postais)
    try:
        url = "https://nominatim.openstreetmap.org/search?q=" + urllib.parse.quote(endereco_limpo + ", Ceará, Brasil") + "&format=json&limit=1"
        req = urllib.request.Request(url, headers={'User-Agent': 'AproarLogisticsWeb/1.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read())
            if data: return float(data[0]['lat']), float(data[0]['lon'])
    except: pass
    
    return None, None

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
            dLat = math.radians(coords[j][0] - coords[i][0])
            dLon = math.radians(coords[j][1] - coords[i][1])
            a = math.sin(dLat/2)**2 + math.cos(math.radians(coords[i][0]))*math.cos(math.radians(coords[j][0]))*math.sin(dLon/2)**2
            c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
            km = (6371 * c) * 1.3
            row_d.append(km)
            row_t.append((km / VELOCIDADE_MEDIA_KMH) * 60)
        distancias.append(row_d)
        duracoes.append(row_t)
    return distancias, duracoes

def extrair_dados_completos(texto, card_name):
    num_match = re.search(r'\b(\d{4}(?:\.\d+)?|APR[A-Z0-9]+)\b', card_name, re.IGNORECASE)
    num = num_match.group(1).upper() if num_match else ""
    
    unidade = ""
    for u in UNIDADES_PROPRIAS:
        if u.lower() in card_name.lower():
            unidade = "MARACANAÚ" if u.upper() == "MARACANAU" else u.upper()
            break
            
    if num and unidade: short_name = f"{num} - {unidade}"
    elif num: short_name = f"Obra {num}"
    elif unidade: short_name = unidade
    else: short_name = card_name[:25] + "..."

    origem, destino = "DESCONHECIDO", "DESCONHECIDO"
    materiais = "Ver Trello"
    
    if texto:
        mo = re.search(r'(?i)(?:coletar|pegar|retirar|buscar)\s+(?:no|na|em|o|a|ao|à)\s+\*?\*?(.*?)\*?\*?(?:\:|\n|$)', texto)
        if mo: origem = mo.group(1).strip().upper()

        md = re.search(r'(?i)(?:e\s+)?(?:levar|entreg(?:ar|á-lo|á-la|á-los|á-las)|devolver|encaminhar|transportar|deixar)\s+(?:para|no|na|ao|à|aos|às)\s+(?:o|a|os|as)?\s*\*?\*?(.*?)\*?\*?(?:\:|\n|$|\.)', texto)
        if md: destino = md.group(1).strip().upper()
        
        if mo and md:
            start_idx = mo.end()
            end_idx = md.start()
            if start_idx < end_idx:
                mat_text = texto[start_idx:end_idx].strip()
                mat_text = re.sub(r'\*+', '', mat_text)
                linhas_limpas = [
                    l.strip().lstrip('-').strip() 
                    for l in mat_text.split('\n') 
                    if len(l.strip()) >= 2 and l.lower() not in ['e', 'e:', 'e -', 'e,', 'para', 'levar para'] and not l.startswith(('![', '➡️', '→'))
                ]
                if linhas_limpas: materiais = " | ".join(linhas_limpas)

    if "SEBRAE" in destino or "SEBRAE" in short_name:
        if destino != "DESCONHECIDO" and destino not in ["ESCRITÓRIO", "ESCRITORIO"]:
            destino = "ESCRITÓRIO"
            materiais += " ⚠️[DEIXAR NO ESCRITÓRIO P/ SOARES]"

    return short_name, origem, destino, materiais

def classificar_prioridade(due_str):
    if not due_str: return 1, "Sem Prazo"
    try:
        due_date = datetime.strptime(due_str[:10], "%Y-%m-%d").date()
        diff = (due_date - datetime.now().date()).days
        if diff < 0: return 5, "VENCIDA"
        elif diff == 0: return 4, "HOJE"
        elif diff <= 2: return 3, f"Em {diff} dias"
        else: return 1, "Futuro"
    except: return 1, "Sem Prazo"

def format_time(minutes):
    total = int(round(minutes))
    return f"{total // 60:02d}:{total % 60:02d}"

# =====================================================================
# INTERFACE STREAMLIT
# =====================================================================
st.title("🚚 LOGÍSTICA APROAR - Torre de Controle")

if "demandas" not in st.session_state:
    st.session_state.demandas = pd.DataFrame()

# Painel Lateral (Configurações e Integração Trello)
with st.sidebar:
    st.header("⚙️ Painel de Operações")
    
    if st.button("🔄 Sincronizar com Trello", use_container_width=True, type="primary"):
        with st.spinner("Lendo Cartões e Extraindo Endereços... (Até 60s)"):
            try:
                req = urllib.request.Request(TRELLO_JSON_URL, headers={'User-Agent': 'AproarLogisticsWeb/1.0'})
                with urllib.request.urlopen(req, timeout=60) as response:
                    data = json.loads(response.read())
                
                trello_lists = {l['id']: l['name'] for l in data.get('lists', []) if not l.get('closed')}
                cards = data.get('cards', [])
                
                demandas_extraidas = []
                excluir_termos = ["CONCLUÍDAS", "CONCLUIDAS", "ENTREGUE"]
                
                df_antigo = st.session_state.demandas
                
                for c in cards:
                    if c.get('closed'): continue
                    nome_lista = trello_lists.get(c.get('idList', ''), '').upper()
                    if any(t in nome_lista for t in excluir_termos) or not nome_lista: continue
                    
                    descricao = c.get('desc', '')
                    short_name, origem, destino, materiais = extrair_dados_completos(descricao, c.get('name', ''))
                    peso, status_prazo = classificar_prioridade(c.get('due'))
                    
                    # -------------------------------------------------------------
                    # INTELIGÊNCIA: Scanner de Endereço/Link Direto no Card do Trello
                    # -------------------------------------------------------------
                    if origem and origem != "DESCONHECIDO":
                        endereco_encontrado_no_card = None
                        
                        # Tenta achar um link do google maps na descrição
                        mo_link = re.search(r'(https?://(?:www\.)?google\.[a-z\.]+/maps[^\s\n]+|https?://goo\.gl/maps/[^\s\n]+|https?://maps\.app\.goo\.gl/[^\s\n]+)', descricao)
                        if mo_link: endereco_encontrado_no_card = mo_link.group(1)
                        
                        # Tenta achar "Endereço: Rua XYZ" na descrição
                        if not endereco_encontrado_no_card:
                            mo_end = re.search(r'(?i)(?:endere[çc]o|local)\s*(?:\:|-)\s*([^\n]+)', descricao)
                            if mo_end: endereco_encontrado_no_card = mo_end.group(1).strip()
                            
                        # Se encontrou uma pista no card, guarda silenciosamente no Banco de Dados
                        if endereco_encontrado_no_card:
                            conn = sqlite3.connect(DB_FILE)
                            res = conn.execute("SELECT lat FROM locais WHERE apelido = ?", (origem,)).fetchone()
                            if not res or res[0] is None:
                                lat, lon = buscar_coordenadas(endereco_encontrado_no_card)
                                if lat:
                                    conn.execute("INSERT OR REPLACE INTO locais (apelido, endereco, lat, lon) VALUES (?, ?, ?, ?)", (origem, endereco_encontrado_no_card, lat, lon))
                                    conn.commit()
                            conn.close()
                    # -------------------------------------------------------------
                    
                    # Preservação Inteligente: Mantém edições de Tempos e Uber
                    uber_val = False
                    tc_val = 20 if origem not in UNIDADES_PROPRIAS else 10
                    te_val = 10
                    
                    if not df_antigo.empty and c['id'] in df_antigo['id'].values:
                        linha_antiga = df_antigo[df_antigo['id'] == c['id']].iloc[0]
                        uber_val = linha_antiga['Uber']
                        tc_val = linha_antiga['Tempo_Coleta']
                        te_val = linha_antiga['Tempo_Entrega']
                    
                    demandas_extraidas.append({
                        "id": c['id'],
                        "Obra": short_name,
                        "Origem": origem,
                        "Destino": destino,
                        "Materiais": materiais,
                        "Urgência": status_prazo,
                        "Peso": peso,
                        "Tempo_Coleta": tc_val,
                        "Tempo_Entrega": te_val,
                        "Uber": uber_val
                    })
                
                st.session_state.demandas = pd.DataFrame(demandas_extraidas)
                st.session_state['rota_gerada'] = False 
                st.success("✅ Demandas atualizadas com sucesso!")
            
            except Exception as e:
                st.error(f"⚠️ Erro ao acessar o Trello: {e}")
    
    st.divider()
    
    ponto_saida = st.selectbox("🏁 Ponto de Saída (07:30)", ["ESCRITÓRIO", "CASA DA INDÚSTRIA", "SENAI CENTRO", "MARACANAÚ"])
    
    estrategia = st.selectbox(
        "🎯 Estratégia da Rota",
        [
            "⚖️ Equilibrada (Padrão Aproar)", 
            "🏢 Foco em Descarregar (Agrupar)", 
            "⛽ Menor Distância (Economia)", 
            "🚨 Priorizar Urgências"
        ]
    )
    
    descricoes_estrategia = {
        "⚖️ Equilibrada (Padrão Aproar)": "Equilibra urgência, tempo de trânsito e paradas próximas.",
        "🏢 Foco em Descarregar (Agrupar)": "Prioriza descarregar materiais já coletados e limpar a caçamba.",
        "⛽ Menor Distância (Economia)": "Minimiza os km rodados, ignorando prazos curtos (Menor consumo).",
        "🚨 Priorizar Urgências": "Atende demandas vencidas ou de hoje primeiro, mesmo aumentando o percurso."
    }
    st.caption(f"ℹ️ *{descricoes_estrategia[estrategia]}*")
    
    retornar_base = st.checkbox("Retornar à base no fim do dia", value=True)
    
    st.divider()
    tracker_url = st.text_input("🛰️ Link do Rastreador Online", value="https://rastreamento.exemplo.com")
    if st.button("Abrir Rastreador ao Vivo"):
        st.markdown(f'<a href="{tracker_url}" target="_blank">Clique aqui para abrir o rastreamento em tempo real</a>', unsafe_allow_html=True)

# Trava a tela se não houver dados
if st.session_state.demandas.empty:
    st.info("👋 Bem-vindo(a) à Torre de Controle! Clique no botão vermelho **'🔄 Sincronizar com Trello'** no menu lateral para puxar as demandas ao vivo e começar.")
    st.stop()

# Abas Principais
tab_roteiro, tab_demandas, tab_enderecos = st.tabs(["🗺️ Roteiro do Davi & Mapa", "📦 Gestão de Demandas & Uber", "📍 Base de Endereços"])

# =====================================================================
# ABA 2: GESTÃO DE DEMANDAS & UBER (Tabela Editável)
# =====================================================================
with tab_demandas:
    st.subheader("Gerenciamento de Cargas e Minutos")
    st.write("Marque as caixas para enviar itens via **Uber** ou altere manualmente os minutos de coleta e entrega. As edições não serão perdidas ao sincronizar o Trello!")
    
    df_editado = st.data_editor(
        st.session_state.demandas,
        column_config={
            "Uber": st.column_config.CheckboxColumn("Enviar via Uber?", default=False),
            "Tempo_Coleta": st.column_config.NumberColumn("Tempo Coleta (min)", min_value=1, max_value=120),
            "Tempo_Entrega": st.column_config.NumberColumn("Tempo Entrega (min)", min_value=1, max_value=120),
            "Peso": None,
            "id": None
        },
        disabled=["Obra", "Origem", "Destino", "Materiais", "Urgência"],
        hide_index=True,
        use_container_width=True
    )
    st.session_state.demandas = df_editado

# =====================================================================
# ABA 3: BASE DE ENDEREÇOS
# =====================================================================
with tab_enderecos:
    st.subheader("Locais e Coordenadas GPS")
    conn = sqlite3.connect(DB_FILE)
    df_locais = pd.read_sql_query("SELECT * FROM locais ORDER BY apelido", conn)
    conn.close()
    st.dataframe(df_locais, use_container_width=True, hide_index=True)

# =====================================================================
# ABA 1: ROTEIRIZADOR & MAPA INTERATIVO
# =====================================================================
with tab_roteiro:
    df_ativos = st.session_state.demandas[st.session_state.demandas["Uber"] == False]
    df_uber = st.session_state.demandas[st.session_state.demandas["Uber"] == True]
    
    # -------------------------------------------------------------
    # BOTÃO E LÓGICA DE CÁLCULO
    # -------------------------------------------------------------
    if st.button("🚀 Calcular Rota Otimizada", type="primary"):
        with st.spinner("Traçando a melhor rota pelas ruas..."):
            # Obter Coordenadas
            conn = sqlite3.connect(DB_FILE)
            pontos_necessarios = set([ponto_saida] + df_ativos["Origem"].tolist() + df_ativos["Destino"].tolist())
            locais_dict = {}
            for p in pontos_necessarios:
                res = conn.execute("SELECT lat, lon FROM locais WHERE apelido = ?", (p,)).fetchone()
                if res and res[0] is not None:
                    locais_dict[p] = (res[0], res[1])
                else:
                    lat, lon = buscar_coordenadas(p)
                    if lat:
                        conn.execute("INSERT OR REPLACE INTO locais (apelido, endereco, lat, lon) VALUES (?, ?, ?, ?)", (p, p, lat, lon))
                        conn.commit()
                        locais_dict[p] = (lat, lon)
            conn.close()
            
            faltando = [p for p in pontos_necessarios if p not in locais_dict]
            if faltando:
                st.error(f"⚠️ Os seguintes locais possuem nomes muito incomuns ou internos e o GPS automático não os encontrou: **{', '.join(faltando)}**.")
                st.warning("👉 Vá até a Aba '📍 Base de Endereços' e insira o endereço ou um Link do Maps para eles, ou coloque na descrição do card lá no Trello.")
                st.stop()

            # Matriz OSRM
            pontos_unicos = list(locais_dict.keys())
            coords = [locais_dict[p] for p in pontos_unicos]
            dist_matrix, dur_matrix = calcular_matriz_rotas(coords)

            def get_dist_dur(p1, p2):
                if p1 == p2: return 0.0, 0.0
                i, j = pontos_unicos.index(p1), pontos_unicos.index(p2)
                return dist_matrix[i][j], dur_matrix[i][j]

            # Algoritmo de Decisão
            unpicked = df_ativos.to_dict('records')
            carrying = []
            current = ponto_saida
            route_steps = []
            total_km = 0.0
            current_time = 7.5 * 60  # 07:30
            lunch_taken = False

            while unpicked or carrying:
                candidates = set([t['Origem'] for t in unpicked] + [t['Destino'] for t in carrying])
                if not candidates: break

                best_point = None
                min_score = float('inf')
                best_dist, best_dur = 0, 0

                for p in candidates:
                    d, dur = get_dist_dur(current, p)
                    is_dropoff = any(t['Destino'] == p for t in carrying)
                    urgency = max([t['Peso'] for t in unpicked if t['Origem'] == p], default=1)

                    if "Economia" in estrategia: prio = 2 if is_dropoff else 1
                    elif "Urgências" in estrategia: prio = 10 if is_dropoff else (urgency ** 2)
                    elif "Descarregar" in estrategia: prio = 1000 if is_dropoff else 1
                    else: prio = 10 if is_dropoff else urgency

                    score = d / prio
                    if score < min_score:
                        min_score = score
                        best_point = p
                        best_dist, best_dur = d, dur

                if (current_time + best_dur) >= 720 and not lunch_taken:
                    route_steps.append({"type": "lunch", "chegada": format_time(current_time + best_dur), "saida": format_time(current_time + best_dur + 60)})
                    current_time += 60
                    lunch_taken = True

                current_time += best_dur
                total_km += best_dist

                actions_here = []
                service_mins = 0

                to_drop = [t for t in carrying if t['Destino'] == best_point]
                for t in to_drop:
                    actions_here.append(("ENTREGAR", t))
                    carrying.remove(t)
                    service_mins += t['Tempo_Entrega']

                to_pick = [t for t in unpicked if t['Origem'] == best_point]
                for t in to_pick:
                    actions_here.append(("COLETAR", t))
                    unpicked.remove(t)
                    carrying.append(t)
                    service_mins += t['Tempo_Coleta']

                route_steps.append({
                    "type": "stop",
                    "destino": best_point,
                    "dist": best_dist,
                    "travel_mins": best_dur,
                    "tempo_local": service_mins,
                    "chegada": format_time(current_time),
                    "saida": format_time(current_time + service_mins),
                    "actions": actions_here
                })
                current_time += service_mins
                current = best_point

            if retornar_base and current != ponto_saida:
                d, dur = get_dist_dur(current, ponto_saida)
                total_km += d
                route_steps.append({
                    "type": "return",
                    "destino": ponto_saida,
                    "dist": d,
                    "travel_mins": dur,
                    "chegada": format_time(current_time + dur),
                    "saida": format_time(current_time + dur),
                    "actions": []
                })
                current_time += dur
            
            # SALVAR TUDO NA MEMÓRIA DA SESSÃO
            st.session_state['rota_gerada'] = True
            st.session_state['route_steps'] = route_steps
            st.session_state['total_km'] = total_km
            st.session_state['locais_dict'] = locais_dict
            st.session_state['p_saida'] = ponto_saida
            st.session_state['df_uber_final'] = df_uber

    # -------------------------------------------------------------
    # RENDERIZAÇÃO DA ROTA E DO MAPA
    # -------------------------------------------------------------
    if st.session_state.get('rota_gerada', False):
        route_steps = st.session_state['route_steps']
        total_km = st.session_state['total_km']
        locais_dict = st.session_state['locais_dict']
        p_saida = st.session_state['p_saida']
        df_uber_final = st.session_state['df_uber_final']

        col_esq, col_dir = st.columns([1.2, 0.8])

        with col_esq:
            st.subheader("📋 Roteiro de Viagem do Davi")
            
            texto_whatsapp = f"🚚 *ROTEIRO DE LOGÍSTICA - DAVI*\n🏁 Saída: {p_saida} (07:30)\n\n"
            
            num_parada = 1
            for step in route_steps:
                if step['type'] == 'lunch':
                    st.warning(f"🍔 **Pausa para Almoço** ({step['chegada']} às {step['saida']})")
                    texto_whatsapp += f"🍔 Almoço: {step['chegada']} às {step['saida']}\n\n"
                    continue
                
                if step['type'] == 'return':
                    st.info(f"🏁 **Retorno à Base:** {step['destino']} (Chegada: {step['chegada']})")
                    texto_whatsapp += f"🏁 Retorno: {step['destino']} ({step['chegada']})\n"
                    continue

                with st.container(border=True):
                    st.markdown(f"**📍 PARADA {num_parada}: {step['destino']}** `⏰ {step['chegada']} às {step['saida']}`")
                    st.caption(f"🚘 Trecho: {step['dist']:.1f} km (~{step['travel_mins']:.0f} min) | Pátio: {step['tempo_local']} min")
                    
                    texto_whatsapp += f"📍 *PARADA {num_parada}: {step['destino']}* ({step['chegada']} às {step['saida']})\n"
                    
                    for acao, t in step['actions']:
                        cor = "orange" if acao == "COLETAR" else "green"
                        icone = "📦 COLETAR:" if acao == "COLETAR" else "📬 ENTREGAR:"
                        st.markdown(f":{cor}[**{icone}**] {t['Materiais']} *(Obra: {t['Obra']})*")
                        texto_whatsapp += f" - {acao.capitalize()}: {t['Materiais']} (Obra: {t['Obra']})\n"
                        
                    texto_whatsapp += "\n"
                    num_parada += 1

            st.success(f"🛣️ **Total Rodado:** {total_km:.1f} km | 💰 **Custo Estimado (R$ 1,50/km):** R$ {total_km * CUSTO_KM_PADRAO:.2f}")
            texto_whatsapp += f"🛣️ Total: {total_km:.1f} km | Custo: R$ {total_km * CUSTO_KM_PADRAO:.2f}\n"

            if not df_uber_final.empty:
                st.divider()
                st.markdown("### 🚕 Demandas Terceirizadas (Uber Flash)")
                texto_whatsapp += "\n📱 *DEMANDAS UBER FLASH:*\n"
                for _, u in df_uber_final.iterrows():
                    st.write(f"🚕 **{u['Materiais']}** (De: {u['Origem']} ➔ Para: {u['Destino']})")
                    texto_whatsapp += f"🚕 {u['Materiais']} (De: {u['Origem']} ➔ Para: {u['Destino']})\n"

            st.text_area("📋 Texto Pronto para WhatsApp", value=texto_whatsapp, height=150)

        with col_dir:
            st.subheader("🗺️ Mapa da Rota")
            m = folium.Map(location=[-3.7319, -38.5267], zoom_start=12)
            
            path_points = []
            p_num = 1
            for step in route_steps:
                if step.get('destino') and step['destino'] in locais_dict:
                    lat, lon = locais_dict[step['destino']]
                    path_points.append([lat, lon])
                    
                    cor_pino = "blue" if step['type'] == "return" else "red"
                    folium.Marker(
                        [lat, lon],
                        popup=f"{step['destino']}",
                        tooltip=f"Parada {p_num}: {step['destino']}",
                        icon=folium.Icon(color=cor_pino, icon="info-sign")
                    ).add_to(m)
                    if step['type'] != "return": p_num += 1

            if len(path_points) > 1:
                folium.PolyLine(path_points, color="#2563eb", weight=4, opacity=0.8).add_to(m)
                m.fit_bounds(path_points)

            st_folium(m, width=450, height=550, returned_objects=[])
