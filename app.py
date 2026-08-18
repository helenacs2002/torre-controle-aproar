import os
import re
import json
import math
import sqlite3
import time
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from html import escape as html_escape
from html.parser import HTMLParser
from zoneinfo import ZoneInfo
import pandas as pd
import requests
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
RASTREADOR_LOGIN_URLS = [
    "https://portal.protegeexpress.com.br/sistema/login.aspx",
    "http://portal.protegeexpress.com.br/sistema/login.aspx",
]
RASTREADOR_VEICULOS_PADRAO = "007046861,807289138"
DB_FILE = "enderecos_logistica.db"
VELOCIDADE_MEDIA_KMH = 25.0
FUSO_LOCAL = ZoneInfo("America/Fortaleza")
INICIO_EXPEDIENTE_MIN = 7 * 60
INICIO_ROTA_MIN = 7 * 60 + 30  # Ajustado para 07:30
FIM_EXPEDIENTE_MIN = 17 * 60
INICIO_ALMOCO_MIN = 12 * 60
DURACAO_ALMOCO_MIN = 60

COLUNAS_DEMANDAS = [
    "id", "Obra", "Origem", "Destino", "Materiais", "Urgência", "Peso",
    "Tempo_Coleta", "Tempo_Entrega", "Supervisor"
]

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

TEAMS_SECRET_KEYS = {
    "Luis Eduardo Rodrigues": "luis_eduardo",
    "Victor Bezerra": "victor_bezerra",
    "Gustavo Souza": "gustavo_souza",
    "Neto Porto": "neto_porto",
    "Soares Junior": "soares_junior",
    "Joel Lima": "joel_lima",
    "Sede / Logística": "sede_logistica",
    "Geral / Logística": "geral_logistica",
}

TEAMS_GRUPOS_UNIDADE = [
    ("COMPRAS X ORÇAMENTOS", "geral_logistica", "Geral / Logística"),
    ("MARACANAÚ X COMPRAS", "maracanau", "MARACANAÚ"),
    ("HORIZONTE X COMPRAS", "horizonte", "HORIZONTE"),
    ("BARRA X COMPRAS", "barra", "BARRA"),
    ("CASA DA INDÚSTRIA X COMPRAS", "casa_industria", "CASA DA INDÚSTRIA"),
    ("CENTRO X COMPRAS", "centro", "CENTRO"),
    ("SEBRAE X COMPRAS", "sebrae", "SEBRAE"),
    ("MUSEU DA IND X COMPRAS", "museu", "MUSEU"),
    ("UNIFOR X COMPRAS", "unifor", "UNIFOR"),
    ("SEDE/PARANGABA X COMPRAS", "sede_parangaba", "PARANGABA"),
]

LOCAL_BASE_ENDERECO = (
    "Rua Professor Mário Rocha, 84 - Joaquim Távora, "
    "Fortaleza - CE, 60120-200"
)
LOCAL_BASE_COORDS = (-3.752270016704, -38.51537298342)
ALIASES_LOCAL_BASE = {"ALMOXARIFADO", "ESCRITÓRIO"}

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
    ("ESCRITÓRIO", LOCAL_BASE_ENDERECO),
    ("ALMOXARIFADO", LOCAL_BASE_ENDERECO),
    ("ESPAÇO SMART", "BR-116, 9370 - Barroso, Fortaleza - CE, 60862-735"),
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
    c.execute('''CREATE TABLE IF NOT EXISTS locais_removidos (apelido TEXT PRIMARY KEY)''')
    c.execute('''CREATE TABLE IF NOT EXISTS config_frota (id INTEGER PRIMARY KEY, consumo REAL, preco_gasolina REAL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS abastecimentos (id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT, litros REAL, valor_litro REAL, manutencao REAL, obs TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS registro_km (id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT, km REAL, obs TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS historico_concluidos (id TEXT PRIMARY KEY, obra TEXT, origem TEXT, destino TEXT, materiais TEXT, data_conclusao TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS webhooks_teams (setor TEXT PRIMARY KEY, url TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS config_trello (id INTEGER PRIMARY KEY, api_key TEXT, token TEXT, id_lista_concluida TEXT)''')
    
    c.execute("INSERT OR IGNORE INTO config_frota (id, consumo, preco_gasolina) VALUES (1, 11.5, 5.90)")
    c.execute("INSERT OR IGNORE INTO config_trello (id, api_key, token, id_lista_concluida) VALUES (1, '', '', '')")
    c.execute("INSERT OR IGNORE INTO webhooks_teams (setor, url) VALUES ('Geral / Logística', '')")
    
    for sup in set(SUPERVISORES_MAP.values()):
        c.execute("INSERT OR IGNORE INTO webhooks_teams (setor, url) VALUES (?, '')", (sup,))
    
    for apelido, end in ENDERECOS_PADRAO:
        c.execute(
            "INSERT OR IGNORE INTO locais (apelido, endereco) "
            "SELECT ?, ? WHERE NOT EXISTS ("
            "SELECT 1 FROM locais_removidos WHERE apelido = ?)",
            (apelido, end, apelido)
        )

    c.execute(
        "DELETE FROM locais WHERE UPPER(TRIM(apelido)) = 'DESCONHECIDO'"
    )

    for alias in ALIASES_LOCAL_BASE:
        c.execute(
            "INSERT OR REPLACE INTO locais "
            "(apelido, endereco, lat, lon) VALUES (?, ?, ?, ?)",
            (
                alias,
                LOCAL_BASE_ENDERECO,
                LOCAL_BASE_COORDS[0],
                LOCAL_BASE_COORDS[1]
            )
        )
    conn.commit()
    conn.close()

inicializar_bd()

# =====================================================================
# FUNÇÕES DE INTEGRAÇÃO (TEAMS, TRELLO E MAPAS)
# =====================================================================
def identificar_grupo_teams(destino, obra=""):
    texto = normalizar_local(f"{obra} {destino}")
    regras = [
        (("GERAL / LOGÍSTICA",), "geral_logistica"),
        (("CASA DA INDÚSTRIA", "FIEC"), "casa_industria"),
        (("MARACANAÚ",), "maracanau"),
        (("HORIZONTE",), "horizonte"),
        (("SEBRAE",), "sebrae"),
        (("MUSEU",), "museu"),
        (("BARRA",), "barra"),
        (("CENTRO", "NR SAÚDE"), "centro"),
        (("UNIFOR",), "unifor"),
        (("PARANGABA", "ESCRITÓRIO"), "sede_parangaba"),
    ]
    for termos, chave in regras:
        if any(termo in texto for termo in termos):
            return chave
    return ""

def obter_webhook_teams(setor, supervisor=None, obra=""):
    chave_unidade = identificar_grupo_teams(setor, obra)
    if chave_unidade:
        try:
            url_secret = str(
                st.secrets["teams_unidades"].get(chave_unidade, "")
            ).strip()
            if url_secret:
                return url_secret, "Secrets — grupo da unidade"
        except Exception:
            pass

    nome_supervisor = supervisor or setor
    chave_supervisor = TEAMS_SECRET_KEYS.get(nome_supervisor)
    if chave_supervisor:
        try:
            url_secret = str(
                st.secrets["teams"].get(chave_supervisor, "")
            ).strip()
            if url_secret:
                return url_secret, "Secrets — cadastro anterior"
        except Exception:
            pass

    try:
        conn = sqlite3.connect(DB_FILE)
        registro = conn.execute(
            "SELECT url FROM webhooks_teams WHERE setor = ?", (nome_supervisor,)
        ).fetchone()
        conn.close()
        if registro and registro[0]:
            return registro[0].strip(), "Banco local"
    except Exception:
        pass

    return "", "Não configurado"

def disparar_teams(webhook_url, titulo, mensagem):
    if not webhook_url or not webhook_url.lower().startswith("https://"):
        return False, "O link precisa ser um webhook HTTPS do Teams Workflows."

    payload = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "contentUrl": None,
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.2",
                    "body": [
                        {
                            "type": "TextBlock",
                            "text": titulo,
                            "size": "Medium",
                            "weight": "Bolder",
                            "wrap": True,
                        },
                        {
                            "type": "TextBlock",
                            "text": mensagem,
                            "wrap": True,
                            "spacing": "Medium",
                        },
                    ],
                },
            }
        ],
    }
    ultimo_erro = ""

    for tentativa in range(3):
        try:
            resposta = requests.post(webhook_url, json=payload, timeout=15)
            if 200 <= resposta.status_code < 300:
                return True, "Mensagem aceita pelo Teams."

            ultimo_erro = f"Teams respondeu com o código {resposta.status_code}."
            if resposta.status_code != 429 and resposta.status_code < 500:
                break
        except requests.RequestException:
            ultimo_erro = "Não foi possível alcançar o Teams."

        if tentativa < 2:
            time.sleep(1 + tentativa)

    return False, ultimo_erro or "Falha desconhecida ao enviar a mensagem."

