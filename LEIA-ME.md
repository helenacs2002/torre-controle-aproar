# Pacote pronto para GitHub

Envie para a raiz do repositório:

- `app.py`
- `requirements.txt`
- `.gitignore`
- a pasta `pages` inteira
- `logo.png`, caso já exista no projeto atual

No Streamlit Community Cloud, escolha `app.py` como **Main file path**.

As credenciais não estão neste pacote. Copie o conteúdo do `secrets.toml` atual
para **App settings > Secrets** no Streamlit Cloud. Nunca envie o arquivo
`.streamlit/secrets.toml` ao GitHub.

Depois do deploy:

- Torre: `https://seu-endereco.streamlit.app`
- Davi: `https://seu-endereco.streamlit.app/davi`
