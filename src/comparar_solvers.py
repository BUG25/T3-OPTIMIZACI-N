"""Comparación Gurobi vs. CPLEX sobre las mismas instancias (TC3).

Para cada instancia y cada solver:
  1. Relajación continua (X, Z en [0,1]): objetivo y tiempo (mediana de --reps-lp corridas).
  2. Modelo entero con parámetros POR DEFECTO (solo se fijan Threads y TimeLimit):
     objetivo, cota, gap, nodos, tiempo y validación independiente de la solución.
Guarda logs de cada solver (.log), CSV, JSON, gráficos y un archivo con el entorno.

Uso (desde la raíz del repo):
    python src/comparar_solvers.py                      # A y C, Threads=1, TimeLimit=600
    python src/comparar_solvers.py --solo-lp            # solo relajaciones (segundos)
    python src/comparar_solvers.py --threads 0          # 0 = todos los hilos (corrida complementaria)
    python src/comparar_solvers.py instancias/B_ventanas.json --time-limit 120

Requiere src/modelo_gurobi.py (copia sin cambios de TC2/src/modelo.py) y src/modelo_cplex.py.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import statistics
import sys
from datetime import datetime
from pathlib import Path

from instancia import auditar_instancia, cargar_instancia
from modelo_cplex import resolver_cplex
from validar import extraer_solucion, validar_solucion

RAIZ = Path(__file__).resolve().parent.parent
INSTANCIAS = [RAIZ / "instancias" / "A_capacidad.json", RAIZ / "instancias" / "C_clusters.json"]
GRB_ESTADOS = {2: "OPTIMAL", 3: "INFEASIBLE", 4: "INF_OR_UNBD", 5: "UNBOUNDED",
               9: "TIME_LIMIT", 11: "INTERRUPTED", 13: "SUBOPTIMAL"}


# ----------------------------------------------------------------------------
# Gurobi
# ----------------------------------------------------------------------------
class _SolGurobi:
    """Adapta un modelo de Gurobi a la interfaz que usa validar.extraer_solucion (docplex)."""

    def __init__(self, m):
        self._m = m

    def get_value(self, var) -> float:
        return float(var.X)

    @property
    def objective_value(self) -> float:
        return float(self._m.ObjVal)


def resolver_gurobi(inst, relajar: bool, time_limit: float, threads: int, log_path: Path | None):
    import gurobipy as gp
    from modelo_gurobi import build_model

    mod = build_model(inst, verbose=False)
    m = mod.m.relax() if relajar else mod.m
    m.Params.OutputFlag = 1
    m.Params.LogToConsole = 0
    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.unlink(missing_ok=True)       # LogFile de Gurobi agrega al final, no sobrescribe
        m.Params.LogFile = str(log_path)
    m.Params.Threads = threads
    m.Params.TimeLimit = time_limit
    m.optimize()

    hay_sol = m.SolCount > 0
    res = {
        "estado": GRB_ESTADOS.get(m.Status, str(m.Status)),
        "objetivo": m.ObjVal if hay_sol else None,
        "cota": None, "gap_%": None, "nodos": 0,
        "tiempo_s": float(m.Runtime), "iteraciones": int(m.IterCount),
        "n_vars": m.NumVars, "n_restr": m.NumConstrs,
        "valida": False, "errores_validacion": [],
    }
    if not relajar:
        res["cota"] = float(m.ObjBound)
        res["gap_%"] = 100.0 * m.MIPGap if hay_sol else None
        res["nodos"] = int(m.NodeCount)
        if hay_sol:
            sol = extraer_solucion(mod, _SolGurobi(m))
            res["errores_validacion"] = validar_solucion(inst, sol)
            res["valida"] = not res["errores_validacion"]
    res["version"] = ".".join(map(str, gp.gurobi.version()))
    m.dispose()
    return res


# ----------------------------------------------------------------------------
# Utilidades
# ----------------------------------------------------------------------------
def version_cplex() -> str:
    try:
        import cplex
        return cplex.Cplex().get_version()
    except Exception:
        return "?"


def escribir_csv(ruta: Path, filas: list[dict]) -> None:
    if not filas:
        return
    campos = list(dict.fromkeys(k for f in filas for k in f))
    with open(ruta, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=campos)
        w.writeheader()
        w.writerows(filas)


def dif_rel(a: float | None, b: float | None) -> float | None:
    if a is None or b is None:
        return None
    return abs(a - b) / max(1.0, abs(a), abs(b))


def fmt(v, dec=2) -> str:
    return "N/D" if v is None else (f"{v:.{dec}f}" if isinstance(v, float) else str(v))


def guardar_entorno(carpeta: Path, a) -> None:
    import gurobipy as gp
    lineas = [
        f"fecha: {datetime.now().isoformat(timespec='seconds')}",
        f"equipo: {platform.node()} | {platform.platform()} | {platform.processor()} | cpu_count={os.cpu_count()}",
        f"python: {sys.version.split()[0]}",
        f"gurobi: {'.'.join(map(str, gp.gurobi.version()))}",
        f"cplex: {version_cplex()}",
        f"threads={a.threads} (0 = automático) | time_limit={a.time_limit}s | reps_lp={a.reps_lp}",
        "parámetros: por defecto en ambos solvers salvo Threads y TimeLimit",
        "CPLEX: clocktype=2 (tiempo de pared), igual que el TimeLimit de Gurobi",
    ]
    (carpeta / "entorno.txt").write_text("\n".join(lineas) + "\n", encoding="utf-8")


def generar_graficos(comp: list[dict], carpeta: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    col = {"Gurobi": "#2878a5", "CPLEX": "#d9822b"}
    paneles = [("LP_tiempo_ms", "Relajación: tiempo (ms)", 1), ("MIP_tiempo_s", "Entero: tiempo (s)", 1),
               ("MIP_nodos", "Entero: nodos explorados", 0), ("MIP_gap_%", "Entero: gap final (%)", 2),
               ("MIP_objetivo", "Entero: valor objetivo", 2), ("LP_obj", "Relajación: z_LP", 2)]
    insts = [c["instancia"] for c in comp]
    fig, ejes = plt.subplots(2, 3, figsize=(13, 7))
    for ax, (campo, titulo, dec) in zip(ejes.flat, paneles):
        w = 0.38
        for k, solver in enumerate(("Gurobi", "CPLEX")):
            vals = [c[f"{campo}_{solver}"] or 0.0 for c in comp]
            xs = [i + (k - 0.5) * w for i in range(len(insts))]
            barras = ax.bar(xs, vals, w, label=solver, color=col[solver])
            for b, v in zip(barras, vals):
                ax.text(b.get_x() + b.get_width() / 2, v, f"{v:.{dec}f}", ha="center", va="bottom", fontsize=8)
        ax.set_xticks(range(len(insts)), insts, fontsize=8)
        ax.set_title(titulo, fontsize=10)
        ax.margins(y=0.15)
    ejes[0, 0].legend()
    fig.suptitle("Gurobi vs. CPLEX — parámetros por defecto")
    fig.tight_layout()
    fig.savefig(carpeta / "comparacion_gurobi_cplex.png", dpi=160)
    plt.close(fig)


# ----------------------------------------------------------------------------
def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("instancias", nargs="*")
    p.add_argument("--time-limit", type=float, default=600.0)
    p.add_argument("--threads", type=int, default=1, help="1 = comparación controlada (por defecto); 0 = automático")
    p.add_argument("--reps-lp", type=int, default=5, help="repeticiones de la relajación (se reporta la mediana)")
    p.add_argument("--solo-lp", action="store_true")
    p.add_argument("--solo-mip", action="store_true")
    a = p.parse_args()

    rutas = [Path(r).resolve() for r in a.instancias] if a.instancias else INSTANCIAS
    carpeta = RAIZ / "resultados" / f"comparacion_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    (carpeta / "logs").mkdir(parents=True, exist_ok=True)
    guardar_entorno(carpeta, a)
    hilos = a.threads if a.threads > 0 else None     # resolver_cplex: None = automático
    hilos_grb = a.threads                             # Gurobi: 0 = automático

    filas, comp = [], []
    for ruta in rutas:
        inst = cargar_instancia(ruta)
        print(f"{'=' * 78}\n{inst.resumen()}\n  auditoría: {auditar_instancia(inst)}")
        c = {"instancia": inst.nombre}

        # ---- 1) Relajación continua -------------------------------------------------
        if not a.solo_mip:
            for solver in ("Gurobi", "CPLEX"):
                tiempos, lp = [], None
                for k in range(a.reps_lp):
                    log = carpeta / "logs" / f"{inst.nombre}_{solver.lower()}_lp.log" if k == 0 else None
                    if solver == "Gurobi":
                        r = resolver_gurobi(inst, True, a.time_limit, hilos_grb, log)
                    else:
                        r, _ = resolver_cplex(inst, relajar=True, time_limit=a.time_limit, threads=hilos, log_path=log)
                    tiempos.append(r["tiempo_s"])
                    lp = lp or r
                lp_fila = {"solver": solver, "tipo": "LP", "instancia": inst.nombre, "estado": lp["estado"],
                           "objetivo": lp["objetivo"], "tiempo_mediana_ms": 1000 * statistics.median(tiempos),
                           "tiempo_min_ms": 1000 * min(tiempos), "tiempo_max_ms": 1000 * max(tiempos),
                           "iteraciones": lp["iteraciones"], "n_vars": lp["n_vars"], "n_restr": lp["n_restr"]}
                filas.append(lp_fila)
                c[f"LP_obj_{solver}"] = lp["objetivo"]
                c[f"LP_tiempo_ms_{solver}"] = lp_fila["tiempo_mediana_ms"]
                print(f"  [LP  {solver:6s}] z_LP={lp['objetivo']:.4f}  t_mediana={lp_fila['tiempo_mediana_ms']:.1f} ms  "
                      f"iter={lp['iteraciones']}  vars={lp['n_vars']} restr={lp['n_restr']}")
            d = dif_rel(c["LP_obj_Gurobi"], c["LP_obj_CPLEX"])
            c["LP_dif_rel"] = d
            print(f"  >> diferencia relativa z_LP Gurobi vs CPLEX = {d:.2e}  "
                  f"({'OK, mismo modelo' if d is not None and d < 1e-6 else 'REVISAR'})")

        # ---- 2) Modelo entero, parámetros por defecto -------------------------------
        if not a.solo_lp:
            for solver in ("Gurobi", "CPLEX"):
                log = carpeta / "logs" / f"{inst.nombre}_{solver.lower()}_mip.log"
                if solver == "Gurobi":
                    r = resolver_gurobi(inst, False, a.time_limit, hilos_grb, log)
                else:
                    r, sol = resolver_cplex(inst, relajar=False, time_limit=a.time_limit, threads=hilos, log_path=log)
                filas.append({"solver": solver, "tipo": "MIP", "instancia": inst.nombre,
                              **{k: r[k] for k in ("estado", "objetivo", "cota", "gap_%", "tiempo_s", "nodos",
                                                   "iteraciones", "valida", "n_vars", "n_restr")}})
                for k_src, k_dst in (("objetivo", "MIP_objetivo"), ("cota", "MIP_cota"), ("gap_%", "MIP_gap_%"),
                                     ("tiempo_s", "MIP_tiempo_s"), ("nodos", "MIP_nodos"), ("estado", "MIP_estado")):
                    c[f"{k_dst}_{solver}"] = r[k_src]
                print(f"  [MIP {solver:6s}] {r['estado']:10s} obj={fmt(r['objetivo'])} cota={fmt(r['cota'])} "
                      f"gap={fmt(r['gap_%'], 3)}% t={r['tiempo_s']:.1f}s nodos={r['nodos']} válida={r['valida']}")
            d = dif_rel(c["MIP_objetivo_Gurobi"], c["MIP_objetivo_CPLEX"])
            c["MIP_dif_rel_obj"] = d
            if d is not None:
                print(f"  >> diferencia relativa de objetivos = {d:.2e}")
        comp.append(c)

    escribir_csv(carpeta / "detalle.csv", filas)
    escribir_csv(carpeta / "comparacion.csv", comp)
    (carpeta / "resumen.json").write_text(json.dumps({"detalle": filas, "comparacion": comp}, indent=2,
                                                      ensure_ascii=False, default=str), encoding="utf-8")
    if not a.solo_lp and not a.solo_mip:
        generar_graficos(comp, carpeta)
    print(f"\nResultados y logs en {carpeta}")


if __name__ == "__main__":
    main()