def mover_cartao_trello(card_id):
    conn = sqlite3.connect(DB_FILE)
    cfg = conn.execute("SELECT api_key, token, id_lista_concluida FROM config_trello WHERE id=1").fetchone()
    conn.close()
    
    if not cfg or not cfg[0] or not cfg[1] or not cfg[2]:
        return False, "Chaves da API ou Lista de Destino não configuradas na aba de Integrações."
        
    url = f"https://api.trello.com/1/cards/{card_id}?idList={cfg[2]}&key={cfg[0]}&token={cfg[1]}"
    try:
        req = urllib.request.Request(url, method='PUT')
        urllib.request.urlopen(req, timeout=5)
        return True, "Movido com sucesso!"
    except Exception as e:
        return False, f"Erro de comunicação com o Trello: {e}"

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

def canonicalizar_ponto_rota(nome):
    texto = normalizar_local(str(nome or ""))
    texto = re.sub(r"[\\*_`]+", "", texto).strip(" :-\t\r\n")
    if texto in ALIASES_LOCAL_BASE:
        return "ESCRITÓRIO"
    return texto

def garantir_gps_local_base(conn):
    coordenadas = None
    for alias in ("ESCRITÓRIO", "ALMOXARIFADO"):
        registro = conn.execute(
            "SELECT lat, lon FROM locais WHERE apelido = ?",
            (alias,)
        ).fetchone()
        if registro and registro[0] is not None and registro[1] is not None:
            coordenadas = (float(registro[0]), float(registro[1]))
            break

    if coordenadas is None:
        coordenadas = LOCAL_BASE_COORDS

    if coordenadas is not None:
        lat, lon = coordenadas
        for alias in ALIASES_LOCAL_BASE:
            conn.execute(
                "INSERT OR REPLACE INTO locais "
                "(apelido, endereco, lat, lon) VALUES (?, ?, ?, ?)",
                (alias, LOCAL_BASE_ENDERECO, lat, lon)
            )
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

def buscar_geometria_rota(coords_ordenadas):
    coords_limpas = []
    for coord in coords_ordenadas:
        if not coords_limpas or coord != coords_limpas[-1]:
            coords_limpas.append(coord)

    if len(coords_limpas) < 2:
        return [[lat, lon] for lat, lon in coords_limpas], False

    try:
        coords_str = ";".join(
            f"{lon},{lat}" for lat, lon in coords_limpas
        )
        url = (
            "https://router.project-osrm.org/route/v1/driving/"
            f"{coords_str}?overview=full&geometries=geojson&steps=false"
        )
        req = urllib.request.Request(
            url,
            headers={'User-Agent': 'AproarLogisticsWeb/1.0'}
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            res = json.loads(response.read())
        if res.get("code") == "Ok" and res.get("routes"):
            coordenadas = res["routes"][0]["geometry"]["coordinates"]
            return [[lat, lon] for lon, lat in coordenadas], True
    except Exception:
        pass

    return [[lat, lon] for lat, lon in coords_limpas], False

def normalizar_local(nome):
    if not nome: return ""
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

    origem, destino = "", ""
    materiais = "Ver Trello"
    
    if texto:
        texto_limpo = re.sub(r'[*_`]+', '', texto)

        mo = re.search(r'(?i)(?:coletar|pegar|retirar|buscar)\s+(?:no|na|em|o|a|ao|à)\s+(.*?)(?:\:|\n|$)', texto_limpo)
        if mo: origem = normalizar_local(mo.group(1))

        md = re.search(r'(?i)(?:e\s+)?(?:levar|entreg(?:ar|á-lo|á-la|á-los|á-las)|devolver|encaminhar|transportar|deixar)\s+(?:para|no|na|ao|à|aos|às)\s+(?:o|a|os|as)?\s*(.*?)(?:\:|\n|$|\.)', texto_limpo)
        if md: destino = normalizar_local(md.group(1))
        
        if mo and md:
            start_idx = mo.end()
            end_idx = md.start()
            if start_idx < end_idx:
                mat_text = texto_limpo[start_idx:end_idx].strip()
                mat_text = re.sub(r'\*+', '', mat_text)
                linhas_limpas = [l.strip().lstrip('-').strip() for l in mat_text.split('\n') if len(l.strip()) >= 2 and l.lower() not in ['e', 'e:', 'e -', 'e,', 'para', 'levar para'] and not l.startswith(('![', '➡️', '→'))]
                if linhas_limpas: materiais = " | ".join(linhas_limpas)

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
        diff = (due_date - datetime.now(FUSO_LOCAL).date()).days
        if diff < 0: return 5, "VENCIDA"
        elif diff == 0: return 4, "HOJE"
        elif diff <= 2: return 3, f"Em {diff} dias"
        else: return 1, "Futuro"
    except: return 1, "Sem Prazo"

def converter_data_trello(valor):
    if not valor:
        return None
    data = datetime.fromisoformat(valor.replace("Z", "+00:00"))
    if data.tzinfo is None:
        data = data.replace(tzinfo=timezone.utc)
    return data.astimezone(FUSO_LOCAL)

def lista_esta_concluida(nome_lista):
    nome = normalizar_local(nome_lista or "")
    return "CONCLU" in nome or "ENTREG" in nome

def encontrar_conclusao_de_hoje(card_id, acoes):
    hoje = datetime.now(FUSO_LOCAL).date()
    conclusoes = []

    for acao in acoes:
        if acao.get("type") != "updateCard":
            continue

        dados = acao.get("data", {})
        cartao = dados.get("card", {})
        lista_antes = dados.get("listBefore", {}).get("name", "")
        lista_depois = dados.get("listAfter", {}).get("name", "")

        if cartao.get("id") != card_id:
            continue
        if not lista_esta_concluida(lista_depois):
            continue
        if lista_esta_concluida(lista_antes):
            continue

        try:
            momento = converter_data_trello(acao.get("date"))
        except (TypeError, ValueError):
            continue

        if momento and momento.date() == hoje:
            conclusoes.append(momento)

    return max(conclusoes) if conclusoes else None

def prazo_era_hoje_ou_atrasado(due_str, momento_conclusao):
    if not due_str or not momento_conclusao:
        return False
    try:
        prazo = converter_data_trello(due_str)
        return prazo.date() <= momento_conclusao.date()
    except (TypeError, ValueError):
        return False

def format_time(minutes):
    total = int(round(minutes))
    return f"{total // 60:02d}:{total % 60:02d}"

def formatar_duracao(minutes):
    total = max(0, int(round(minutes)))
    horas, minutos = divmod(total, 60)
    if horas and minutos:
        return f"{horas}h{minutos:02d}"
    if horas:
        return f"{horas}h"
    return f"{minutos}min"

# =====================================================================
# INTEGRAÇÃO COM O RASTREADOR PROTEGE EXPRESS
# =====================================================================
class FormularioLoginParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.action = None
        self.inputs = []

    def handle_starttag(self, tag, attrs):
        atributos = {k: (v or "") for k, v in attrs}
        if tag.lower() == "form" and self.action is None:
            self.action = atributos.get("action", "")
        elif tag.lower() == "input":
            self.inputs.append(atributos)

def _escolher_campo(campos, palavras):
    if not campos:
        return None
    for campo in campos:
        identificador = f"{campo.get('name', '')} {campo.get('id', '')}".lower()
        if any(palavra in identificador for palavra in palavras):
            return campo
    return campos[0]

def _montar_formulario_login(html, usuario, senha):
    parser = FormularioLoginParser()
    parser.feed(html)

    campos_com_nome = [c for c in parser.inputs if c.get("name")]
    campos_usuario = [
        c for c in campos_com_nome
        if c.get("type", "text").lower() in ("text", "email")
    ]
    campos_senha = [
        c for c in campos_com_nome if c.get("type", "").lower() == "password"
    ]

    campo_usuario = _escolher_campo(
        campos_usuario, ("usu", "user", "login", "email")
    )
    campo_senha = _escolher_campo(campos_senha, ("senha", "password", "pass"))

    if not campo_usuario or not campo_senha:
        raise RuntimeError("Não foi possível identificar os campos de acesso do portal.")

    dados = {
        c["name"]: c.get("value", "")
        for c in campos_com_nome
        if c.get("type", "").lower() == "hidden"
    }
    dados[campo_usuario["name"]] = usuario
    dados[campo_senha["name"]] = senha

    botoes = [
        c for c in campos_com_nome
        if c.get("type", "").lower() in ("submit", "button")
    ]
    if botoes:
        botao = _escolher_campo(botoes, ("entr", "acess", "login", "logar"))
        dados[botao["name"]] = botao.get("value", "Entrar")

    imagens = [
        c for c in campos_com_nome if c.get("type", "").lower() == "image"
    ]
    if imagens:
        nome = imagens[0]["name"]
        dados[f"{nome}.x"] = "10"
        dados[f"{nome}.y"] = "10"

    return parser.action, dados

def _parsear_resposta_rastreador(texto):
    posicoes = []
    for registro in texto.replace("\r", "").split(";"):
        registro = registro.strip()
        if not registro:
            continue

        partes = registro.split("|", 8)
        if len(partes) < 9:
            continue

        try:
            latitude = float(partes[3])
            longitude = float(partes[4])
            velocidade = float(partes[5].replace(",", "."))
        except (TypeError, ValueError):
            continue

        codigo_status = partes[6].strip().upper()
        situacao = {
            "P": "Parado",
            "M": "Em movimento",
            "L": "Ligado",
            "D": "Desligado",
        }.get(codigo_status, codigo_status or "Não informado")

        posicoes.append({
            "ID": partes[0].strip(),
            "Placa": partes[1].strip(),
            "Última atualização": partes[2].strip(),
            "Latitude": latitude,
            "Longitude": longitude,
            "Velocidade (km/h)": velocidade,
            "Situação": situacao,
            "Código": codigo_status,
            "Ícone": partes[7].strip(),
            "Endereço": partes[8].strip(),
        })

    return posicoes

def consultar_posicoes_protege(sessao, pagina_atual, veiculos):
    url = urllib.parse.urljoin(pagina_atual, "consultaajax_all.aspx")
    resposta = sessao.post(
        url,
        params={"p1": veiculos},
        headers={
            "X-Requested-With": "XMLHttpRequest",
            "Referer": pagina_atual,
        },
        timeout=20,
    )
    resposta.raise_for_status()
    posicoes = _parsear_resposta_rastreador(resposta.text)
    if not posicoes:
        raise RuntimeError("O portal não devolveu posições. A sessão pode ter expirado.")
    return posicoes

def autenticar_protege(usuario, senha, veiculos):
    ultimo_erro = None

    for login_url in RASTREADOR_LOGIN_URLS:
        try:
            sessao = requests.Session()
            sessao.headers.update({
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/151.0 Safari/537.36"
                )
            })

            pagina_login = sessao.get(login_url, timeout=20)
            pagina_login.raise_for_status()
            action, dados = _montar_formulario_login(
                pagina_login.text, usuario, senha
            )
            url_post = urllib.parse.urljoin(
                pagina_login.url, action or pagina_login.url
            )
            resposta_login = sessao.post(
                url_post,
                data=dados,
                timeout=20,
                allow_redirects=True,
            )
            resposta_login.raise_for_status()

            pagina_atual = resposta_login.url
            posicoes = consultar_posicoes_protege(
                sessao, pagina_atual, veiculos
            )
            return sessao, pagina_atual, posicoes
        except Exception as erro:
            ultimo_erro = erro

    raise RuntimeError(
        "Não foi possível autenticar ou consultar o rastreador. "
        "Confira usuário, senha e identificadores dos veículos."
    ) from ultimo_erro

