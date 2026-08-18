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
# CONFIGURAÇÕES DE TELA, EQUIPE E BANCO DE DADOS
# =====================================================================
st.set_page_config(
    page_title="Aproar - Torre de Controle Logística",
    page_icon="🚚",
    layout="wide"
)

TRELLO_JSON_URL = "https://trello.com/b/tyR8YgDF.json"
DB_FILE = "enderecos_logistica.db"
VELOCIDADE_MEDIA_KMH = 25.0

UNIDADES_PROPRIAS = [
    "FIEC", "CENTRO", "MARACANAÚ", "SEBRAE", 
    "UNIFOR", "PARANGABA", "HORIZONTE", "MUSEU", "BARRA", 
    "ESCRITÓRIO", "CASA DA INDÚSTRIA"
]

SUPERVISORES_MAP = {
    "BARRA": "Luis Eduardo Rodrigues",
    "SESI BARRA DO CEARÁ": "Luis Eduardo Rodrigues",
    "SENAI BARRA DO CEARÁ": "Luis Eduardo Rodrigues",
    "CENTRO": "Victor Bezerra",
    "SENAI CENTRO": "Victor Bezerra",
    "ESCOLA CENTRO": "Victor Bezerra",
    "NR SAÚDE": "Victor Bezerra",
    "MUSEU": "Victor Bezerra",
    "SESI MUSEU": "Victor Bezerra",
    "CASA DA INDÚSTRIA": "Gustavo Souza",
    "FIEC": "Gustavo Souza",
    "MARACANAÚ": "Neto Porto",
    "SESI ALBANO FRANCO": "Neto Porto",
    "SESI CLUBE DA PARCERIA": "Neto Porto",
    "SENAI ISTEMM": "Neto Porto",
    "SENAI CETAFR": "Neto Porto",
    "HORIZONTE": "Soares Junior",
    "SESI HORIZONTE": "Soares Junior",
    "SENAI HORIZONTE": "Soares Junior",
    "SEBRAE": "Soares Junior",
    "UNIFOR": "Joel Lima",
    "ESCRITÓRIO": "Sede / Logística",
    "PARANGABA": "Sede / Logística"
}

ENDERECOS_PADRAO = [
    ("CASA DA INDÚSTRIA", "Av. Barão de Studart, 1980 - Aldeota, Fortaleza - CE"),
    ("SENAI CENTRO", "R. Padre Ibiapina, 1280 - Jacarecanga, Fortaleza - CE"),
    ("ESCOLA CENTRO", "R. Agapito dos Santos, 750 - Centro, Fortaleza - CE"),
    ("CENTRO", "R. Padre Ibiapina, 1280 - Jacarecanga, Fortaleza - CE"),
    ("NR SAÚDE", "R. Padre Ibiapina, 1449 - Jacarecanga, Fortaleza - CE"),
    ("SESI BARRA DO CEARÁ", "R. Florêncio de Alencar, 900 - Barra do Ceará, Fortaleza - CE"),
    ("SENAI BARRA DO CEARÁ", "Av. Francisco Sá, 7221 - Barra do Ceará, Fortaleza - CE"),
    ("BARRA", "Rua Florencio de Alencar, 900 - Barra do Ceará, Fortaleza - CE"),
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
    ("ALDEOTA", "Rua Dr. José Lourenço, 1990 - Aldeota, Fortaleza - CE"),
    ("EDSON QUEIROZ", "Av. Dr. Valmir Pontes, 675 - Edson Queiroz, Fortaleza - CE"),
    ("FIEC", "Av. Barão de Studart, 1980 - Aldeota, Fortaleza - CE"),
    ("UNIFOR", "Av. Washington Soares, 1321 - Edson Queiroz, Fortaleza - CE"),
    ("HORIZONTE", "R. Raimunda Pontes - Planalto Horizonte, Horizonte - CE"),
    ("LECI FERRAGENS", "Rua Gen. Clarindo de Queiroz, 1668 - Centro, Fortaleza - CE")
]

