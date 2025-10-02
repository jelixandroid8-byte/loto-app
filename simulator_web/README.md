# Simulador financiero - LotoWeb (web UI)

Pequeña app Flask para ejecutar simulaciones Monte Carlo desde una página web y ver resultados.

Cómo ejecutar localmente:

1. Crear un entorno virtual e instalar dependencias:

```powershell
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements_web.txt
```

2. Ejecutar la app:

```powershell
set FLASK_APP=app.py
venv\Scripts\python.exe app.py
```

3. Abrir en el navegador: http://localhost:5001

Archivos importantes:
- `simulator_web/app.py` - servidor Flask
- `simulator_web/sim_logic.py` - lógica de simulación
- `simulator_web/templates/` - plantillas HTML

Notas:
- El formulario expone variables clave: meses, simulaciones, ventas por sorteo, sorteos por semana, % billetes, clientes estimados, costos fijos y costos variables.
- El backend corre las simulaciones y devuelve estadísticas y una muestra de resultados.
