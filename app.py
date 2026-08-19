<!-- Bloco de Registro de Quilometragem -->
<div style="max-width: 600px; padding: 20px; font-family: Arial, sans-serif; border: 1px solid #ccc; border-radius: 8px; background-color: #f9f9f9;">
    <h3 style="margin-top: 0; color: #333;">Lançamento de Fechamento de KM</h3>
    
    <form id="form-fechamento-km" style="display: flex; flex-direction: column; gap: 15px;">
        
        <div>
            <label style="font-weight: bold; display: block; margin-bottom: 5px;">Veículo</label>
            <select id="veiculo" style="width: 100%; padding: 8px; border-radius: 4px; border: 1px solid #ccc;">
                <option value="Strada (TIF-2I23)">Strada (TIF-2I23)</option>
                <!-- Adicionar outros veículos aqui -->
            </select>
        </div>

        <div style="display: flex; gap: 15px;">
            <div style="flex: 1;">
                <label style="font-weight: bold; display: block; margin-bottom: 5px;">Data Inicial</label>
                <input type="date" id="data-inicial" style="width: 100%; padding: 8px; border-radius: 4px; border: 1px solid #ccc;">
            </div>
            <div style="flex: 1;">
                <label style="font-weight: bold; display: block; margin-bottom: 5px;">Data Final</label>
                <input type="date" id="data-final" style="width: 100%; padding: 8px; border-radius: 4px; border: 1px solid #ccc;">
            </div>
        </div>

        <div style="display: flex; gap: 15px;">
            <div style="flex: 1;">
                <label style="font-weight: bold; display: block; margin-bottom: 5px;">KM Inicial</label>
                <input type="number" id="km-inicial" placeholder="Ex: 251" style="width: 100%; padding: 8px; border-radius: 4px; border: 1px solid #ccc;" oninput="calcularKM()">
            </div>
            <div style="flex: 1;">
                <label style="font-weight: bold; display: block; margin-bottom: 5px;">KM Final</label>
                <input type="number" id="km-final" placeholder="Ex: 1226" style="width: 100%; padding: 8px; border-radius: 4px; border: 1px solid #ccc;" oninput="calcularKM()">
            </div>
        </div>

        <div style="background-color: #e3f2fd; padding: 15px; border-radius: 4px; text-align: center;">
            <label style="font-weight: bold; display: block; margin-bottom: 5px; color: #0277bd;">Total Rodado no Período (KM)</label>
            <input type="number" id="km-total" readonly style="width: 50%; padding: 10px; font-size: 18px; font-weight: bold; text-align: center; border: none; background-color: #fff; color: #333;">
        </div>

        <button type="button" style="background-color: #28a745; color: white; border: none; padding: 12px; font-size: 16px; font-weight: bold; border-radius: 4px; cursor: pointer;">
            Salvar Lançamento
        </button>
    </form>
</div>

<!-- Script para calcular automaticamente o KM -->
<script>
    function calcularKM() {
        // Pega os valores digitados
        let kmInicial = parseFloat(document.getElementById('km-inicial').value) || 0;
        let kmFinal = parseFloat(document.getElementById('km-final').value) || 0;
        let kmTotal = document.getElementById('km-total');

        // Calcula a diferença apenas se o KM Final for maior que o KM Inicial
        if (kmFinal > kmInicial && kmInicial > 0) {
            kmTotal.value = kmFinal - kmInicial;
        } else {
            kmTotal.value = ''; // Fica em branco se a conta ainda não for possível
        }
    }
</script>
