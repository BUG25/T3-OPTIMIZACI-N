# Formulación del ConVRP reducido (TC2 / TC3)

Versión reducida del modelo de Campelo, Neves-Moreira, Amorim y Almada-Lobo (2019),
*Consistent vehicle routing problem with service level agreements*, EJOR 273(1), §3.1
(pág. 134–136). Se mantiene exactamente la misma formulación matemática trabajada en TC2
para comparar el desempeño de **Gurobi** y **CPLEX** sobre las mismas instancias.

## Conjuntos

| Símbolo | Significado |
|---|---|
| $T$ | días del horizonte de planificación |
| $R$ | rutas (vehículos/conductores), las mismas todos los días |
| $N$ | clientes |
| $N_t \subseteq N$ | clientes con demanda positiva el día $t$ ($q_{it} > 0$) |
| $V_t = \{0\} \cup N_t$ | nodos activos del día $t$; el $0$ es el depósito |
| $W \subseteq N$ | clientes con ventana de tiempo definida |

## Parámetros

| Símbolo | Significado |
|---|---|
| $d_{ij}$ | distancia euclidiana entre $i$ y $j$ (redondeada a 2 decimales) |
| $\tau_{ij}$ | tiempo de viaje entre $i$ y $j$ ($\tau_{ij} = d_{ij}$) |
| $s_i$ | tiempo de servicio en el cliente $i$ |
| $q_{it}$ | demanda del cliente $i$ el día $t$ |
| $Q$ | capacidad de cada vehículo |
| $[a_i, b_i]$ | ventana de tiempo del cliente $i \in W$ |
| $[E, L]$ | horario de operación del depósito |
| $M_{ij}$ | constante Big-M calibrada para cada arco |

## Variables

| Variable | Tipo | Significado |
|---|---|---|
| $X_{rijt}$ | binaria | $1$ si la ruta $r$ recorre el arco $(i,j)$ el día $t$ ($(i,j) \in V_t^2,\, i \ne j$) |
| $Z_{ri}$ | binaria | $1$ si el cliente $i \in N$ queda asignado a la ruta $r$ durante todo el horizonte |
| $A_{it}$ | continua | instante en que comienza el servicio en $i \in N_t$ el día $t$ |
| $S_r$ | continua | hora de salida planificada de la ruta $r$ desde el depósito |
| $F_{rt}$ | continua | hora de retorno de la ruta $r$ al depósito el día $t$ |

## Modelo matemático

**(1) Función objetivo.** Minimizar la distancia total recorrida por todas las rutas en todos los días:

$$\min \sum_{t\in T}\sum_{r\in R}\sum_{(i,j)\in V_t^2,\, i\ne j} d_{ij}\, X_{rijt}$$

**(2) Asignación cliente–ruta (consistencia).** Cada cliente queda asignado a exactamente una ruta:

$$\sum_{r\in R} Z_{ri} = 1 \qquad \forall i\in N$$

**(3)–(4) Grado de salida y entrada.** Solo se imponen sobre $i \in N_t$ (los clientes sin demanda el día $t$ no son visitados):

$$\sum_{j\in V_t,\, j\ne i} X_{rijt} = Z_{ri} \qquad \forall r\in R,\ t\in T,\ i\in N_t$$

$$\sum_{j\in V_t,\, j\ne i} X_{rjit} = Z_{ri} \qquad \forall r\in R,\ t\in T,\ i\in N_t$$

**(5) Salida del depósito.** Cada ruta sale del depósito a lo más una vez por día:

$$\sum_{j\in N_t} X_{r0jt} \le 1 \qquad \forall r\in R,\ t\in T$$

**(7) Tiempo de llegada (Big-M agregado sobre las rutas).** Propaga los tiempos de inicio de servicio y elimina subtours ($s_i + \tau_{ij} > 0$):

$$A_{jt} \ge A_{it} + s_i + \tau_{ij} - M_{ij}\Big(1-\sum_{r\in R} X_{rijt}\Big) \qquad \forall t\in T,\ i,j\in N_t,\ i\ne j$$

**(8) Ventanas de tiempo.** Solo para los clientes con ventana activa ese día:

$$a_i \le A_{it} \le b_i \qquad \forall t\in T,\ i\in N_t\cap W$$

**(9) Coordinación con la salida del depósito:**

$$A_{jt} \ge S_r + \tau_{0j} - M_{0j}(1-X_{r0jt}) \qquad \forall r\in R,\ t\in T,\ j\in N_t$$

**(10) Coordinación con el retorno al depósito:**

$$F_{rt} \ge A_{it} + s_i + \tau_{i0} - M_{i0}(1-X_{ri0t}) \qquad \forall r\in R,\ t\in T,\ i\in N_t$$

**(11)–(12) Horario de operación del depósito:**

$$S_r \ge E \qquad \forall r\in R, \qquad\qquad F_{rt} \le L \qquad \forall r\in R,\ t\in T$$

**(14) Capacidad por ruta y día:**

$$\sum_{i\in N_t} q_{it}\, Z_{ri} \le Q \qquad \forall r\in R,\ t\in T$$

**(16) Dominio de las variables:**

$$X_{rijt},\ Z_{ri}\in\{0,1\};\qquad A_{it},\ S_r,\ F_{rt}\in[E, L]$$

## Calibración del Big-M

Con el intervalo efectivo $[lo_i, hi_i]$ para cada cliente $i$:

$$lo_i = \max(a_i,\ E + \tau_{0i}), \qquad hi_i = \min(b_i,\ L - s_i - \tau_{i0})$$

(tomando $a_i = E$, $b_i = L$ cuando el cliente no tiene ventana):

- $M_{ij} = \max(0,\ hi_i + s_i + \tau_{ij} - lo_j)$
- $M_{0j} = \max(0,\ L + \tau_{0j} - lo_j)$
- $M_{i0} = \max(0,\ hi_i + s_i + \tau_{i0} - E)$