def carregar_config_protege():
    try:
        config = st.secrets["protege"]
        usuario = str(config.get("usuario", "")).strip()
        senha = str(config.get("senha", "")).strip()
        veiculos = config.get("veiculos", RASTREADOR_VEICULOS_PADRAO)
        if isinstance(veiculos, (list, tuple)):
            veiculos = ",".join(str(v).strip() for v in veiculos)
        else:
            veiculos = str(veiculos).strip()
        return usuario, senha, veiculos
    except Exception:
        return "", "", RASTREADOR_VEICULOS_PADRAO

# =====================================================================
# INTERFACE STREAMLIT
# =====================================================================
st.title("🚚 LOGÍSTICA APROAR - Torre de Controle")

if "demandas" not in st.session_state:
    st.session_state.demandas = pd.DataFrame(columns=COLUNAS_DEMANDAS)

# Painel Lateral
with st.sidebar:
    st.header("⚙️ Painel de Operações")
    st.caption("Versão 18.08.2026-r21 (Auto-Sync & Timing)")
    
    if st.button("🔄 Sincronizar com Trello", use_container_width=True, type="primary"):
        with st.spinner("Puxando demandas ao vivo..."):
            try:
                req = urllib.request.Request(TRELLO_JSON_URL, headers={'User-Agent': 'AproarLogisticsWeb/1.0'})
                with urllib.request.urlopen(req, timeout=60) as response:
                    data = json.loads(response.read())
                
                st.session_state['trello_lists_raw'] = data.get('lists', [])
                
                trello_lists = {l['id']: l['name'] for l in data.get('lists', []) if not l.get('closed')}
                cards = data.get('cards', [])
                acoes = data.get('actions', [])
                
                demandas_extraidas = []
                data_hoje = datetime.now(FUSO_LOCAL).strftime("%d/%m/%Y")
                ids_concluidos_validos_hoje = set()
                
                conn = sqlite3.connect(DB_FILE)
                df_antigo = st.session_state.demandas
                
                for c in cards:
                    if c.get('closed'): continue
                    nome_lista = trello_lists.get(c.get('idList', ''), '').upper()
                    
                    short_name, origem, destino, materiais = extrair_dados_completos(c.get('desc', ''), c.get('name', ''))
                    peso, status_prazo = classificar_prioridade(c.get('due'))
                    supervisor = SUPERVISORES_MAP.get(destino, "Sede / Logística")
                    
                    if lista_esta_concluida(nome_lista):
                        momento_conclusao = encontrar_conclusao_de_hoje(c['id'], acoes)
                        if prazo_era_hoje_ou_atrasado(c.get('due'), momento_conclusao):
                            data_conclusao = momento_conclusao.strftime("%d/%m/%Y")
                            conn.execute(
                                "INSERT OR REPLACE INTO historico_concluidos "
                                "(id, obra, origem, destino, materiais, data_conclusao) "
                                "VALUES (?, ?, ?, ?, ?, ?)",
                                (c['id'], short_name, origem, destino, materiais, data_conclusao)
                            )
                            ids_concluidos_validos_hoje.add(c['id'])
                        continue
                    
                    endereco_card = encontrar_endereco_na_descricao(c.get('desc', ''))
                    if endereco_card:
                        lat, lon = buscar_coordenadas(endereco_card)
                        if lat:
                            if origem and origem not in UNIDADES_PROPRIAS:
                                res = conn.execute("SELECT lat FROM locais WHERE apelido = ?", (origem,)).fetchone()
                                if not res or res[0] is None:
                                    conn.execute("INSERT OR REPLACE INTO locais (apelido, endereco, lat, lon) VALUES (?, ?, ?, ?)", (origem, endereco_card, lat, lon))
                            if destino and destino not in UNIDADES_PROPRIAS:
                                res = conn.execute("SELECT lat FROM locais WHERE apelido = ?", (destino,)).fetchone()
                                if not res or res[0] is None:
                                    conn.execute("INSERT OR REPLACE INTO locais (apelido, endereco, lat, lon) VALUES (?, ?, ?, ?)", (destino, endereco_card, lat, lon))
                    
                    tc_val = 20 if origem not in UNIDADES_PROPRIAS else 10
                    te_val = 10
                    
                    if not df_antigo.empty and c['id'] in df_antigo['id'].values:
                        linha_antiga = df_antigo[df_antigo['id'] == c['id']].iloc[0]
                        tc_val = linha_antiga['Tempo_Coleta']
                        te_val = linha_antiga['Tempo_Entrega']
                    
                    demandas_extraidas.append({
                        "id": c['id'], "Obra": short_name, "Origem": origem, "Destino": destino,
                        "Materiais": materiais, "Urgência": status_prazo, "Peso": peso,
                        "Tempo_Coleta": tc_val, "Tempo_Entrega": te_val, "Supervisor": supervisor
                    })

                if acoes:
                    registros_de_hoje = conn.execute(
                        "SELECT id FROM historico_concluidos WHERE data_conclusao = ?",
                        (data_hoje,)
                    ).fetchall()
                    for (card_id_salvo,) in registros_de_hoje:
                        if card_id_salvo not in ids_concluidos_validos_hoje:
                            conn.execute(
                                "DELETE FROM historico_concluidos WHERE id = ?",
                                (card_id_salvo,)
                            )
                
                conn.commit()
                conn.close()
                
                st.session_state.demandas = pd.DataFrame(
                    demandas_extraidas,
                    columns=COLUNAS_DEMANDAS
                )
                if st.session_state.get('data_rota') != data_hoje:
                    st.session_state['rota_gerada'] = False
                st.success(
                    f"✅ Sincronizado! {len(ids_concluidos_validos_hoje)} demanda(s) "
                    "atrasada(s) ou de hoje foi(ram) concluída(s) hoje."
                )
                if not acoes:
                    st.warning(
                        "O Trello não enviou o histórico de movimentações. "
                        "Por segurança, nenhuma conclusão foi registrada como sendo de hoje."
                    )
            
            except Exception as e:
                st.error(f"⚠️ Erro ao acessar o Trello: {e}")
    
    st.divider()
    veiculo_selecionado = st.radio("🚗 Tipo de Custeio da Rota", ["Frota da Empresa (Calcula Gasolina)", "Carro Próprio/Frete (R$ 1,50/km)"])
    st.divider()
    
    ponto_saida = st.selectbox("🏁 Ponto de Saída", ["ESCRITÓRIO", "CASA DA INDÚSTRIA", "SENAI CENTRO", "MARACANAÚ"])
    estrategia = st.selectbox("🎯 Estratégia da Rota", ["⚖️ Equilibrada", "🏢 Foco em Descarregar", "⛽ Menor Distância", "🚨 Priorizar Urgências"])
    
    descricoes_estrategia = {
        "⚖️ Equilibrada": "Mescla urgência com proximidade para fazer a rota mais lógica e eficiente.",
        "🏢 Foco em Descarregar": "Prioriza entregar os materiais o quanto antes para esvaziar a caçamba do carro.",
        "⛽ Menor Distância": "Foca 100% no menor KM percorrido (Economia de combustível).",
        "🚨 Priorizar Urgências": "Foca 100% nas demandas Vencidas ou programadas para Hoje, rodando mais se necessário."
    }
    st.caption(f"ℹ️ *{descricoes_estrategia[estrategia]}*")
    
    retornar_base = st.checkbox("Retornar à base no fim do dia", value=True)

