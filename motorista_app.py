from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
import sqlalchemy
import os

app = FastAPI()

# Ligação ao Supabase usando a porta de Connection Pooling (Porta 6543)
DATABASE_URL = os.getenv("SUPABASE_URL_POOLING")
engine = sqlalchemy.create_engine(DATABASE_URL)

@app.get("/davi", response_class=HTMLResponse)
def interface_motorista():
    # 1. Buscar as paragens do motorista diretamente ao Supabase
    try:
        with engine.connect() as conexao:
            query = sqlalchemy.text("SELECT * FROM rastreio_paradas WHERE motorista = 'Davi'")
            resultado = conexao.execute(query).fetchall()
    except Exception as e:
        return f"<h1>Erro ao ligar à base de dados: {str(e)}</h1>"

    # 2. O teu HTML/CSS/JS otimizado para telemóvel
    # Podes colar aqui a estrutura do carrossel que tinhas no Streamlit
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
            function enviarCheckin() {
                alert('A registar check-in...');
                // Aqui podes adicionar um fetch para uma rota POST do FastAPI que atualiza o Supabase
            }
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)
