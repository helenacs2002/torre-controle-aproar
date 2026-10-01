from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import sqlalchemy
import os

app = FastAPI()

DATABASE_URL = os.getenv("SUPABASE_URL_POOLING")
engine = sqlalchemy.create_engine(DATABASE_URL)

@app.get("/davi", response_class=HTMLResponse)
def interface_motorista():
    # Vai buscar as paragens reais do Davi ao Supabase
    paragens = []
    try:
        with engine.connect() as conexao:
            query = sqlalchemy.text("SELECT * FROM rastreio_paradas WHERE motorista = 'Davi'")
            resultado = conexao.execute(query).fetchall()
            paragens = [dict(row._mapping) for row in resultado]
    except Exception as e:
        paragens = []

    # Criar a lista de paragens em HTML dinamicamente
    itens_html = ""
    for p in paragens:
        itens_html += f"""
        <div class="card">
            <p><strong>Paragem:</strong> {p.get('paragem', 'Endereço')}</p>
            <p>Estado: <strong>{p.get('status', 'Pendente')}</strong></p>
            <button class="btn-acao" onclick="enviarCheckin({p.get('id', 1)})">Concluir Paragem</button>
        </div>
        """

    if not itens_html:
        itens_html = "<div class='card'><p>Sem paragens carregadas no momento.</p></div>"

    # HTML moderno e adaptado para telemóvel (Tema Escuro)
    html_content = f"""
    <!DOCTYPE html>
    <html lang="pt">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Aproar - App do Motorista</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0b0f19; color: #fff; padding: 15px; margin: 0; }}
            .header {{ background: #161b22; padding: 15px; border-radius: 10px; margin-bottom: 15px; border: 1px: #30363d; }}
            .card {{ background: #161b22; padding: 15px; border-radius: 10px; margin-bottom: 15px; border: 1px solid #30363d; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }}
            .btn-acao {{ background: #238636; color: white; border: none; padding: 12px; width: 100%; border-radius: 6px; font-size: 16px; font-weight: bold; cursor: pointer; margin-top: 10px; }}
            .btn-acao:active {{ background: #2ea043; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h3>Bom dia, Davi</h3>
            <p>Rota oficial de entrega</p>
        </div>

        <h4>Roteiro do dia</h4>
        {itens_html}

        <script>
            async function enviarCheckin(paragemId) {{
                if(!confirm('Deseja concluir esta paragem?')) return;
                
                const resposta = await fetch('/api/checkin', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ paragem_id: paragemId, status: 'Concluído' }})
                }});
                
                const dados = await resposta.json();
                if(dados.sucesso) {{
                    alert('Atualizado com sucesso!');
                    location.reload();
                }} else {{
                    alert('Erro ao atualizar.');
                }}
            }}
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

class CheckinPayload(BaseModel):
    paragem_id: int
    status: str

@app.post("/api/checkin")
def registar_checkin(dados: CheckinPayload):
    try:
        with engine.connect() as conexao:
            query = sqlalchemy.text(
                "UPDATE rastreio_paradas SET status = :status WHERE id = :id"
            )
            conexao.execute(query, {"status": dados.status, "id": dados.paragem_id})
            conexao.commit()
        return {"sucesso": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