if st.session_state.demandas.empty:
    st.info("👋 Bem-vindo(a) à Torre de Controle! Clique no botão vermelho **'🔄 Sincronizar com Trello'** no menu lateral para puxar as demandas ao vivo e começar.")

# =====================================================================
# ABAS PRINCIPAIS
# =====================================================================
tab_roteiro, tab_rastreador, tab_demandas, tab_historico, tab_enderecos, tab_custos, tab_integ = st.tabs([
    "🗺️ Roteiro do Davi", 
    "📡 Rastreador ao Vivo",
    "📦 Demandas Ativas", 
    "📋 Histórico & Concluídos",
    "📍 Endereços",
    "💰 Dashboard & Custos",
    "⚙️ Integrações"
])

# -------------------------------------------------------------
# ABA: RASTREADOR AO VIVO
# -------------------------------------------------------------
with tab_rastreador:
    st.subheader("📡 Rastreador ao Vivo — Protege Express")
    st.caption(
        "Posições consultadas diretamente no portal e exibidas em mapa próprio. "
        "Atualização automática a cada 30 segundos."
    )

    usuario_protege, senha_protege, ids_veiculos = carregar_config_protege()

    if not usuario_protege or not senha_protege:
        st.warning(
            "Configure o usuário e a senha da Protege Express nos Secrets do "
            "aplicativo para ativar o login automático."
        )
    else:
        def exibir_painel_rastreador():
            col_status, col_atualizar = st.columns([4, 1])
            col_status.success("🔒 Login automático configurado")

            if col_atualizar.button(
                "🔄 Reconectar",
                key="btn_reconectar_protege",
                use_container_width=True
            ):
                st.session_state.pop("protege_sessao", None)
                st.session_state.pop("protege_pagina", None)

            try:
                sessao = st.session_state.get("protege_sessao")
                pagina = st.session_state.get("protege_pagina")

                if sessao is None or not pagina:
                    sessao, pagina, posicoes = autenticar_protege(
                        usuario_protege,
                        senha_protege,
                        ids_veiculos
                    )
                    st.session_state["protege_sessao"] = sessao
                    st.session_state["protege_pagina"] = pagina
                else:
                    try:
                        posicoes = consultar_posicoes_protege(
                            sessao, pagina, ids_veiculos
                        )
                    except Exception:
                        sessao, pagina, posicoes = autenticar_protege(
                            usuario_protege,
                            senha_protege,
                            ids_veiculos
                        )
                        st.session_state["protege_sessao"] = sessao
                        st.session_state["protege_pagina"] = pagina

                velocidades = [p["Velocidade (km/h)"] for p in posicoes]
                em_movimento = sum(1 for v in velocidades if v > 0)

                met1, met2, met3 = st.columns(3)
                met1.metric("Veículos localizados", len(posicoes))
                met2.metric("Em movimento", em_movimento)
                met3.metric(
                    "Última leitura",
                    datetime.now(FUSO_LOCAL).strftime("%H:%M:%S")
                )

                centro_lat = sum(p["Latitude"] for p in posicoes) / len(posicoes)
                centro_lon = sum(p["Longitude"] for p in posicoes) / len(posicoes)
                mapa = folium.Map(
                    location=[centro_lat, centro_lon],
                    zoom_start=11,
                    tiles="OpenStreetMap"
                )

                limites = []
                for posicao in posicoes:
                    em_rota = posicao["Velocidade (km/h)"] > 0
                    cor = "green" if em_rota else "red"
                    icone = "play" if em_rota else "stop"
                    limites.append([posicao["Latitude"], posicao["Longitude"]])

                    popup = (
                        f"<b>{posicao['Placa']}</b><br>"
                        f"{posicao['Situação']} — "
                        f"{posicao['Velocidade (km/h)']:.0f} km/h<br>"
                        f"Atualização: {posicao['Última atualização']}<br>"
                        f"{posicao['Endereço']}"
                    )
                    folium.Marker(
                        [posicao["Latitude"], posicao["Longitude"]],
                        popup=folium.Popup(popup, max_width=360),
                        tooltip=f"{posicao['Placa']} — {posicao['Situação']}",
                        icon=folium.Icon(color=cor, icon=icone, prefix="fa")
                    ).add_to(mapa)

                if len(limites) > 1:
                    mapa.fit_bounds(limites, padding=(35, 35))

                st_folium(
                    mapa,
                    height=520,
                    use_container_width=True,
                    returned_objects=[],
                    key="mapa_rastreador_protege"
                )

                tabela = pd.DataFrame(posicoes)[[
                    "Placa", "Última atualização", "Velocidade (km/h)",
                    "Situação", "Endereço"
                ]]
                st.dataframe(tabela, use_container_width=True, hide_index=True)

            except Exception:
                st.session_state.pop("protege_sessao", None)
                st.session_state.pop("protege_pagina", None)
                st.error(
                    "Não consegui entrar automaticamente no rastreador. "
                    "Confira as credenciais e os identificadores cadastrados."
                )

        if hasattr(st, "fragment"):
            st.fragment(run_every="30s")(exibir_painel_rastreador)()
        else:
            exibir_painel_rastreador()

