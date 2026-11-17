# TAREA 3 DE OPTIMIZACIÓN — ConVRP en CPLEX

Implementación en **CPLEX** del mismo modelo de ruteo consistente trabajado en la Tarea Computacional 2 (basado en Campelo et al., 2019)

## Estructura

```
docs/modelo.md             Formulación algebraica completa
instancias/                Instancias de TC2 (principales: A_capacidad.json y C_clusters.json)
resultados/                Salidas de CPLEX (CSV, JSON, logs y gráficos PNG)
src/instancia.py           Lector JSON -> Instancia y auditoría
src/validar.py             Reconstrucción y validación independiente de rutas
src/modelo_cplex.py        Modelo PLEM y cálculo de Big-M en docplex/CPLEX
src/verificar_entorno.py   Verificación de instancias y licencia de CPLEX
src/comparar.py            Ejecución de CPLEX (LP + MIP) y generación de gráficos
```

## Requisitos y configuración

```bash
pip install -r requirements.txt
docplex config --upgrade "C:\Program Files\IBM\ILOG\CPLEX_Studio222"
```

## Uso

```bash
python src/verificar_entorno.py
python src/comparar.py --time-limit 600
```
