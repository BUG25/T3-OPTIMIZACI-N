from __future__ import annotations

import argparse
import contextlib
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

from instancia import Instancia, cargar_instancia
from validar import extraer_solucion, imprimir_solucion, validar_solucion

ESTADOS = {
    1: "OPTIMAL", 101: "OPTIMAL", 102: "OPTIMAL",
    10: "ITER_LIMIT", 11: "TIME_LIMIT", 107: "TIME_LIMIT", 108: "TIME_LIMIT",
    3: "INFEASIBLE", 103: "INFEASIBLE", 2: "UNBOUNDED", 118: "UNBOUNDED",
}


@dataclass
class ModeloCPLEX:
    m: object
    inst: Instancia
    X: dict
    Z: dict
    A: dict
    S: dict
    F: dict
    big_m: dict[tuple[int, int], float]


def calcular_big_m(inst: Instancia) -> dict[tuple[int, int], float]:
    """Calcula las constantes Big-M calibradas según ventanas efectivas"""
    vent = {}
    for i in inst.clientes:
        a, b = inst.ventana[i] if inst.tiene_ventana(i) else (inst.E, inst.L)
        lo = max(a, inst.E + inst.tiempo(0, i))
        hi = min(b, inst.L - inst.servicio[i] - inst.tiempo(i, 0))
        if lo > hi + 1e-9:
            raise ValueError(f"Cliente {i} inatendible: [{lo:.1f}, {hi:.1f}]")
        vent[i] = (lo, hi)

    s, t = inst.servicio, inst.tiempo
    M: dict[tuple[int, int], float] = {}
    for i in inst.clientes:
        for j in inst.clientes:
            if i != j:
                M[i, j] = max(0.0, vent[i][1] + s[i] + t(i, j) - vent[j][0])
        M[0, i] = max(0.0, inst.L + t(0, i) - vent[i][0])
        M[i, 0] = max(0.0, vent[i][1] + s[i] + t(i, 0) - inst.E)
    return M


def build_model_cplex(inst: Instancia, relajar: bool = False) -> ModeloCPLEX:
    """Construye el modelo ConVRP en docplex """
    from docplex.mp.model import Model

    m = Model(name=f"ConVRP_{inst.nombre}")
    R, T, C = inst.rutas, inst.dias, inst.clientes
    s, q, Q, E, L = inst.servicio, inst.demanda, inst.Q, inst.E, inst.L
    M = calcular_big_m(inst)

    idx_x = [(r, i, j, t) for t in T for (i, j) in inst.arcos(t) for r in R]
    idx_z = [(r, i) for r in R for i in C]
    if relajar:
        X = {k: m.continuous_var(lb=0, ub=1, name=f"X_{k[0]}_{k[1]}_{k[2]}_{k[3]}") for k in idx_x}
        Z = {k: m.continuous_var(lb=0, ub=1, name=f"Z_{k[0]}_{k[1]}") for k in idx_z}
    else:
        X = {k: m.binary_var(name=f"X_{k[0]}_{k[1]}_{k[2]}_{k[3]}") for k in idx_x}
        Z = {k: m.binary_var(name=f"Z_{k[0]}_{k[1]}") for k in idx_z}

    A = {(i, t): m.continuous_var(lb=E, ub=L, name=f"A_{i}_{t}") for t in T for i in inst.N(t)}
    S = {r: m.continuous_var(lb=E, ub=L, name=f"S_{r}") for r in R}
    F = {(r, t): m.continuous_var(lb=E, ub=L, name=f"F_{r}_{t}") for r in R for t in T}

    # (1) Objetivo y (2) Asignación única
    m.minimize(m.sum(inst.dist[i, j] * X[r, i, j, t] for (r, i, j, t) in idx_x))
    m.add_constraints((m.sum(Z[r, i] for r in R) == 1 for i in C), names=[f"asig_{i}" for i in C])

    for t in T:
        Nt, Vt = inst.N(t), inst.V(t)
        # (3)-(4) Grado de salida/entrada solo en clientes con demanda en t
        m.add_constraints(m.sum(X[r, i, j, t] for j in Vt if j != i) == Z[r, i] for r in R for i in Nt)
        m.add_constraints(m.sum(X[r, j, i, t] for j in Vt if j != i) == Z[r, i] for r in R for i in Nt)
        # (5) Salida del depósito
        m.add_constraints(m.sum(X[r, 0, j, t] for j in Nt) <= 1 for r in R)
        # (7) Tiempo de llegada (Big-M) y eliminación de subtours
        m.add_constraints(
            A[j, t] >= A[i, t] + s[i] + inst.tiempo(i, j) - M[i, j] * (1 - m.sum(X[r, i, j, t] for r in R))
            for i in Nt for j in Nt if i != j
        )
        # (8) Ventanas de tiempo
        for i in Nt:
            if inst.tiene_ventana(i):
                a, b = inst.ventana[i]
                m.add_constraint(A[i, t] >= a)
                m.add_constraint(A[i, t] <= b)
        # (9)-(10) Salida y retorno al depósito
        m.add_constraints(A[j, t] >= S[r] + inst.tiempo(0, j) - M[0, j] * (1 - X[r, 0, j, t]) for r in R for j in Nt)
        m.add_constraints(F[r, t] >= A[i, t] + s[i] + inst.tiempo(i, 0) - M[i, 0] * (1 - X[r, i, 0, t]) for r in R for i in Nt)

    # (11)-(12) Horario del depósito y (14) Capacidad
    m.add_constraints(S[r] >= E for r in R)
    m.add_constraints(F[r, t] <= L for r in R for t in T)
    m.add_constraints(m.sum(q[i, t] * Z[r, i] for i in inst.N(t)) <= Q for r in R for t in T)
    return ModeloCPLEX(m=m, inst=inst, X=X, Z=Z, A=A, S=S, F=F, big_m=M)


