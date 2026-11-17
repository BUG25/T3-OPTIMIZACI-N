from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Instancia:
    nombre: str
    n_rutas: int
    n_dias: int
    Q: float
    E: float
    L: float
    coords: dict[int, tuple[float, float]]
    servicio: dict[int, float]
    ventana: dict[int, tuple[float, float] | None]
    demanda: dict[tuple[int, int], float]
    dist: dict[tuple[int, int], float] = field(default_factory=dict)

    @property
    def clientes(self) -> list[int]:
        return sorted(i for i in self.coords if i != 0)

    @property
    def rutas(self) -> range:
        return range(self.n_rutas)

    @property
    def dias(self) -> range:
        return range(self.n_dias)

    def N(self, t: int) -> list[int]:
        return [i for i in self.clientes if self.demanda.get((i, t), 0) > 0]

    def V(self, t: int) -> list[int]:
        return [0] + self.N(t)

    def arcos(self, t: int) -> list[tuple[int, int]]:
        Vt = self.V(t)
        return [(i, j) for i in Vt for j in Vt if i != j]

    def tiempo(self, i: int, j: int) -> float:
        return self.dist[i, j]

    def tiene_ventana(self, i: int) -> bool:
        return self.ventana.get(i) is not None

    def resumen(self) -> str:
        n_vent = sum(self.tiene_ventana(i) for i in self.clientes)
        lineas = [
            f"Instancia {self.nombre}: {len(self.clientes)} clientes, {self.n_dias} días, {self.n_rutas} rutas, Q={self.Q}",
            f"  Depósito [{self.E}, {self.L}]; con ventana: {n_vent}",
        ]
        for t in self.dias:
            dem = sum(self.demanda.get((i, t), 0) for i in self.clientes)
            lineas.append(f"  Día {t}: {len(self.N(t))} clientes, demanda {dem:.0f} ({dem / (self.n_rutas * self.Q):.0%})")
        return "\n".join(lineas)


def auditar_instancia(inst: Instancia) -> dict:
    """Verifica criterios mínimos y estructura """
    n = len(inst.clientes)
    todos = sum(all(inst.demanda.get((i, t), 0) > 0 for t in inst.dias) for i in inst.clientes)
    ok = n >= 15 and inst.n_dias >= 3 and inst.n_rutas >= 3 and todos < n
    return {
        "nombre": inst.nombre,
        "clientes": n,
        "dias": inst.n_dias,
        "rutas": inst.n_rutas,
        "clientes_con_ventana": sum(inst.tiene_ventana(i) for i in inst.clientes),
        "clientes_con_dias_sin_demanda": n - todos,
        "cumple_criterios": ok,
    }


def cargar_instancia(ruta: str | Path) -> Instancia:
    """Carga la instancia y calcula la matriz de distancias euclidianas"""
    datos = json.loads(Path(ruta).read_text(encoding="utf-8"))
    dep, n_dias = datos["deposito"], int(datos["n_dias"])
    coords = {0: (float(dep["x"]), float(dep["y"]))}
    servicio, ventana, demanda = {0: 0.0}, {0: None}, {}

    for c in datos["clientes"]:
        i = int(c["id"])
        if i == 0:
            raise ValueError("El id 0 está reservado para el depósito")
        coords[i] = (float(c["x"]), float(c["y"]))
        servicio[i] = float(c.get("servicio", 0))
        v = c.get("ventana")
        ventana[i] = (float(v[0]), float(v[1])) if v else None
        if len(c["demanda"]) != n_dias:
            raise ValueError(f"Cliente {i}: se esperaban {n_dias} demandas")
        for t, q in enumerate(c["demanda"]):
            if q > 0:
                demanda[i, t] = float(q)
        if not any(q > 0 for q in c["demanda"]):
            raise ValueError(f"Cliente {i} sin demanda en ningún día")

    inst = Instancia(
        nombre=datos.get("nombre", Path(ruta).stem),
        n_rutas=int(datos["n_rutas"]),
        n_dias=n_dias,
        Q=float(datos["capacidad"]),
        E=float(dep.get("apertura", 0)),
        L=float(dep["cierre"]),
        coords=coords,
        servicio=servicio,
        ventana=ventana,
        demanda=demanda,
    )
    for i, (xi, yi) in coords.items():
        for j, (xj, yj) in coords.items():
            if i != j:
                inst.dist[i, j] = round(math.hypot(xi - xj, yi - yj), 2)
    return inst
