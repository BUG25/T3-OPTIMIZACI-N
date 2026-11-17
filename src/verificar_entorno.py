"""Verificación rápida de instancias y entorno CPLEX/docplex."""
from __future__ import annotations

import sys
from pathlib import Path

from instancia import auditar_instancia, cargar_instancia

RAIZ = Path(__file__).resolve().parent.parent


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    print("=== Instancias ===")
    for ruta in sorted((RAIZ / "instancias").glob("*.json")):
        info = auditar_instancia(cargar_instancia(ruta))
        print(f"  {ruta.name:26s} | C={info['clientes']:2d} | T={info['dias']} | R={info['rutas']} | OK={info['cumple_criterios']}")

    print("\n=== CPLEX / docplex ===")
    try:
        import cplex
        import docplex
        from docplex.mp.model import Model

        print(f"  docplex={getattr(docplex, '__version__', '?')}, cplex={cplex.Cplex().get_version()}")
        m = Model("test")
        x = m.binary_var_list(1200, name="x")
        m.add_constraint(m.sum(x) >= 1)
        m.minimize(x[0])
        sol = m.solve(log_output=False)
        m.end()
        print(f"  Prueba 1200 vars: OK (obj={sol.objective_value})")
    except Exception as exc:
        print(f"  ERROR CPLEX: {exc}")


if __name__ == "__main__":
    main()
