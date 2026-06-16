# Captures de pantalla per al manual

Guarda cada captura a `docs/manual/img/` amb **el nom exacte** indicat a la primera columna. Si el nom no coincideix, l'script no la trobarà i el manual mostrarà un placeholder.

Format recomanat: **PNG**, amplada entre 1200 i 1600px. Pots fer la captura amb amplada de finestra normal del navegador.

Si vols evitar exposar dades reals (noms, empreses, DNIs), pots:
- Fer servir el navegador en mode "developer tools" per redactar text amb el DOM
- O fer la captura i després retocar amb Paint / GIMP per emborronar parts sensibles
- O carregar dades de prova al sistema abans

Un cop tinguis totes (o algunes) → `python scripts/build_manual.py` per regenerar.

---

## Secció 2 — Primer accés

| Fitxer | URL | Què mostrar |
|---|---|---|
| `01_login.png` | `http://visitesfc.agrienergia.local/admin/login` | Formulari de login (email + contrasenya) sense omplir. |
| `02_layout.png` | `http://visitesfc.agrienergia.local/admin/` (un cop dins) | Vista global del panell, amb la barra de navegació superior/lateral visible. Pot ser el dashboard mateix. |
| `03_profile.png` | Menú d'usuari (clica el teu nom a dalt a la dreta) | Desplegable del menú d'usuari o pantalla de perfil amb el botó de canviar contrasenya. |

## Secció 3 — Dashboard

| Fitxer | URL | Què mostrar |
|---|---|---|
| `10_dashboard.png` | `http://visitesfc.agrienergia.local/admin/` | Vista completa del dashboard, amb targetes de resum i taula d'actives. |
| `11_dashboard_expected.png` | `http://visitesfc.agrienergia.local/admin/` | Detall del bàner de visites previstes (només la part superior). Si no n'hi ha cap, en crea una de prova abans. |
| `12_active_table.png` | `http://visitesfc.agrienergia.local/admin/` | Detall de la taula de visites actives, idealment amb alguna fila en groc o vermell per mostrar els colors d'alerta. |
| `13_manual_checkout.png` | `http://visitesfc.agrienergia.local/admin/` | Detall del botó "Sortida manual" d'una fila (zoom o crop). |

## Secció 4 — Historial

| Fitxer | URL | Què mostrar |
|---|---|---|
| `20_visits_list.png` | `http://visitesfc.agrienergia.local/admin/visits` | Llistat d'historial amb diverses files, on es vegin les columnes principals. |
| `21_filters.png` | `http://visitesfc.agrienergia.local/admin/visits` | Detall de la part superior amb tots els filtres visibles (dates, empresa, departament, etc). |

## Secció 5 — Detall d'una visita

| Fitxer | URL | Què mostrar |
|---|---|---|
| `30_visit_detail.png` | `http://visitesfc.agrienergia.local/admin/visits/<id_qualsevol>` | Vista completa del detall d'una visita (preferiblement una de completada). |
| `31_view_dni.png` | Mateix detall + clica "Veure DNI" | Diàleg que demana la contrasenya per desxifrar el DNI (no cal arribar a desxifrar; només la pantalla del prompt). |

## Secció 6 — Exportar

| Fitxer | URL | Què mostrar |
|---|---|---|
| `40_export.png` | `http://visitesfc.agrienergia.local/admin/visits` | Detall dels botons d'exportació Excel/CSV (la barra superior amb els botons). |

## Secció 7 — Visites previstes

| Fitxer | URL | Què mostrar |
|---|---|---|
| `50_expected_list.png` | `http://visitesfc.agrienergia.local/admin/expected` | Llistat de visites previstes. |
| `51_expected_new.png` | `http://visitesfc.agrienergia.local/admin/expected/new` (o similar) | Formulari de nova visita prevista. |
| `52_expected_calendar.png` | `http://visitesfc.agrienergia.local/admin/expected/calendar` (o accés des de "Calendari") | Vista del calendari amb previsions. |
| `53_expected_notify.png` | `http://visitesfc.agrienergia.local/admin/expected/<id>` | Detall d'una previsió en estat "Pendent" mostrant els botons "Enviar notificació" (blau, dalt) i "Enviar invitació al visitant" (morat, al bloc del codi). |

## Secció 8 — Estadístiques

| Fitxer | URL | Què mostrar |
|---|---|---|
| `60_stats_top.png` | `http://visitesfc.agrienergia.local/admin/stats` | Part superior d'estadístiques amb el resum del període. |
| `61_stats_daily.png` | `http://visitesfc.agrienergia.local/admin/stats` | El gràfic de visites per dia (es pot fer scroll i capturar només aquest gràfic). |

## Secció 9 — Què veu el visitant

> Aquestes captures és més fàcil fer-les des d'un navegador normal anant a les URL del flux del visitant, no cal anar fins a la tablet.

| Fitxer | URL | Què mostrar |
|---|---|---|
| `70_visitor_language.png` | `http://visitesfc.agrienergia.local/` | Pantalla de selecció d'idioma amb els 4 botons (CA/ES/FR/EN). |
| `71_visitor_action.png` | `http://visitesfc.agrienergia.local/ca/action` | Menú amb les 3 opcions (Entrada / Sortida / Codi). |
| `72_visitor_form.png` | `http://visitesfc.agrienergia.local/ca/register` | Formulari de dades (sense omplir o amb dades de prova). |
| `73_visitor_legal.png` | `http://visitesfc.agrienergia.local/ca/legal` (després d'haver enviat el formulari) | Pantalla de normes i signatura. Si no surt, omple primer el formulari amb dades de prova. |
| `74_visitor_confirmation.png` | Després de completar un registre de prova | Pantalla de confirmació amb el "Benvingut/da, ...". |
| `75_visitor_checkout.png` | `http://visitesfc.agrienergia.local/checkout` | Pantalla on s'introdueix el DNI per registrar la sortida. |
| `76_visitor_code.png` | `http://visitesfc.agrienergia.local/ca/code` | Pantalla d'introducció del codi de pre-registre. |

---

## Total

25 captures. No cal fer-les totes alhora — el manual es regenera amb les que tinguis i marca les que falten com a "[CAPTURA PENDENT]".