# -------------------------------------------------------------
# ABA: DEMANDAS ATIVAS
# -------------------------------------------------------------
with tab_demandas:
    st.subheader("Gerenciamento de Cargas e Minutos")
    df_editado = st.data_editor(
        st.session_state.demandas,
        column_config={
            "Tempo_Coleta": st.column_config.NumberColumn("Tempo Coleta (min)", min_value=1, max_value=120),
            "Tempo_Entrega": st.column_config.NumberColumn("Tempo Entrega (min)", min_value=1, max_value=120),
            "Peso": None, "id": None, "Supervisor": None
        },
        disabled=["Obra", "Origem", "Destino", "Materiais", "Urgência"],
        hide_index=True, use_container_width=True
    )
    st.session_state.demandas = df_editado
    
    st.divider()
    st.subheader("📣 Concluir Entregas (Trello + Teams)")
    st.caption(
        "Ao clicar em 'Concluir e Avisar', o sistema notifica o supervisor no Teams e já move o cartão "
        "para a coluna 'Concluídas' lá no Trello instantaneamente."
    )

    data_hoje_entregas = datetime.now(FUSO_LOCAL).strftime("%d/%m/%Y")
    conn = sqlite3.connect(DB_FILE)
    df_entregues_hoje = pd.read_sql_query(
        "SELECT id, obra AS Obra, origem AS Origem, destino AS Destino, "
        "materiais AS Materiais FROM historico_concluidos "
        "WHERE data_conclusao = ? ORDER BY rowid DESC",
        conn,
        params=(data_hoje_entregas,)
    )
    conn.close()

    ids_entregues_hoje = set(
        df_entregues_hoje.get("id", pd.Series(dtype=str)).astype(str)
    )
    df_abertas_hoje = st.session_state.demandas.copy()
    if not df_abertas_hoje.empty:
        df_abertas_hoje = df_abertas_hoje[
            df_abertas_hoje["Urgência"].isin(["HOJE", "VENCIDA"])
        ].copy()

    linhas_entregas = []
    if not df_abertas_hoje.empty:
        linhas_entregas.extend(df_abertas_hoje.to_dict("records"))

    for _, entregue in df_entregues_hoje.iterrows():
        card_id = str(entregue["id"])
        if any(str(item.get("id", "")) == card_id for item in linhas_entregas):
            continue
        destino_entregue = entregue["Destino"]
        linhas_entregas.append({
            "id": card_id,
            "Obra": entregue["Obra"],
            "Origem": entregue["Origem"],
            "Destino": destino_entregue,
            "Materiais": entregue["Materiais"],
            "Supervisor": SUPERVISORES_MAP.get(
                destino_entregue, "Sede / Logística"
            )
        })

    if not linhas_entregas:
        st.info("Nenhuma entrega atrasada ou prevista para hoje na fila.")
    else:
        for row in linhas_entregas:
            card_id = str(row.get("id", ""))
            entregue_no_trello = card_id in ids_entregues_hoje
            sup = row.get("Supervisor", "Sede / Logística")
            dest = row.get("Destino", "")
            mat = row.get("Materiais", "Ver Trello")

            c1, c_status, c2 = st.columns([3.2, 1.1, 1.4])
            c1.markdown(
                f"📦 **{row.get('Obra', '')} — {dest}** "
                f"(Resp: {sup}) <br>"
                f"<span style='font-size:12px; color:gray;'>{mat}</span>",
                unsafe_allow_html=True
            )
            
            if entregue_no_trello:
                c_status.markdown("🟢 **Finalizada**")
                c2.button(
                    "✅ Já Baixada",
                    key=f"btn_tms_{card_id}_done",
                    disabled=True,
                    use_container_width=True
                )
            else:
                c_status.caption("Aguardando Baixa")
                if c2.button(
                    "✅ Concluir e Avisar",
                    key=f"btn_tms_{card_id}",
                    type="primary",
                    use_container_width=True
                ):
                    # 1. Movimentar no Trello Automaticamente
                    trello_ok, trello_msg = mover_cartao_trello(card_id)
                    
                    # 2. Avisar no Teams
                    url_webhook, _ = obter_webhook_teams(
                        dest,
                        supervisor=sup,
                        obra=row.get("Obra", "")
                    )
                    teams_ok = False
                    if url_webhook:
                        concluida_em = datetime.now(FUSO_LOCAL).strftime(
                            "%d/%m/%Y às %H:%M"
                        )
                        mensagem = (
                            "✅ **Os materiais foram entregues na obra e a demanda "
                            "foi concluída.**\n\n"
                            f"**Obra:** {row.get('Obra', '')}\n\n"
                            f"**Unidade / local da entrega:** {dest}\n\n"
                            f"**Materiais entregues:** {mat}\n\n"
                            f"**Origem da coleta:** {row.get('Origem', '')}\n\n"
                            f"**Data e Hora:** {concluida_em}"
                        )
                        teams_ok, detalhe = disparar_teams(
                            url_webhook,
                            f"✅ Entrega concluída — {dest}",
                            mensagem
                        )
                    
                    if trello_ok:
                        st.success("✅ Cartão movido para Concluídas no Trello com sucesso!")
                        if teams_ok:
                            st.success(f"📱 Supervisor ({sup}) notificado no Teams!")
                        else:
                            st.warning("Trello atualizado, mas o aviso no Teams falhou (ou não configurado).")
                    else:
                        st.error(f"⚠️ Erro ao mover no Trello: {trello_msg}")
                    
                    time.sleep(2)
                    st.rerun()

            st.write("---")

# -------------------------------------------------------------
# ABA: HISTÓRICO E CONCLUÍDOS
# -------------------------------------------------------------
with tab_historico:
    st.subheader("📋 Atrasadas ou de Hoje Concluídas Hoje")
    st.write(
        "Aqui aparecem somente as demandas cujo prazo era **hoje ou já estava "
        "vencido** e que foram movidas para **'CONCLUÍDAS/ENTREGUES' hoje** no Trello."
    )
    
    conn = sqlite3.connect(DB_FILE)
    data_hoje = datetime.now(FUSO_LOCAL).strftime("%d/%m/%Y")
    df_hist = pd.read_sql_query(
        "SELECT * FROM historico_concluidos WHERE data_conclusao = ? ORDER BY rowid DESC",
        conn,
        params=(data_hoje,)
    )
    conn.close()
    
    if df_hist.empty:
        st.info("Nenhuma demanda atrasada ou com prazo de hoje foi concluída hoje.")
    else:
        st.dataframe(df_hist, use_container_width=True, hide_index=True)

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
                conn.execute(
                    "DELETE FROM locais_removidos WHERE apelido = ?",
                    (apelido_input,)
                )
                conn.execute("INSERT OR REPLACE INTO locais (apelido, endereco, lat, lon) VALUES (?, ?, ?, ?)", (apelido_input, endereco_input, lat, lon))
                conn.commit()
                conn.close()
                st.success(f"✅ GPS de '{apelido_input}' salvo com sucesso!")
            else:
                st.error("❌ Não consegui achar as coordenadas com esse texto. Cole o Link Direto do Google Maps!")
        else:
            st.warning("Preencha o nome e o endereço.")

    conn = sqlite3.connect(DB_FILE)
    conn.execute(
        "DELETE FROM locais WHERE UPPER(TRIM(apelido)) = 'DESCONHECIDO'"
    )
    conn.commit()
    df_locais = pd.read_sql_query("SELECT * FROM locais ORDER BY apelido", conn)
    conn.close()
    st.dataframe(df_locais, use_container_width=True, hide_index=True)

    st.divider()
    st.markdown("#### Remover local")
    locais_protegidos = set(ALIASES_LOCAL_BASE)
    locais_removiveis = [
        apelido for apelido in df_locais["apelido"].tolist()
        if apelido not in locais_protegidos
    ]

    if locais_removiveis:
        local_remover = st.selectbox(
            "Selecione o local que deseja remover",
            locais_removiveis,
            index=None,
            placeholder="Escolha um local..."
        )
        confirmar_remocao = st.checkbox(
            "Confirmo que desejo remover este local e seu GPS",
            key="confirmar_remocao_local"
        )

        if st.button(
            "🗑️ Remover local selecionado",
            disabled=not (local_remover and confirmar_remocao)
        ):
            conn = sqlite3.connect(DB_FILE)
            conn.execute(
                "INSERT OR REPLACE INTO locais_removidos (apelido) VALUES (?)",
                (local_remover,)
            )
            conn.execute(
                "DELETE FROM locais WHERE apelido = ?",
                (local_remover,)
            )
            conn.commit()
            conn.close()
            st.success(f"✅ Local '{local_remover}' removido.")
            st.rerun()
    else:
        st.info("Não há locais disponíveis para remoção.")