def resolver_cplex(
    inst: Instancia,
    relajar: bool = False,
    time_limit: float | None = 600.0,
    threads: int | None = None,
    log_path: Path | None = None,
    verbose: bool = False,
) -> tuple[dict, dict | None]:
    """Resuelve la relajación LP o el MIP por defecto en CPLEX"""
    mod = build_model_cplex(inst, relajar=relajar)
    m = mod.m
    try:
        if time_limit is not None:
            m.parameters.timelimit = time_limit
        if threads is not None:
            m.parameters.threads = threads
            m.parameters.clocktype = 2   # tiempo de pared, igual que el TimeLimit de Gurobi

        t0 = perf_counter()
        if log_path is not None:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "w", encoding="utf-8") as fh:
                sol = m.solve(log_output=fh)
        else:
            sol = m.solve(log_output=verbose)
        wall_s = perf_counter() - t0

        sd = m.solve_details
        estado = ESTADOS.get(sd.status_code, sd.status or str(sd.status_code))
        obj = float(sol.objective_value) if sol is not None else None
        cota = float(sd.best_bound) if sd.best_bound is not None and not math.isnan(sd.best_bound) and abs(sd.best_bound) < 1e19 else None

        gap_pct = None
        if not relajar and obj is not None:
            gap_raw = getattr(sd, "mip_relative_gap", None)
            gap_pct = 100.0 * float(gap_raw) if gap_raw is not None and not math.isnan(gap_raw) else (
                100.0 * abs(obj - cota) / abs(obj) if cota is not None and abs(obj) > 1e-12 else None
            )

        iteraciones = getattr(sd, "nb_iterations", 0) or 0
        if not iteraciones:
            with contextlib.suppress(Exception):
                iteraciones = int(m.get_cplex().solution.progress.get_num_iterations())

        xs = [float(sol.get_value(v)) for v in mod.X.values()] if sol is not None else []
        x_frac = 100.0 * sum(1e-6 < x < 1 - 1e-6 for x in xs) / max(1, len(xs)) if xs else 0.0

        sol_dict = extraer_solucion(mod, sol) if (sol is not None and not relajar) else None
        errores = validar_solucion(inst, sol_dict) if sol_dict is not None else []

        res = {
            "instancia": inst.nombre,
            "n_vars": int(m.number_of_variables),
            "n_bin": int(m.number_of_binary_variables),
            "n_restr": int(m.number_of_constraints),
            "estado": estado,
            "estado_raw": sd.status,
            "objetivo": obj,
            "cota": cota,
            "gap_%": gap_pct,
            "tiempo_s": float(sd.time) if sd.time is not None else float(wall_s),
            "tiempo_wall_s": float(wall_s),
            "nodos": int(getattr(sd, "nb_nodes_processed", 0) or 0),
            "iteraciones": int(iteraciones),
            "x_fraccionales_%": x_frac,
            "valida": (not errores) if sol_dict is not None else False,
            "errores_validacion": errores,
        }
        return res, sol_dict
    except Exception as exc:
        if "1016" in str(exc) or "Community Edition" in str(exc):
            raise RuntimeError("CPLEX Community Edition excedió el límite de 1000 variables/restricciones.") from exc
        raise
    finally:
        with contextlib.suppress(Exception):
            m.end()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="Resuelve una instancia ConVRP en CPLEX.")
    p.add_argument("instancia")
    p.add_argument("--time-limit", type=float, default=600.0)
    p.add_argument("--threads", type=int, default=None)
    p.add_argument("--relajar", action="store_true")
    p.add_argument("--silencioso", action="store_true")
    a = p.parse_args()

    inst = cargar_instancia(a.instancia)
    print(inst.resumen())
    res, sol = resolver_cplex(inst, relajar=a.relajar, time_limit=a.time_limit, threads=a.threads, verbose=not a.silencioso)
    if sol:
        imprimir_solucion(inst, sol)
        print("\nValidación:", "OK" if res["valida"] else "; ".join(res["errores_validacion"]))
    print(f"\n[CPLEX {'LP' if a.relajar else 'MIP'}] {res['estado']}, obj={res['objetivo']}, "
          f"gap={res['gap_%']}%, nodos={res['nodos']}, t={res['tiempo_s']:.2f} s")
