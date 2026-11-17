"""Extracción y validación independiente de soluciones del ConVRP."""
from __future__ import annotations

from instancia import Instancia

TOL = 1e-4


def extraer_solucion(mod, sol) -> dict:
    """Reconstruye asignación y rutas desde una SolveSolution de docplex."""
    inst = mod.inst
    z_vals = {k: float(sol.get_value(v)) for k, v in mod.Z.items()}
    x_vals = {k: float(sol.get_value(v)) for k, v in mod.X.items()}
    asign = {i: r for r in inst.rutas for i in inst.clientes if z_vals.get((r, i), 0.0) > 0.5}
    rutas = {}
    for t in inst.dias:
        for r in inst.rutas:
            suc = {i: j for (rr, i, j, tt), val in x_vals.items() if rr == r and tt == t and val > 0.5}
            camino = [0]
            if 0 in suc:
                act = suc[0]
                while act != 0 and len(camino) <= len(inst.clientes) + 1:
                    camino.append(act)
                    act = suc.get(act, 0)
                camino.append(0)
            rutas[r, t] = {
                "camino": camino,
                "arcos": suc,
                "salida": float(sol.get_value(mod.S[r])),
                "retorno": float(sol.get_value(mod.F[r, t])),
                "llegadas": {i: float(sol.get_value(mod.A[i, t])) for i in camino[1:-1]},
            }
    return {"asignacion": asign, "z_vals": z_vals, "rutas": rutas, "objetivo": float(sol.objective_value)}


def validar_solucion(inst: Instancia, sol: dict) -> list[str]:
    """Devuelve lista de errores encontrados"""
    errores: list[str] = []
    asign, z_vals = sol["asignacion"], sol["z_vals"]
    for i in inst.clientes:
        n = sum(z_vals.get((r, i), 0.0) > 0.5 for r in inst.rutas)
        if n != 1:
            errores.append(f"Cliente {i} asignado a {n} rutas")

    dist_total = 0.0
    for (r, t), ruta in sol["rutas"].items():
        camino, vis = ruta["camino"], ruta["camino"][1:-1]
        if len(ruta["arcos"]) != max(0, len(camino) - 1):
            errores.append(f"Ruta {r} día {t}: subtour detectado")
        if len(set(vis)) != len(vis):
            errores.append(f"Ruta {r} día {t}: cliente repetido")
        esperados = {i for i in inst.N(t) if asign.get(i) == r}
        if set(vis) != esperados:
            errores.append(f"Ruta {r} día {t}: visita {sorted(vis)} ≠ esperado {sorted(esperados)}")
        carga = sum(inst.demanda[i, t] for i in vis)
        if carga > inst.Q + TOL:
            errores.append(f"Ruta {r} día {t}: carga {carga} > Q={inst.Q}")
        if not vis:
            continue

        S, F, A = ruta["salida"], ruta["retorno"], ruta["llegadas"]
        if S < inst.E - TOL or F > inst.L + TOL:
            errores.append(f"Ruta {r} día {t}: fuera de horario [{inst.E}, {inst.L}]")
        prev, listo = 0, S
        for i in vis:
            if A[i] < listo + inst.tiempo(prev, i) - TOL:
                errores.append(f"Ruta {r} día {t}: llegada anticipada a {i}")
            if inst.tiene_ventana(i):
                a, b = inst.ventana[i]
                if not (a - TOL <= A[i] <= b + TOL):
                    errores.append(f"Cliente {i} día {t}: {A[i]:.1f} fuera de [{a}, {b}]")
            prev, listo = i, A[i] + inst.servicio[i]
        if F < listo + inst.tiempo(prev, 0) - TOL:
            errores.append(f"Ruta {r} día {t}: retorno inconsistente")
        dist_total += sum(inst.dist[a, b] for a, b in zip(camino, camino[1:]))

    if abs(dist_total - sol["objetivo"]) > 1e-3 * max(1.0, sol["objetivo"]):
        errores.append(f"Distancia {dist_total:.2f} ≠ objetivo {sol['objetivo']:.2f}")
    return errores


def imprimir_solucion(inst: Instancia, sol: dict) -> None:
    print(f"\nDistancia total: {sol['objetivo']:.2f}")
    for r in inst.rutas:
        fijos = sorted(i for i, rr in sol["asignacion"].items() if rr == r)
        print(f"\nRuta {r} (clientes: {fijos})")
        for t in inst.dias:
            ruta = sol["rutas"][r, t]
            if len(ruta["camino"]) <= 2:
                print(f"  Día {t}: no sale")
                continue
            vis = ruta["camino"][1:-1]
            carga = sum(inst.demanda[i, t] for i in vis)
            pasos = " → ".join("D" if i == 0 else f"{i}@{ruta['llegadas'][i]:.0f}" for i in ruta["camino"])
            sale = max(inst.E, ruta["llegadas"][vis[0]] - inst.tiempo(0, vis[0]))
            vuelve = ruta["llegadas"][vis[-1]] + inst.servicio[vis[-1]] + inst.tiempo(vis[-1], 0)
            print(f"  Día {t}: {pasos}  | carga {carga:.0f}/{inst.Q:.0f}, sale ≤{sale:.0f}, vuelve ≥{vuelve:.0f}")