# -------------------------------------------------------------
# ABA: FECHAMENTO MENSAL E CUSTOS
# -------------------------------------------------------------
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
        conn.commit()
        st.success("✅ Base de cálculo atualizada!")
    
    st.divider()
    col_recibo, col_km = st.columns(2)
    
    with col_recibo:
        st.markdown("#### ⛽ Lançar Recibo de Gasto")
        with st.form("form_recibo", clear_on_submit=True):
            f_data = st.date_input("Data do Recibo")
            fc1, fc2 = st.columns(2)
            f_litros = fc1.number_input("Litros Abastecidos", min_value=0.0, step=0.1)
            f_valor = fc2.number_input("Preço pago (R$/L)", value=novo_preco, step=0.01)
            f_manut = st.number_input("Gastos c/ Manutenção (R$)", min_value=0.0, step=10.0)
            f_obs = st.text_input("Observação (Ex: Posto Ipiranga, Troca de Óleo)")
            
            if st.form_submit_button("Lançar no Caixa"):
                conn.execute("INSERT INTO abastecimentos (data, litros, valor_litro, manutencao, obs) VALUES (?, ?, ?, ?, ?)", 
                             (f_data.strftime("%d/%m/%Y"), f_litros, f_valor, f_manut, f_obs))
                conn.commit()
                st.success("Recibo salvo com sucesso!")

    with col_km:
        st.markdown("#### 🛣️ Lançar KMs Avulsos")
        with st.form("form_km", clear_on_submit=True):
            k_data = st.date_input("Data da Corrida")
            k_km = st.number_input("Total de KM Rodado", min_value=0.1, step=1.0)
            k_obs = st.text_input("Motivo (Ex: Ida ao banco, Frete extra)")
            
            if st.form_submit_button("Lançar KMs"):
                conn.execute("INSERT INTO registro_km (data, km, obs) VALUES (?, ?, ?)", 
                             (k_data.strftime("%d/%m/%Y"), k_km, k_obs))
                conn.commit()
                st.success(f"{k_km} km salvos com sucesso!")

    st.divider()
    st.markdown("#### 📊 Painel de Fechamento (Mês Atual)")
    mes_atual_str = datetime.now().strftime("%m/%Y")
    
    df_km = pd.read_sql_query("SELECT data, km FROM registro_km", conn)
    df_km['data_dt'] = pd.to_datetime(df_km['data'], format="%d/%m/%Y", errors='coerce')
    df_km = df_km.dropna(subset=['data_dt'])
    km_mes = df_km[df_km['data_dt'].dt.strftime('%m/%Y') == mes_atual_str]['km'].sum()
    
    df_abastec = pd.read_sql_query("SELECT data, litros, valor_litro, manutencao FROM abastecimentos", conn)
    df_abastec['data_dt'] = pd.to_datetime(df_abastec['data'], format="%d/%m/%Y", errors='coerce')
    df_abastec = df_abastec.dropna(subset=['data_dt'])
    df_abastec_mes = df_abastec[df_abastec['data_dt'].dt.strftime('%m/%Y') == mes_atual_str].copy()
    
    if not df_abastec_mes.empty:
        gasto_gasolina_mes = (df_abastec_mes['litros'] * df_abastec_mes['valor_litro']).sum()
        gasto_manutencao_mes = df_abastec_mes['manutencao'].sum()
    else:
        gasto_gasolina_mes = 0.0
        gasto_manutencao_mes = 0.0
        
    gasto_total_mes = gasto_gasolina_mes + gasto_manutencao_mes
    custo_real_por_km = (gasto_total_mes / km_mes) if km_mes > 0 else 0.0

    met1, met2, met3, met4 = st.columns(4)
    met1.metric("KM Total Rodado", f"{km_mes:.1f} km", f"Mês: {mes_atual_str}", delta_color="off")
    met2.metric("Gasto com Gasolina", f"R$ {gasto_gasolina_mes:.2f}", "Pelo recibo", delta_color="inverse")
    met3.metric("Gasto em Manutenção", f"R$ {gasto_manutencao_mes:.2f}", "Pelo recibo", delta_color="inverse")
    
    if custo_real_por_km <= 1.50:
        met4.metric("CUSTO REAL / KM", f"R$ {custo_real_por_km:.2f}", "Mais barato que frete 1.50!", delta_color="normal")
    else:
        met4.metric("CUSTO REAL / KM", f"R$ {custo_real_por_km:.2f}", "Atenção: Carro caro!", delta_color="inverse")

    conn.close()

# -------------------------------------------------------------
# ABA: INTEGRAÇÕES (TEAMS E TRELLO)
# -------------------------------------------------------------
with tab_integ:
    st.subheader("⚙️ Configurações de API e Automações")
    
    # --- TRELLO ---
    st.markdown("### 1. Automação do Trello (Concluir Cartão)")
    st.write("Siga os passos abaixo para permitir que a Torre de Controle arraste os cartões no Trello automaticamente:")
    st.markdown(
        "1. Acesse [https://trello.com/app-key](https://trello.com/app-key) e copie a **Chave (API Key)**.\n"
        "2. Na mesma página, clique no botão para gerar um **Token** e copie o código secreto."
    )
    
    conn = sqlite3.connect(DB_FILE)
    cfg_trello = conn.execute("SELECT api_key, token, id_lista_concluida FROM config_trello WHERE id=1").fetchone()
    
    c_trl1, c_trl2 = st.columns(2)
    nova_api = c_trl1.text_input("Chave da API (Key)", value=cfg_trello[0], type="password")
    novo_token = c_trl2.text_input("Token Secreto", value=cfg_trello[1], type="password")
    
    listas_trello = st.session_state.get('trello_lists_raw', [])
    nova_lista_id = cfg_trello[2]
    
    if listas_trello:
        opcoes_dropdown = [l['id'] for l in listas_trello if not l.get('closed')]
        nomes_dropdown = {l['id']: l['name'] for l in listas_trello if not l.get('closed')}
        index_inicial = opcoes_dropdown.index(cfg_trello[2]) if cfg_trello[2] in opcoes_dropdown else 0
        
        st.write("Escolha para qual coluna do Trello o cartão deve ir quando você clicar em 'Concluir':")
        nova_lista_id = st.selectbox("Coluna de Destino", options=opcoes_dropdown, format_func=lambda x: nomes_dropdown[x], index=index_inicial)
    else:
        st.info("💡 Sincronize o Trello ali no menu lateral vermelho primeiro para poder ver as colunas do seu quadro aqui.")
        
    if st.button("Salvar Chaves do Trello", type="primary"):
        conn.execute("UPDATE config_trello SET api_key=?, token=?, id_lista_concluida=? WHERE id=1", (nova_api, novo_token, nova_lista_id))
        conn.commit()
        st.success("Integração com Trello salva com sucesso!")
        
    st.divider()

    # --- TEAMS ---
    st.markdown("### 2. Integração dos Grupos no Teams")
    st.write(
        "Caso os Secrets não estejam configurados, o aplicativo olhará para estes links salvos localmente."
    )

    df_teams = pd.read_sql_query("SELECT * FROM webhooks_teams ORDER BY setor", conn)
    for index, row in df_teams.iterrows():
        setor = row['setor']
        nova_url = st.text_input(f"👤 {setor}", value=row['url'], key=f"tms_db_{setor}")
        if st.button(f"Salvar {setor}"):
            conn.execute("UPDATE webhooks_teams SET url=? WHERE setor=?", (nova_url, setor))
            conn.commit()
            st.success(f"Link de '{setor}' salvo no banco local!")
            
    conn.close()