def inicializar_bd():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS locais (apelido TEXT PRIMARY KEY, endereco TEXT, lat REAL, lon REAL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS config_frota (id INTEGER PRIMARY KEY, consumo REAL, preco_gasolina REAL, custo_fixo REAL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS abastecimentos (id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT, litros REAL, valor_litro REAL, manutencao REAL, obs TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS webhooks_teams (setor TEXT PRIMARY KEY, url TEXT)''')
    
    c.execute("INSERT OR IGNORE INTO config_frota (id, consumo, preco_gasolina, custo_fixo) VALUES (1, 11.5, 5.90, 23.0)")
    c.execute("INSERT OR IGNORE INTO webhooks_teams (setor, url) VALUES ('Geral / Logística', '')")
    
    # Adiciona todos os supervisores na tabela do Teams
    for sup in set(SUPERVISORES_MAP.values()):
        c.execute("INSERT OR IGNORE INTO webhooks_teams (setor, url) VALUES (?, '')", (sup,))
    
    for apelido, end in ENDERECOS_PADRAO:
        c.execute("INSERT OR IGNORE INTO locais (apelido, endereco) VALUES (?, ?)", (apelido, end))
    conn.commit()
    conn.close()

inicializar_bd()

# =====================================================================
# FUNÇÕES DE INTEGRAÇÃO (TEAMS E MAPAS)
# =====================================================================
def disparar_teams(webhook_url, titulo, mensagem, cor="22c55e"):
    if not webhook_url or "http" not in webhook_url: return False
    payload = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "themeColor": cor,
        "summary": titulo,
        "sections": [{
            "activityTitle": titulo,
            "text": mensagem
        }]
    }
    try:
        req = urllib.request.Request(webhook_url, json.dumps(payload).encode('utf-8'), {'Content-Type': 'application/json'})
        urllib.request.urlopen(req, timeout=5)
        return True
    except:
        return False

def is_in_ceara(lat, lon):
    return -7.5 <= lat <= -2.5 and -42.0 <= lon <= -37.0

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
                lat = float(data['candidates'][0]['location']['y'])
                lon = float(data['candidates'][0]['location']['x'])
                if is_in_ceara(lat, lon): return lat, lon
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

def normalizar_local(nome):
    if not nome: return "DESCONHECIDO"
    n = nome.upper().strip()
    if "MARACANAU" in n: n = n.replace("MARACANAU", "MARACANAÚ")
    if "ESCRITORIO" in n: n = n.replace("ESCRITORIO", "ESCRITÓRIO")
    if "DEPÓSITO" in n: n = n.replace("DEPÓSITO", "DEPOSITO")
    if "ESPACO" in n: n = n.replace("ESPACO", "ESPAÇO")
    return n

def extrair_dados_completos(texto, card_name):
    num_match = re.search(r'\b(\d{4}(?:\.\d+)?|APR[A-Z0-9]+)\b', card_name, re.IGNORECASE)
    num = num_match.group(1).upper() if num_match else ""
    
    unidade = ""
    for u in UNIDADES_PROPRIAS:
        if normalizar_local(u) in normalizar_local(card_name):
            unidade = normalizar_local(u)
            break
            
    short_name = f"{num} - {unidade}" if (num and unidade) else num if num else unidade if unidade else card_name[:25] + "..."

    origem, destino = "DESCONHECIDO", "DESCONHECIDO"
    materiais = "Ver Trello"
    
    if texto:
        mo = re.search(r'(?i)(?:coletar|pegar|retirar|buscar)\s+(?:no|na|em|o|a|ao|à)\s+\*?\*?(.*?)\*?\*?(?:\:|\n|$)', texto)
        if mo: origem = normalizar_local(mo.group(1))

        md = re.search(r'(?i)(?:e\s+)?(?:levar|entreg(?:ar|á-lo|á-la|á-los|á-las)|devolver|encaminhar|transportar|deixar)\s+(?:para|no|na|ao|à|aos|às)\s+(?:o|a|os|as)?\s*\*?\*?(.*?)\*?\*?(?:\:|\n|$|\.)', texto)
        if md: destino = normalizar_local(md.group(1))
        
        if mo and md:
            start_idx = mo.end()
            end_idx = md.start()
            if start_idx < end_idx:
                mat_text = texto[start_idx:end_idx].strip()
                mat_text = re.sub(r'\*+', '', mat_text)
                linhas_limpas = [l.strip().lstrip('-').strip() for l in mat_text.split('\n') if len(l.strip()) >= 2 and l.lower() not in ['e', 'e:', 'e -', 'e,', 'para', 'levar para'] and not l.startswith(('![', '➡️', '→'))]
                if linhas_limpas: materiais = " | ".join(linhas_limpas)

    if "SEBRAE" in destino or "SEBRAE" in short_name:
        if destino != "DESCONHECIDO" and destino not in ["ESCRITÓRIO"]:
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

# Painel Lateral
with st.sidebar:
    st.header("⚙️ Painel de Operações")
    
    if st.button("🔄 Sincronizar com Trello", use_container_width=True, type="primary"):
        with st.spinner("Puxando demandas ao vivo..."):
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
                    
                    # Define quem é o supervisor dessa entrega
                    supervisor = SUPERVISORES_MAP.get(destino, "Sede / Logística")
                    
                    endereco_card = encontrar_endereco_na_descricao(descricao)
                    if endereco_card:
                        lat, lon = buscar_coordenadas(endereco_card)
                        if lat:
                            conn = sqlite3.connect(DB_FILE)
                            if origem not in UNIDADES_PROPRIAS and origem != "DESCONHECIDO":
                                res = conn.execute("SELECT lat FROM locais WHERE apelido = ?", (origem,)).fetchone()
                                if not res or res[0] is None:
                                    conn.execute("INSERT OR REPLACE INTO locais (apelido, endereco, lat, lon) VALUES (?, ?, ?, ?)", (origem, endereco_card, lat, lon))
                            if destino not in UNIDADES_PROPRIAS and destino != "DESCONHECIDO":
                                res = conn.execute("SELECT lat FROM locais WHERE apelido = ?", (destino,)).fetchone()
                                if not res or res[0] is None:
                                    conn.execute("INSERT OR REPLACE INTO locais (apelido, endereco, lat, lon) VALUES (?, ?, ?, ?)", (destino, endereco_card, lat, lon))
                            conn.commit()
                            conn.close()
                    
                    uber_val = False
                    tc_val = 20 if origem not in UNIDADES_PROPRIAS else 10
                    te_val = 10
                    
                    if not df_antigo.empty and c['id'] in df_antigo['id'].values:
                        linha_antiga = df_antigo[df_antigo['id'] == c['id']].iloc[0]
                        uber_val = linha_antiga['Uber']
                        tc_val = linha_antiga['Tempo_Coleta']
                        te_val = linha_antiga['Tempo_Entrega']
                    
                    demandas_extraidas.append({
                        "id": c['id'], "Obra": short_name, "Origem": origem, "Destino": destino,
                        "Materiais": materiais, "Urgência": status_prazo, "Peso": peso,
                        "Tempo_Coleta": tc_val, "Tempo_Entrega": te_val, "Uber": uber_val,
                        "Supervisor": supervisor
                    })
                
                st.session_state.demandas = pd.DataFrame(demandas_extraidas)
                st.session_state['rota_gerada'] = False 
                st.success("✅ Demandas atualizadas com sucesso!")
            
            except Exception as e:
                st.error(f"⚠️ Erro ao acessar o Trello: {e}")
    
    st.divider()
    veiculo_selecionado = st.radio("🚗 Veículo da Rota", ["Carro da Empresa (Apenas Gasolina)", "Carro Próprio/Frete (R$ 1,50/km)"])
    st.divider()
    
    ponto_saida = st.selectbox("🏁 Ponto de Saída (07:30)", ["ESCRITÓRIO", "CASA DA INDÚSTRIA", "SENAI CENTRO", "MARACANAÚ"])
    estrategia = st.selectbox("🎯 Estratégia da Rota", ["⚖️ Equilibrada", "🏢 Foco em Descarregar", "⛽ Menor Distância", "🚨 Priorizar Urgências"])
    retornar_base = st.checkbox("Retornar à base no fim do dia", value=True)

if st.session_state.demandas.empty:
    st.info("👋 Bem-vindo(a) à Torre de Controle! Clique no botão vermelho **'🔄 Sincronizar com Trello'** no menu lateral para puxar as demandas ao vivo e começar.")
    st.stop()

# =====================================================================
# ABAS PRINCIPAIS
# =====================================================================
tab_roteiro, tab_demandas, tab_enderecos, tab_custos, tab_teams = st.tabs([
    "🗺️ Roteiro do Davi", 
    "📦 Demandas & Entregas", 
    "📍 Endereços",
    "💰 Dashboard & Custos",
    "💬 Integração Teams"
])

# -------------------------------------------------------------
# ABA: DEMANDAS E ALERTAS TEAMS
# -------------------------------------------------------------
with tab_demandas:
    st.subheader("Gerenciamento de Cargas e Minutos")
    df_editado = st.data_editor(
        st.session_state.demandas,
        column_config={
            "Uber": st.column_config.CheckboxColumn("Enviar via Uber?", default=False),
            "Tempo_Coleta": st.column_config.NumberColumn("Tempo Coleta (min)", min_value=1, max_value=120),
            "Tempo_Entrega": st.column_config.NumberColumn("Tempo Entrega (min)", min_value=1, max_value=120),
            "Peso": None, "id": None, "Supervisor": None
        },
        disabled=["Obra", "Origem", "Destino", "Materiais", "Urgência"],
        hide_index=True, use_container_width=True
    )
    st.session_state.demandas = df_editado
    
    st.divider()
    st.subheader("🔔 Baixa de Entregas (Avisar Supervisor)")
    st.write("Clique no botão correspondente para avisar o supervisor no Teams de que o material da obra dele foi entregue.")
    
    conn = sqlite3.connect(DB_FILE)
    df_pendentes = st.session_state.demandas[st.session_state.demandas["Uber"] == False]
    
    if df_pendentes.empty:
        st.info("Nenhuma demanda pendente para o carro.")
    else:
        for idx, row in df_pendentes.iterrows():
            sup = row['Supervisor']
            dest = row['Destino']
            mat = row['Materiais']
            
            c1, c2 = st.columns([3, 1])
            c1.markdown(f"📦 **{dest}** (Resp: {sup}) <br> <span style='font-size:12px; color:gray;'>{mat}</span>", unsafe_allow_html=True)
            if c2.button(f"✅ Avisar {sup.split()[0]}", key=f"btn_concluir_{row['id']}", use_container_width=True):
                url_webhook = conn.execute("SELECT url FROM webhooks_teams WHERE setor=?", (sup,)).fetchone()
                if url_webhook and url_webhook[0]:
                    mensagem = f"O material foi entregue com sucesso pela logística.\n\n**Local:** {dest}\n**Itens:** {mat}"
                    if disparar_teams(url_webhook[0], f"✅ Entrega Concluída: {dest}", mensagem):
                        st.success(f"Notificação enviada para {sup} no Teams!")
                    else:
                        st.error("Erro ao enviar mensagem para o Teams.")
                else:
                    st.warning(f"O supervisor {sup} ainda não tem um link do Teams cadastrado na aba de Configurações.")
            st.write("---")
    conn.close()

# -------------------------------------------------------------
# ABA: ENDEREÇOS
# -------------------------------------------------------------
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
                conn.execute("INSERT OR REPLACE INTO locais (apelido, endereco, lat, lon) VALUES (?, ?, ?, ?)", (apelido_input, endereco_input, lat, lon))
                conn.commit()
                conn.close()
                st.success(f"✅ GPS de '{apelido_input}' salvo com sucesso!")
            else:
                st.error("❌ Não consegui achar as coordenadas com esse texto. Cole o Link Direto do Google Maps!")
        else:
            st.warning("Preencha o nome e o endereço.")

    conn = sqlite3.connect(DB_FILE)
    df_locais = pd.read_sql_query("SELECT * FROM locais ORDER BY apelido", conn)
    conn.close()
    st.dataframe(df_locais, use_container_width=True, hide_index=True)

# -------------------------------------------------------------
# ABA: DASHBOARD & CUSTOS
# -------------------------------------------------------------
with tab_custos:
    st.subheader("💰 Análise de Custos e Combustível")
    conn = sqlite3.connect(DB_FILE)
    
    cfg = pd.read_sql_query("SELECT * FROM config_frota WHERE id=1", conn).iloc[0]
    
    st.markdown("#### ⚙️ Parâmetros do Carro da Empresa")
    cc1, cc2, cc3 = st.columns(3)
    novo_consumo = cc1.number_input("Consumo (km/L)", value=float(cfg['consumo']), step=0.1)
    novo_preco = cc2.number_input("Gasolina (R$/L)", value=float(cfg['preco_gasolina']), step=0.01)
    novo_fixo = cc3.number_input("Custo Fixo Diário (R$)", value=float(cfg['custo_fixo']), step=1.0)
    
    if st.button("Salvar Parâmetros"):
        conn.execute("UPDATE config_frota SET consumo=?, preco_gasolina=?, custo_fixo=? WHERE id=1", (novo_consumo, novo_preco, novo_fixo))
        conn.commit()
        st.success("✅ Parâmetros atualizados!")
    
    st.divider()
    
    if st.session_state.get('rota_gerada', False):
        km_total = st.session_state['total_km']
        custo_strada = (km_total / novo_consumo) * novo_preco + novo_fixo
        custo_uber = (km_total * 2.20) + 8.00  # Estimativa Uber
        custo_proprio = km_total * 1.50 # Terceirizado
        
        st.markdown(f"#### 📊 Comparativo da Rota Atual ({km_total:.1f} km)")
        met1, met2, met3 = st.columns(3)
        met1.metric("Carro da Empresa (Combustível)", f"R$ {custo_strada:.2f}", f"R$ {novo_preco/novo_consumo:.2f} / km", delta_color="off")
        met2.metric("Veículo Próprio (R$ 1,50/km)", f"R$ {custo_proprio:.2f}", "R$ 1.50 / km", delta_color="off")
        met3.metric("Terceirizar tudo no Uber", f"R$ {custo_uber:.2f}", "R$ 2.20 / km", delta_color="inverse")
        st.divider()
        
    st.markdown("#### ⛽ Diário de Bordo da Empresa")
    with st.expander("➕ Adicionar Novo Recibo (Gasolina / Manutenção)", expanded=False):
        f_data = st.date_input("Data do Recibo")
        fc1, fc2, fc3 = st.columns(3)
        f_litros = fc1.number_input("Litros Abastecidos", min_value=0.0, step=0.1)
        f_valor = fc2.number_input("Preço da Gasolina (R$/L)", value=novo_preco, step=0.01)
        f_manut = fc3.number_input("Gastos c/ Manutenção (R$)", min_value=0.0, step=10.0)
        f_obs = st.text_input("Observação (Ex: Troca de óleo, pneu furado)")
        
        if st.button("Lançar Despesa"):
            conn.execute("INSERT INTO abastecimentos (data, litros, valor_litro, manutencao, obs) VALUES (?, ?, ?, ?, ?)", 
                         (f_data.strftime("%d/%m/%Y"), f_litros, f_valor, f_manut, f_obs))
            conn.commit()
            st.success("Lançamento salvo com sucesso!")

    df_abastec = pd.read_sql_query("SELECT * FROM abastecimentos ORDER BY id DESC", conn)
    if not df_abastec.empty:
        df_abastec['Custo Gasolina'] = df_abastec['litros'] * df_abastec['valor_litro']
        df_abastec['Custo Total'] = df_abastec['Custo Gasolina'] + df_abastec['manutencao']
        st.dataframe(df_abastec[['data', 'litros', 'valor_litro', 'Custo Gasolina', 'manutencao', 'Custo Total', 'obs']], use_container_width=True)
        
        tot_litros = df_abastec['litros'].sum()
        tot_gas = df_abastec['Custo Gasolina'].sum()
        tot_man = df_abastec['manutencao'].sum()
        st.info(f"**Acumulado Histórico:** ⛽ {tot_litros:.1f}L abastecidos | 💰 R$ {tot_gas:.2f} em Gasolina | 🔧 R$ {tot_man:.2f} em Manutenção | **Custo Total: R$ {tot_gas + tot_man:.2f}**")

    conn.close()

# -------------------------------------------------------------
# ABA: TEAMS
# -------------------------------------------------------------
with tab_teams:
    st.subheader("💬 Configuração dos Supervisores no Teams")
    st.write("Cole aqui o link do Webhook gerado no Microsoft Teams para cada supervisor. Quando uma entrega for concluída, o alerta vai direto para ele!")
    
    conn = sqlite3.connect(DB_FILE)
    df_teams = pd.read_sql_query("SELECT * FROM webhooks_teams ORDER BY setor", conn)
    
    for index, row in df_teams.iterrows():
        setor = row['setor']
        nova_url = st.text_input(f"👤 {setor}", value=row['url'], key=f"tms_{setor}")
        if st.button(f"Salvar URL de {setor}"):
            conn.execute("UPDATE webhooks_teams SET url=? WHERE setor=?", (nova_url, setor))
            conn.commit()
            st.success(f"Link de '{setor}' atualizado!")
            
    conn.close()

# -------------------------------------------------------------
# ABA: ROTEIRO E MAPA
# -------------------------------------------------------------
with tab_roteiro:
    df_ativos = st.session_state.demandas[st.session_state.demandas["Uber"] == False]
    df_uber = st.session_state.demandas[st.session_state.demandas["Uber"] == True]
    
    if st.button("🚀 Calcular Rota Otimizada", type="primary"):
        with st.spinner("Analisando grupamentos e traçando rota anti zigue-zague..."):
            
            conn = sqlite3.connect(DB_FILE)
            pontos_necessarios = set([ponto_saida] + df_ativos["Origem"].tolist() + df_ativos["Destino"].tolist())
            locais_dict = {}
            for p in pontos_necessarios:
                res = conn.execute("SELECT lat, lon FROM locais WHERE apelido = ?", (p,)).fetchone()
                if res and res[0] is not None:
                    locais_dict[p] = (res[0], res[1])
            conn.close()
            
            faltando = [p for p in pontos_necessarios if p not in locais_dict]
            if faltando:
                st.warning(f"⚠️ Os seguintes locais precisam de endereço/GPS na Aba 2: **{', '.join(faltando)}**")
                st.stop()

            pontos_unicos = list(locais_dict.keys())
            coords = [locais_dict[p] for p in pontos_unicos]
            dist_matrix, dur_matrix = calcular_matriz_rotas(coords)

            def get_dist_dur(p1, p2):
                if p1 == p2: return 0.0, 0.0
                i, j = pontos_unicos.index(p1), pontos_unicos.index(p2)
                return dist_matrix[i][j], dur_matrix[i][j]

            unpicked = df_ativos.to_dict('records')
            carrying = []
            current = ponto_saida
            route_steps = []
            total_km = 0.0
            current_time = 7.5 * 60
            lunch_taken = False

            while unpicked or carrying:
                candidates = set([t['Origem'] for t in unpicked] + [t['Destino'] for t in carrying])
                if not candidates: break

                best_point = None
                min_score = float('inf')
                best_dist, best_dur = 0, 0
                
                destinos_no_carro = set(t['Destino'] for t in carrying)

                for p in candidates:
                    d, dur = get_dist_dur(current, p)
                    is_dropoff = any(t['Destino'] == p for t in carrying)
                    is_pickup = any(t['Origem'] == p for t in unpicked)
                    urgency = max([t['Peso'] for t in unpicked if t['Origem'] == p] + [1])
                    
                    pendentes_para_p = sum(1 for t in unpicked if t['Destino'] == p)
                    prio = 1.0
                    
                    if is_dropoff:
                        prio = 2.0
                        if pendentes_para_p > 0: prio = 0.1 
                    
                    if is_pickup:
                        destinos_desta_coleta = set(t['Destino'] for t in unpicked if t['Origem'] == p)
                        if destinos_desta_coleta.intersection(destinos_no_carro):
                            prio *= 3.0
                        else:
                            prio *= 1.5

                    if "Urgências" in estrategia: prio *= (urgency ** 2)
                    elif "Descarregar" in estrategia and is_dropoff: prio *= 5.0
                    elif "Economia" in estrategia:
                        if is_dropoff and pendentes_para_p > 0: prio = 0.05
                            
                    if prio == 0: prio = 0.001
                    score = (d + (dur * 0.1)) / prio
                    
                    if d < 0.1: score = -1.0

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
            
            st.session_state['rota_gerada'] = True
            st.session_state['route_steps'] = route_steps
            st.session_state['total_km'] = total_km
            st.session_state['locais_dict'] = locais_dict
            st.session_state['p_saida'] = ponto_saida
            st.session_state['df_uber_final'] = df_uber

    if st.session_state.get('rota_gerada', False):
        route_steps = st.session_state['route_steps']
        total_km = st.session_state['total_km']
        locais_dict = st.session_state['locais_dict']
        p_saida = st.session_state['p_saida']
        df_uber_final = st.session_state['df_uber_final']
        
        # CÁLCULO DINÂMICO DE CUSTO BASEADO NO VEÍCULO SELECIONADO
        if "Empresa" in veiculo_selecionado:
            conn = sqlite3.connect(DB_FILE)
            cfg = pd.read_sql_query("SELECT consumo, preco_gasolina FROM config_frota WHERE id=1", conn).iloc[0]
            conn.close()
            custo_rota = (total_km / float(cfg['consumo'])) * float(cfg['preco_gasolina'])
            desc_custo = "Custo Aprox. (Combustível Empresa)"
        else:
            custo_rota = total_km * 1.50
            desc_custo = "Custo (R$ 1,50/km)"

        col_esq, col_dir = st.columns([1.2, 0.8])

        with col_esq:
            st.subheader("📋 Roteiro de Viagem do Davi")
            texto_whatsapp = f"🚚 *ROTEIRO DE LOGÍSTICA - DAVI*\n🏁 Saída: {p_saida} (07:30)\n🚗 Veículo: {veiculo_selecionado}\n\n"
            
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

            # Botão de Envio Geral (Opcional)
            conn = sqlite3.connect(DB_FILE)
            url_geral = conn.execute("SELECT url FROM webhooks_teams WHERE setor='Geral / Logística'").fetchone()
            conn.close()
            
            if url_geral and url_geral[0]:
                if st.button("📢 Mandar Roteiro Completo no Grupo Geral (Teams)", use_container_width=True):
                    resumo = f"O roteiro do Davi já está pronto.\n\n**Total Paradas:** {num_parada-1}\n**Quilometragem Estimada:** {total_km:.1f} km"
                    if disparar_teams(url_geral[0], "🚚 Roteiro Diário Liberado!", resumo):
                        st.success("✅ Roteiro enviado para o grupo Geral!")

            st.success(f"🛣️ **Total Rodado:** {total_km:.1f} km | 💰 **{desc_custo}:** R$ {custo_rota:.2f}")
            texto_whatsapp += f"🛣️ Total: {total_km:.1f} km | {desc_custo}: R$ {custo_rota:.2f}\n"

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
            
            if p_saida in locais_dict:
                lat_s, lon_s = locais_dict[p_saida]
                path_points.append([lat_s, lon_s])
                folium.Marker(
                    [lat_s, lon_s], popup=f"Saída: {p_saida}", tooltip="Ponto de Saída",
                    icon=folium.DivIcon(html=f'''<div style="background-color: #3b82f6; color: white; border: 2px solid white; border-radius: 50%; width: 30px; height: 30px; display: flex; justify-content: center; align-items: center; font-weight: bold; box-shadow: 2px 2px 5px rgba(0,0,0,0.5); font-family: sans-serif; font-size: 14px;">0</div>''')
                ).add_to(m)

            for step in route_steps:
                if step.get('destino') and step['destino'] in locais_dict:
                    lat, lon = locais_dict[step['destino']]
                    path_points.append([lat, lon])
                    
                    if step['type'] == 'lunch': continue
                    if step['type'] == 'return':
                        bg_color, num_str, tt_text = "#3b82f6", "🏁", f"Retorno: {step['destino']}"
                    else:
                        acoes = [a[0] for a in step.get('actions', [])]
                        bg_color = "#a855f7" if "COLETAR" in acoes and "ENTREGAR" in acoes else "#f59e0b" if "COLETAR" in acoes else "#22c55e"
                        num_str, tt_text = str(p_num), f"Parada {p_num}: {step['destino']}"
                    
                    folium.Marker(
                        [lat, lon], popup=f"{step['destino']}", tooltip=tt_text,
                        icon=folium.DivIcon(html=f'''<div style="background-color: {bg_color}; color: white; border: 2px solid white; border-radius: 50%; width: 30px; height: 30px; display: flex; justify-content: center; align-items: center; font-weight: bold; box-shadow: 2px 2px 5px rgba(0,0,0,0.5); font-family: sans-serif; font-size: 14px;">{num_str}</div>''')
                    ).add_to(m)
                    if step['type'] != "return": p_num += 1

            if len(path_points) > 1:
                folium.PolyLine(path_points, color="#2563eb", weight=4, opacity=0.8).add_to(m)
                m.fit_bounds(path_points)

            st_folium(m, width=450, height=550, returned_objects=[])
            st.markdown("<div style='text-align: center; font-size: 14px; margin-top: 10px;'><b>Legenda:</b> 🔵 Saída/Retorno | 🟡 Coleta | 🟢 Entrega | 🟣 Ambos</div>", unsafe_allow_html=True)
