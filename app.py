import streamlit as st

st.markdown("### Lançamento de Fechamento de KM")

# Cria as caixas de seleção e datas lado a lado
veiculo = st.selectbox("Veículo", ["Strada (TIF-2I23)"])

col1, col2 = st.columns(2)
with col1:
    data_inicial = st.date_input("Data Inicial")
    km_inicial = st.number_input("KM Inicial", min_value=0, value=0, step=1)
with col2:
    data_final = st.date_input("Data Final")
    km_final = st.number_input("KM Final", min_value=0, value=0, step=1)

# Calcula o KM automaticamente
km_total = 0
if km_final > km_inicial and km_inicial > 0:
    km_total = km_final - km_inicial

# Exibe o resultado em destaque
st.info(f"**Total Rodado no Período:** {km_total} km")

# Botão para salvar
if st.button("Salvar Lançamento"):
    if km_total > 0:
        st.success(f"Lançamento de {km_total} km da {veiculo} salvo com sucesso!")
        # AQUI VOCÊ COLOCA O CÓDIGO PARA SALVAR NO SEU BANCO DE DADOS
    else:
        st.warning("Verifique os valores. O KM Final precisa ser maior que o KM Inicial.")
