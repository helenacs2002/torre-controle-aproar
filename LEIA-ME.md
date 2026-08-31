# Pacote pronto para GitHub

Versão: **Motor de rota V3 — locais consolidados e paleta APROAR**.

Descompacte o ZIP no seu computador e envie/substitua, na raiz do repositório:

- `app.py`
- `requirements.txt`
- `.gitignore`
- a pasta `pages` inteira
- `logo.png`, caso já exista no projeto atual

**Não envie somente o arquivo ZIP para o GitHub.** O Streamlit precisa enxergar
o `app.py` e a pasta `pages` já descompactados. Mantenha o `logo.png` que já está
no repositório; ele será carregado automaticamente.

No Streamlit Community Cloud, escolha `app.py` como **Main file path**.

As credenciais não estão neste pacote. Copie o conteúdo do `secrets.toml` atual
para **App settings > Secrets** no Streamlit Cloud. Nunca envie o arquivo
`.streamlit/secrets.toml` ao GitHub.

Depois do deploy:

- Torre: `https://seu-endereco.streamlit.app`
- Davi: `https://seu-endereco.streamlit.app/davi`

Como confirmar que o código novo está publicado:

- o cabeçalho da Torre mostra discretamente `MOTOR V3`;
- o botão de recalcular é azul, não amarelo;
- coletas usam azul APROAR e entregas usam verde discreto;
- o mapa escuro usa OpenStreetMap e não solicita API key;
- ao abrir uma rota antiga com Barra/FIEC repetidas, o sistema a recalcula
  automaticamente com uma visita por local sempre que as dependências permitirem.

Se o Streamlit ainda mostrar a tela anterior, abra **Manage app > Reboot app**.
Depois, na Torre, use uma vez **Recalcular / Atualizar Rota** se a rota antiga
continuar aberta em uma aba que já estava carregada.
