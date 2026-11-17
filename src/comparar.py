"""Ejecución de CPLEX
Uso:
  python src/comparar.py --time-limit 600
  python src/comparar.py --solo-lp
  python src/comparar.py --solo-graficos resultados/carpeta_resultados
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

from instancia import auditar_instancia, cargar_instancia
from modelo_cplex import resolver_cplex

RAIZ = Path(__file__).resolve().parent.parent
INSTANCIAS = [RAIZ / "instancias" / "A_capacidad.json", RAIZ / "instancias" / "C_clusters.json"]


def _fmt(val: float | int | None, dec: int = 2) -> str:
    if val is None:
        return "N/D"
    return f"{val:,}".replace(",", " ") if isinstance(val, int) else f"{val:.{dec}f}"


def _etiquetar_barras(ax, barras, dec: int = 2) -> None:
    for b in barras:
        h = b.get_height()
        ax.text(b.get_x() + b.get_width() / 2, h, f"{h:.{dec}f}", ha="center", va="bottom", fontsize=9)


def generar_graficos(filas_lp: list[dict], filas_mip: list[dict], carpeta: Path) -> None:
    """Genera gráficos de barras únicamente con las instancias ejecutadas (A y C)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    graf_dir = carpeta / "graficos"
    graf_dir.mkdir(parents=True, exist_ok=True)

    if filas_lp:
        insts = [f["instancia"] for f in filas_lp]
        fig, ejes = plt.subplots(1, 2, figsize=(9.5, 4))
        b0 = ejes[0].bar(insts, [f["z_LP"] for f in filas_lp], color="#d62728", width=0.5)
        _etiquetar_barras(ejes[0], b0, 2)
        ejes[0].set_title("CPLEX LP: z_LP")
        ejes[0].set_ylim(0, max(f["z_LP"] for f in filas_lp) * 1.15)

        t_ms = [1000.0 * f["tiempo_wall_s"] for f in filas_lp]
        b1 = ejes[1].bar(insts, t_ms, color="#d62728", width=0.5)
        _etiquetar_barras(ejes[1], b1, 1)
        ejes[1].set_title("CPLEX LP: tiempo wall (ms)")
        ejes[1].set_ylim(0, max(t_ms) * 1.18 if max(t_ms) > 0 else 1)

        fig.suptitle("Relajación continua — CPLEX")
        fig.tight_layout()
        fig.savefig(graf_dir / "cplex_lp.png", dpi=160)
        plt.close(fig)

    if filas_mip:
        insts = [f["instancia"] for f in filas_mip]
        metricas = [("tiempo_s", "Tiempo solver (s)", 1), ("nodos", "Nodos explorados", 0),
                    ("gap_%", "Gap final (%)", 2), ("objetivo", "Valor objetivo", 2)]
        fig, ejes = plt.subplots(2, 2, figsize=(10, 6.8))
        for ax, (campo, titulo, dec) in zip(ejes.flat, metricas):
            vals = [f[campo] if f[campo] is not None else 0.0 for f in filas_mip]
            barras = ax.bar(insts, vals, color="#d62728", width=0.5)
            _etiquetar_barras(ax, barras, dec)
            ax.set_title(titulo)
            top = max(vals)
            ax.set_ylim(0, top * 1.15 if top > 0 else 1)
        fig.suptitle("Modelo entero (configuración por defecto) — CPLEX")
        fig.tight_layout()
        fig.savefig(graf_dir / "cplex_mip.png", dpi=160)
        plt.close(fig)


def escribir_csv(ruta: Path, filas: list[dict]) -> None:
    if not filas:
        return
    with open(ruta, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(filas[0]))
        w.writeheader()
        w.writerows(filas)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("instancias", nargs="*")
    p.add_argument("--time-limit", type=float, default=600.0)
    p.add_argument("--threads", type=int, default=None)
    p.add_argument("--solo-lp", action="store_true")
    p.add_argument("--solo-mip", action="store_true")
    p.add_argument("--solo-graficos", type=Path, default=None, help="Regenera los gráficos desde resumen.json de una carpeta existente")
    a = p.parse_args()

    if a.solo_graficos:
        data = json.loads((a.solo_graficos / "resumen.json").read_text(encoding="utf-8"))
        generar_graficos(data.get("relajacion", []), data.get("modelo_entero", []), a.solo_graficos)
        print(f"Gráficos regenerados en {a.solo_graficos / 'graficos'}")
        return

    rutas = [Path(r).resolve() for r in a.instancias] if a.instancias else INSTANCIAS
    carpeta = RAIZ / "resultados" / f"cplex_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    (carpeta / "logs").mkdir(parents=True, exist_ok=True)
    (carpeta / "soluciones").mkdir(exist_ok=True)

    auditorias, filas_lp, filas_mip = [], [], []
    for ruta in rutas:
        inst = cargar_instancia(ruta)
        auditorias.append(auditar_instancia(inst))
        print(f"{'=' * 70}\n{inst.resumen()}")

        if not a.solo_mip:
            lp, _ = resolver_cplex(inst, relajar=True, time_limit=a.time_limit, threads=a.threads, log_path=carpeta / "logs" / f"{inst.nombre}_lp.log")
            lp["z_LP"] = lp.pop("objetivo")
            filas_lp.append(lp)
            print(f"  [LP]  z_LP={lp['z_LP']:.4f}, t_wall={lp['tiempo_wall_s']:.4f} s, iter={lp['iteraciones']}")

        if not a.solo_lp:
            mip, sol = resolver_cplex(inst, relajar=False, time_limit=a.time_limit, threads=a.threads, log_path=carpeta / "logs" / f"{inst.nombre}_mip.log")
            if sol:
                (carpeta / "soluciones" / f"{inst.nombre}_cplex.json").write_text(
                    json.dumps({**mip, "rutas": {f"r{r}_d{t}": v["camino"] for (r, t), v in sol["rutas"].items()}, "asignacion": {str(i): r for i, r in sol["asignacion"].items()}}, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
            filas_mip.append(mip)
            print(f"  [MIP] {mip['estado']}, obj={_fmt(mip['objetivo'])}, cota={_fmt(mip['cota'])}, gap={_fmt(mip['gap_%'], 3)}%, t={mip['tiempo_s']:.2f} s, nodos={mip['nodos']}, valida={mip['valida']}")

    escribir_csv(carpeta / "relajacion_cplex.csv", filas_lp)
    escribir_csv(carpeta / "milp_cplex.csv", filas_mip)
    generar_graficos(filas_lp, filas_mip, carpeta)
    (carpeta / "resumen.json").write_text(
        json.dumps({"auditoria": auditorias, "relajacion": filas_lp, "modelo_entero": filas_mip}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\nGuardado en {carpeta}")


if __name__ == "__main__":
    main()