# -------------------------------------------------------------
# ABA: ROTEIRO E MAPA
# -------------------------------------------------------------
with tab_roteiro:
    data_hoje_roteiro = datetime.now(FUSO_LOCAL).strftime("%d/%m/%Y")
    if (
        st.session_state.get('rota_gerada', False)
        and st.session_state.get('data_rota') != data_hoje_roteiro
    ):
        st.session_state['rota_gerada'] = False

    df_ativos = st.session_state.demandas.copy()
    if not df_ativos.empty:
        df_ativos["Origem"] = df_ativos["Origem"].apply(
            canonicalizar_ponto_rota
        )
        df_ativos["Destino"] = df_ativos["Destino"].apply(
            canonicalizar_ponto_rota
        )

        origem_invalida = df_ativos["Origem"].fillna("").isin(
            ["", "DESCONHECIDO"]
        )
        destino_invalido = df_ativos["Destino"].fillna("").isin(
            ["", "DESCONHECIDO"]
        )
        demandas_incompletas = df_ativos[origem_invalida | destino_invalido]
        if not demandas_incompletas.empty:
            obras_incompletas = ", ".join(
                demandas_incompletas["Obra"].astype(str).tolist()
            )
            st.warning(
                "⚠️ Estas demandas estão sem origem ou destino legível no "
                f"Trello e ficaram fora da rota: **{obras_incompletas}**."
            )
            df_ativos = df_ativos[~(origem_invalida | destino_invalido)].copy()

    if df_ativos.empty:
        st.info("Sincronize o Trello para carregar demandas antes de calcular a rota.")
    
    if st.button(
        "🚀 Calcular Rota Otimizada",
        type="primary",
        disabled=df_ativos.empty
    ):
        with st.spinner("Analisando grupamentos e traçando rota anti zigue-zague..."):
            
            conn = sqlite3.connect(DB_FILE)
            garantir_gps_local_base(conn)
            pontos_brutos = (
                [ponto_saida]
                + df_ativos["Origem"].tolist()
                + df_ativos["Destino"].tolist()
            )
            pontos_necessarios = {
                canonicalizar_ponto_rota(p)
                for p in pontos_brutos
                if canonicalizar_ponto_rota(p) not in {
                    "", "DESCONHECIDO", "NAN", "NONE"
                }
            }
            locais_dict = {}
            for p in pontos_necessarios:
                res = conn.execute(
                    "SELECT endereco, lat, lon FROM locais WHERE apelido = ?",
                    (p,)
                ).fetchone()
                if res and res[1] is not None and res[2] is not None:
                    locais_dict[p] = (res[1], res[2])
                    continue

                if res and res[0]:
                    lat, lon = buscar_coordenadas(res[0])
                    if lat is not None and lon is not None:
                        conn.execute(
                            "UPDATE locais SET lat = ?, lon = ? WHERE apelido = ?",
                            (lat, lon, p)
                        )
                        locais_dict[p] = (lat, lon)
            conn.commit()
            conn.close()
            
            faltando = sorted(
                p for p in pontos_necessarios
                if p not in locais_dict
                and p not in {"", "DESCONHECIDO", "NAN", "NONE"}
            )
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
            current_time = INICIO_ROTA_MIN
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
                    if "Menor Distância" in estrategia:
                        score = d + (dur * 0.1)
                    else:
                        prio = 1.0

                        if is_dropoff:
                            prio = 2.0
                            if pendentes_para_p > 0:
                                prio = 0.1

                        if is_pickup:
                            destinos_desta_coleta = set(
                                t['Destino'] for t in unpicked
                                if t['Origem'] == p
                            )
                            if destinos_desta_coleta.intersection(destinos_no_carro):
                                prio *= 3.0
                            else:
                                prio *= 1.5

                        if "Urgências" in estrategia:
                            prio *= urgency ** 2
                        elif "Descarregar" in estrategia and is_dropoff:
                            prio *= 5.0

                        if prio == 0:
                            prio = 0.001
                        score = (d + (dur * 0.1)) / prio
                    
                    if d < 0.1: score = -1.0

                    if score < min_score:
                        min_score = score
                        best_point = p
                        best_dist, best_dur = d, dur

                if (
                    (current_time + best_dur) >= INICIO_ALMOCO_MIN
                    and not lunch_taken
                ):
                    route_steps.append({
                        "type": "lunch",
                        "chegada": format_time(current_time + best_dur),
                        "saida": format_time(
                            current_time + best_dur + DURACAO_ALMOCO_MIN
                        )
                    })
                    current_time += DURACAO_ALMOCO_MIN
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

                # --- AJUSTE CARREGAMENTO MATINAL NO PONTO DE SAÍDA ---
                # Se estamos na primeira parada, e ela é o Ponto de Saída (o escritório),
                # então as coletas já foram separadas pelo Almoxarife das 07:00 às 07:30.
                is_start_load = (best_point == ponto_saida and current_time == INICIO_ROTA_MIN and not any(a[0] == "ENTREGAR" for a in actions_here))
                
                if is_start_load:
                    chegada_str = "07:00"
                    saida_str = "07:30"
                    tempo_local_exibicao = 30
                    service_mins = 0 # O carregamento absorveu os minutos antes de 07:30
                else:
                    chegada_str = format_time(current_time)
                    saida_str = format_time(current_time + service_mins)
                    tempo_local_exibicao = service_mins

                route_steps.append({
                    "type": "stop",
                    "destino": best_point,
                    "dist": best_dist,
                    "travel_mins": best_dur,
                    "tempo_local": tempo_local_exibicao,
                    "chegada": chegada_str,
                    "saida": saida_str,
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

            coords_ordenadas_rota = [locais_dict[ponto_saida]]
            for step in route_steps:
                destino_step = step.get("destino")
                if destino_step in locais_dict:
                    coords_ordenadas_rota.append(locais_dict[destino_step])
            geometria_rota, geometria_viaria = buscar_geometria_rota(
                coords_ordenadas_rota
            )
            
            st.session_state['rota_gerada'] = True
            st.session_state['route_steps'] = route_steps
            st.session_state['total_km'] = total_km
            st.session_state['locais_dict'] = locais_dict
            st.session_state['p_saida'] = ponto_saida
            st.session_state['horario_conclusao_min'] = current_time
            st.session_state['geometria_rota'] = geometria_rota
            st.session_state['geometria_viaria'] = geometria_viaria
            st.session_state['data_rota'] = datetime.now(FUSO_LOCAL).strftime(
                "%d/%m/%Y"
            )

    if st.session_state.get('rota_gerada', False):
        route_steps = st.session_state['route_steps']
        total_km = st.session_state['total_km']
        locais_dict = st.session_state['locais_dict']
        p_saida = st.session_state['p_saida']
        horario_conclusao_min = st.session_state.get('horario_conclusao_min')
        if horario_conclusao_min is None:
            ultima_saida = next(
                (
                    step.get('saida')
                    for step in reversed(route_steps)
                    if step.get('saida')
                ),
                "07:30"
            )
            hora_fim, minuto_fim = map(int, ultima_saida.split(":"))
            horario_conclusao_min = hora_fim * 60 + minuto_fim

        geometria_rota = st.session_state.get('geometria_rota')
        geometria_viaria = st.session_state.get('geometria_viaria', False)
        if not geometria_rota:
            coords_ordenadas_rota = [locais_dict[p_saida]]
            for step in route_steps:
                destino_step = step.get("destino")
                if destino_step in locais_dict:
                    coords_ordenadas_rota.append(locais_dict[destino_step])
            geometria_rota, geometria_viaria = buscar_geometria_rota(
                coords_ordenadas_rota
            )
        
        if "Empresa" in veiculo_selecionado:
            conn = sqlite3.connect(DB_FILE)
            cfg = pd.read_sql_query("SELECT consumo, preco_gasolina FROM config_frota WHERE id=1", conn).iloc[0]
            conn.close()
            custo_rota = (total_km / float(cfg['consumo'])) * float(cfg['preco_gasolina'])
            desc_custo = "Estimativa Gasolina"
        else:
            custo_rota = total_km * 1.50
            desc_custo = "Custo do Frete (R$ 1,50/km)"

        col_esq, col_dir = st.columns([1.2, 0.8])

        with col_esq:
            st.subheader(
                f"📋 Roteiro de Viagem do Davi — {data_hoje_roteiro}"
            )
            st.caption(
                "🕖 Expediente: 07:00 às 17:00  •  "
                "Preparação: 07:00 às 07:30  •  Saída para a rota: 07:30"
            )
            conn = sqlite3.connect(DB_FILE)
            ids_concluidos_hoje = {
                str(registro[0])
                for registro in conn.execute(
                    "SELECT id FROM historico_concluidos "
                    "WHERE data_conclusao = ?",
                    (data_hoje_roteiro,)
                ).fetchall()
            }
            conn.close()
            texto_whatsapp = (
                "🚚 *ROTEIRO DE LOGÍSTICA - DAVI*\n"
                f"📅 Data: {data_hoje_roteiro}\n"
                "🕖 Expediente: 07:00 às 17:00\n"
                f"🏁 Saída: {p_saida} (07:30)\n"
                f"🚗 Veículo: {veiculo_selecionado.split('(')[0].strip()}\n\n"
            )
            
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
                        concluida = str(t.get('id', '')) in ids_concluidos_hoje
                        col_demanda, col_status = st.columns([9, 1])
                        col_demanda.markdown(
                            f":{cor}[**{icone}**] {t['Materiais']} "
                            f"*(Obra: {t['Obra']})*"
                        )
                        if concluida:
                            col_status.markdown("✅")
                        prefixo_status = "✅ " if concluida else ""
                        texto_whatsapp += (
                            f" - {prefixo_status}{acao.capitalize()}: "
                            f"{t['Materiais']} (Obra: {t['Obra']})\n"
                        )
                        
                    texto_whatsapp += "\n"
                    num_parada += 1

            horario_conclusao = format_time(horario_conclusao_min)
            if horario_conclusao_min < FIM_EXPEDIENTE_MIN:
                tempo_standby = FIM_EXPEDIENTE_MIN - horario_conclusao_min
                st.success(
                    f"✅ **Rota prevista para ser concluída às "
                    f"{horario_conclusao}.**"
                )
                st.info(
                    f"🟢 **Todas as demandas finalizadas:** Davi ficará em "
                    f"stand-by das {horario_conclusao} às 17:00 "
                    f"({formatar_duracao(tempo_standby)} disponíveis)."
                )
                texto_whatsapp += (
                    f"✅ Rota concluída às {horario_conclusao}.\n"
                    f"🟢 Davi em stand-by até 17:00 "
                    f"({formatar_duracao(tempo_standby)}).\n"
                )
                status_expediente = (
                    f"Davi em stand-by até 17:00 "
                    f"({formatar_duracao(tempo_standby)})"
                )
            elif horario_conclusao_min == FIM_EXPEDIENTE_MIN:
                st.success(
                    "✅ **Rota prevista para ser concluída às 17:00, "
                    "no fim do expediente.**"
                )
                texto_whatsapp += "✅ Rota concluída às 17:00.\n"
                status_expediente = "Conclusão no fim do expediente"
            else:
                excedente = horario_conclusao_min - FIM_EXPEDIENTE_MIN
                st.warning(
                    f"⚠️ **Rota prevista para terminar às {horario_conclusao}, "
                    f"ultrapassando o expediente em "
                    f"{formatar_duracao(excedente)}.**"
                )
                texto_whatsapp += (
                    f"⚠️ Previsão de término: {horario_conclusao} "
                    f"({formatar_duracao(excedente)} após as 17:00).\n"
                )
                status_expediente = (
                    f"Previsão excede o expediente em "
                    f"{formatar_duracao(excedente)}"
                )

            st.success(f"🛣️ **Total Rodado Planejado:** {total_km:.1f} km | 💰 **{desc_custo}:** R$ {custo_rota:.2f}")
            texto_whatsapp += f"🛣️ Total Planejado: {total_km:.1f} km\n"

            # --- PAINEL INTELIGENTE DE FECHAMENTO DE KM ---
            st.divider()
            with st.form("fechamento_km_rota"):
                st.markdown("#### 💾 Fechamento de KM da Rota do Dia")
                
                total_acoes = sum(len(step.get('actions', [])) for step in route_steps)
                acoes_concluidas = sum(
                    1 for step in route_steps 
                    for acao, t in step.get('actions', []) 
                    if str(t.get('id', '')) in ids_concluidos_hoje
                )
                
                if acoes_concluidas < total_acoes:
                    st.warning(
                        f"⚠️ **Atenção:** Apenas **{acoes_concluidas} de {total_acoes}** demandas "
                        "planejadas nesta rota foram marcadas como concluídas no Trello hoje. "
                        "Se a rota não foi 100% finalizada, altere a quilometragem abaixo "
                        "para o que foi efetivamente lido no painel do veículo."
                    )
                else:
                    st.success("✅ Todas as demandas desta rota foram devidamente concluídas hoje!")
                    
                km_real = st.number_input("KM Efetivamente Rodado na Rota", value=float(total_km), step=1.0)
                
                if st.form_submit_button("Gravar KM no Painel de Custos"):
                    conn = sqlite3.connect(DB_FILE)
                    conn.execute(
                        "INSERT INTO registro_km (data, km, obs) VALUES (?, ?, ?)", 
                        (data_hoje_roteiro, km_real, f"Fechamento da Rota Automática ({acoes_concluidas}/{total_acoes} entregas)")
                    )
                    conn.commit()
                    conn.close()
                    st.success(f"✅ {km_real:.1f} km registrados para o fechamento de custos!")

            # --- BOTÃO TEAMS ---
            url_geral, _ = obter_webhook_teams("Geral / Logística")
            if url_geral:
                if st.button("📢 Mandar Roteiro no Grupo Geral (Teams)", use_container_width=True):
                    resumo = (
                        "O roteiro do Davi já está pronto.\n\n"
                        f"**Data da rota:** {data_hoje_roteiro}\n\n"
                        "**Saída para a rota:** 07:30\n\n"
                        f"**Previsão de conclusão:** {horario_conclusao}\n\n"
                        f"**Situação após a rota:** {status_expediente}\n\n"
                        f"**Total de paradas:** {num_parada-1}\n\n"
                        f"**Quilometragem Planejada:** {total_km:.1f} km"
                    )
                    enviado, detalhe = disparar_teams(
                        url_geral,
                        "🚚 Roteiro Diário Liberado!",
                        resumo
                    )
                    if enviado:
                        st.success("✅ Roteiro enviado para o grupo Geral!")
                    else:
                        st.error(f"Erro ao enviar o roteiro: {detalhe}")

            st.text_area("📋 Texto Pronto para WhatsApp", value=texto_whatsapp, height=150)

        with col_dir:
            st.subheader("🗺️ Mapa da Rota")
            m = folium.Map(location=[-3.7319, -38.5267], zoom_start=12)
            path_points = []
            
            # Ajuste de dispersão para pinos que caem na mesma coordenada exata
            offsets_dict = {}
            def apply_offset(lat, lon):
                key = (round(lat, 4), round(lon, 4))
                offsets_dict[key] = offsets_dict.get(key, 0) + 1
                cnt = offsets_dict[key]
                if cnt > 1:
                    # Desloca a bolinha sutilmente para enxergar o número abaixo
                    return lat - 0.00035 * (cnt - 1), lon + 0.00035 * (cnt - 1)
                return lat, lon

            p_num = 1
            if p_saida in locais_dict:
                lat_s, lon_s = apply_offset(*locais_dict[p_saida])
                path_points.append([lat_s, lon_s])

            for step in route_steps:
                if step.get('destino') and step['destino'] in locais_dict:
                    lat_orig, lon_orig = locais_dict[step['destino']]
                    lat, lon = apply_offset(lat_orig, lon_orig)
                    path_points.append([lat, lon])
                    
                    if step['type'] == 'lunch': continue
                    if step['type'] == 'return':
                        continue

                    acoes = [a[0] for a in step.get('actions', [])]
                    tem_coleta = "COLETAR" in acoes
                    tem_entrega = "ENTREGAR" in acoes
                    if tem_coleta and tem_entrega:
                        fundo_marcador = (
                            "linear-gradient(90deg, #f59e0b 0 50%, "
                            "#16a34a 50% 100%)"
                        )
                    elif tem_coleta:
                        fundo_marcador = "#f59e0b"
                    else:
                        fundo_marcador = "#16a34a"
                    num_str = str(p_num)
                    tt_text = f"Parada {p_num}: {step['destino']}"
                    acoes_texto = " e ".join(sorted(set(acoes))).title()
                    popup_html = (
                        f"<b>Parada {p_num}: "
                        f"{html_escape(str(step['destino']))}</b>"
                        f"<br>Chegada: {step['chegada']}"
                        f"<br>Saída: {step['saida']}"
                        f"<br>Ação: {html_escape(acoes_texto)}"
                    )
                    
                    folium.Marker(
                        [lat, lon],
                        popup=folium.Popup(popup_html, max_width=280),
                        tooltip=tt_text,
                        icon=folium.DivIcon(html=f'''<div style="background: {fundo_marcador}; color: white; border: 2px solid white; border-radius: 50%; width: 30px; height: 30px; display: flex; justify-content: center; align-items: center; font-weight: bold; box-shadow: 2px 2px 5px rgba(0,0,0,0.5); font-family: sans-serif; font-size: 14px;">{num_str}</div>''')
                    ).add_to(m)
                    p_num += 1

            if geometria_viaria and len(geometria_rota) > 1:
                folium.PolyLine(
                    geometria_rota,
                    color="#2563eb",
                    weight=5,
                    opacity=0.85,
                    tooltip="Trajeto planejado"
                ).add_to(m)

            if len(path_points) > 1:
                m.fit_bounds(path_points, padding=(45, 45), max_zoom=14)

            # Início da rota no mapa sempre fica no topo do index visual
            if p_saida in locais_dict:
                lat_s, lon_s = path_points[0]
                folium.Marker(
                    [lat_s, lon_s],
                    popup=folium.Popup(
                        f"<b>Saída/retorno: {html_escape(str(p_saida))}</b>"
                        "<br>Início da rota: 07:30",
                        max_width=280
                    ),
                    tooltip="Saída/retorno — 07:30",
                    z_index_offset=1000,
                    icon=folium.DivIcon(html=f'''<div style="background-color: #2563eb; color: white; border: 3px solid white; border-radius: 50%; width: 34px; height: 34px; display: flex; justify-content: center; align-items: center; font-weight: bold; box-shadow: 2px 2px 7px rgba(0,0,0,0.6); font-family: sans-serif; font-size: 15px;">0</div>''')
                ).add_to(m)

            st_folium(m, width=450, height=550, returned_objects=[])
            if geometria_viaria:
                st.caption("🛣️ Traçado calculado pelas ruas, na ordem das paradas.")
            else:
                st.caption(
                    "⚠️ O serviço viário não respondeu. Para evitar linhas "
                    "incorretas, somente as paradas estão sendo exibidas."
                )
            st.markdown(
                "<div style='text-align: center; font-size: 14px; "
                "margin-top: 10px;'><b>Legenda:</b> 🟡 Coleta | "
                "🟢 Entrega | 🔵 Início/Retorno | 🟡🟢 Ambos</div>",
                unsafe_allow_html=True
            )
