
"""Grafica las instancias (requisito de la presentación de TC3).
 
Un panel por día: depósito, clientes con pedido ese día (tamaño ∝ demanda) y clientes sin pedido
(gris, no se visitan). Los clientes con ventana de tiempo llevan borde grueso y su ventana escrita.
Un último panel muestra cuántos días pide cada cliente (la estructura multi-día).
 
Uso (desde la raíz del repo):
    python src/graficar_instancias.py                  # A y C
    python src/graficar_instancias.py instancias/B_ventanas.json
Guarda resultados/instancias/<nombre>.png
"""
from __future__ import annotations
 
import argparse
import sys
from pathlib import Path
 
from instancia import cargar_instancia
 
RAIZ = Path(__file__).resolve().parent.parent
INSTANCIAS = [RAIZ / "instancias" / "A_capacidad.json", RAIZ / "instancias" / "C_clusters.json"]
 
 
def graficar(inst, salida: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
 
    dias = list(inst.dias)
    fig, ejes = plt.subplots(1, len(dias) + 1, figsize=(4.6 * (len(dias) + 1), 4.8))
    qmax = max(inst.demanda.values())
    for t, ax in zip(dias, ejes):
        for i in inst.clientes:
            x, y = inst.coords[i]
            q = inst.demanda.get((i, t), 0)
            if q > 0:
                ax.scatter(x, y, s=30 + 170 * q / qmax, color="#2878a5", alpha=0.85,
                           edgecolor="black" if inst.tiene_ventana(i) else "none",
                           linewidth=2.2 if inst.tiene_ventana(i) else 0, zorder=3)
                txt = f"{i}\nq={q:.0f}"
                if inst.tiene_ventana(i):
                    a, b = inst.ventana[i]
                    txt += f"\n[{a:.0f},{b:.0f}]"
                ax.annotate(txt, (x, y), textcoords="offset points", xytext=(5, 5), fontsize=6)
            else:
                ax.scatter(x, y, s=25, color="#bbbbbb", marker="x", zorder=2)
        ax.scatter(*inst.coords[0], marker="s", s=120, color="#d62728", zorder=4, label="depósito")
        ax.set_title(f"Día {t}: {len(inst.N(t))} clientes, demanda {sum(inst.demanda.get((i, t), 0) for i in inst.clientes):.0f}"
                     f" (Q·R = {inst.Q * inst.n_rutas:.0f})", fontsize=9)
        ax.set_xlabel("Coordenada x (unidades de distancia)", fontsize=8)
        ax.set_ylabel("Coordenada y (unidades de distancia)", fontsize=8)
        ax.set_aspect("equal", adjustable="datalim")
        ax.grid(alpha=0.25)
    # Leyenda de símbolos (debajo de la figura, para no tapar clientes)
    from matplotlib.lines import Line2D
    handles = [
        Line2D([], [], marker="s", color="w", markerfacecolor="#d62728", markersize=9, label="Depósito"),
        Line2D([], [], marker="o", color="w", markerfacecolor="#2878a5", markersize=8, label="Cliente con pedido (tamaño ∝ demanda q)"),
        Line2D([], [], marker="o", color="w", markerfacecolor="#2878a5", markeredgecolor="black", markeredgewidth=2,
               markersize=8, label="Cliente con ventana de tiempo [a,b]"),
        Line2D([], [], marker="x", color="#bbbbbb", linestyle="", markersize=7, label="Sin pedido ese día (no se visita)"),
    ]
    fig.legend(handles=handles, loc="lower center", ncol=4, fontsize=8, frameon=False)
    ax = ejes[-1]
    for i in inst.clientes:
        x, y = inst.coords[i]
        k = sum(inst.demanda.get((i, t), 0) > 0 for t in dias)
        ax.scatter(x, y, s=70, color=plt.cm.viridis(k / len(dias)), edgecolor="black" if inst.tiene_ventana(i) else "none",
                   linewidth=2 if inst.tiene_ventana(i) else 0, zorder=3)
        ax.annotate(f"{i}:{k}d", (x, y), textcoords="offset points", xytext=(4, 4), fontsize=6)
    ax.scatter(*inst.coords[0], marker="s", s=120, color="#d62728", zorder=4)
    ax.set_title("Días con pedido por cliente (borde = ventana)", fontsize=9)
    ax.set_xlabel("Coordenada x (unidades de distancia)", fontsize=8)
    ax.set_ylabel("Coordenada y (unidades de distancia)", fontsize=8)
    ax.text(0.02, 0.02, "etiqueta  i:kd  = cliente i pide k días de 3\ncolor: amarillo = 3 días, verde = 2 días",
            transform=ax.transAxes, fontsize=6, va="bottom", bbox=dict(facecolor="white", alpha=0.85, edgecolor="#cccccc"))
    ax.set_aspect("equal", adjustable="datalim")
    ax.grid(alpha=0.25)
    fig.suptitle(f"{inst.nombre}: {len(inst.clientes)} clientes, {inst.n_dias} días, {inst.n_rutas} rutas, "
                 f"Q={inst.Q:.0f}, depósito [{inst.E:.0f}, {inst.L:.0f}]", fontsize=11)
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    salida.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(salida, dpi=170)
    plt.close(fig)
 
 
if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("instancias", nargs="*")
    a = p.parse_args()
    for ruta in ([Path(r).resolve() for r in a.instancias] if a.instancias else INSTANCIAS):
        inst = cargar_instancia(ruta)
        out = RAIZ / "resultados" / "instancias" / f"{inst.nombre}.png"
        graficar(inst, out)
        print(f"{inst.nombre} -> {out}")
 