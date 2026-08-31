# Pacote pronto para GitHub

Versão: **Motor de rota V3 — locais consolidados, GPS no mapa e paleta de referência**.

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
- o painel usa azul-marinho, azul, vermelho, verde, dourado e oliva conforme a referência aprovada;
- o mapa usa as cores cartográficas originais do OpenStreetMap e não solicita API key;
- a última posição do Davi aparece como um caminhão no mapa, com velocidade,
  horário e próximo destino, sem bloquear a abertura da página;
- leituras repetidas de rota, conclusões, check-ins e paradas usam cache curto
  para deixar cliques e atualizações mais rápidos;
- no `/davi`, a próxima entrega é selecionada automaticamente e o registro pede
  somente quem recebeu, uma foto e o botão **Registrar entrega**;
- o roteiro do motorista aparece em lista vertical simples e o mapa completo só
  carrega quando ele solicitar;
- na Torre, o mapa fica no topo e as paradas ocupam a largura total abaixo,
  eliminando o grande espaço vazio entre as colunas;
- ao abrir uma rota antiga com Barra/FIEC repetidas, o sistema a recalcula
  automaticamente com uma visita por local sempre que as dependências permitirem.

Se o Streamlit ainda mostrar a tela anterior, abra **Manage app > Reboot app**.
Depois, na Torre, use uma vez **Recalcular / Atualizar Rota** se a rota antiga
continuar aberta em uma aba que já estava carregada.
