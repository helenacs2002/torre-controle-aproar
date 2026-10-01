from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import sqlalchemy
import os

app = FastAPI()

# Ligação ao Supabase usando a porta de Connection Pooling (Porta 6543)
DATABASE_URL = os.getenv("SUPABASE_URL_POOLING")
engine = sqlalchemy.create_engine(DATABASE_URL)

# ==========================================
# PARTE 1: A página visual do motorista (GET)
# ==========================================
@app.get("/davi", response_class=HTMLResponse)
def interface_motorista():
    # Vai buscar as paragens do motorista ao Supabase
    try:
        with engine.connect() as conexao:
            query = sqlalchemy.text("SELECT * FROM rastreio_paradas WHERE motorista = 'Davi'")
            resultado = conexao.execute(query).fetchall()
    except Exception as e:
        resultado = []

    # HTML que o telemóvel do Davi vai abrir instantaneamente
    html_content = f"""
    <!DOCTYPE html>
    <html lang="pt">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Aproar - App do Motorista</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0e1117; color: #fff; padding: 15px; margin: 0; }}
            .card {{ background: #262730; padding: 20px; border-radius: 10px; margin-bottom: 15px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }}
            .btn-acao {{ background: #ff4b4b; color: white; border: none; padding: 12px; width: 100%; border-radius: 6px; font-size: 16px; font-weight: bold; cursor: pointer; }}
            .btn-acao:active {{ background: #ff2b2b; }}
        </style>
    </head>
    <body>
        <h2>Torre de Controlo - Rota do Davi</h2>
        <div class="card">
            <p>Estado atual: <strong>Em rota</strong></p>
            <p>Paragens carregadas: <strong>{len(resultado)}</strong></p>
            <button class="btn-acao" onclick="enviarCheckin()">Fazer Check-in / Concluir Paragem</button>
        </div>

        <script>
            async function enviarCheckin() {{
                alert('A registar check-in...');
                
                // Isto envia o aviso para a PARTE 2 deste mesmo código em Python
                const resposta = await fetch('/api/checkin', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ paragem_id: 1, status: 'Concluído' }})
                }});
                
                const dados = await resposta.json();
                alert(dados.mensagem);
            }}
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


# ==========================================
# PARTE 2: O recetor do clique do botão (POST)
# ==========================================
class CheckinPayload(BaseModel):
    paragem_id: int
    status: str

@app.post("/api/checkin")
def registar_checkin(dados: CheckinPayload):
    try:
        with engine.connect() as conexao:
            # Atualiza direto no Supabase quando o botão é premido
            query = sqlalchemy.text(
                "UPDATE rastreio_paradas SET status = :status WHERE id = :id"
            )
            conexao.execute(query, {"status": dados.status, "id": dados.paragem_id})
            conexao.commit()
        return {"sucesso": True, "mensagem": "Atualizado com sucesso na Torre!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
