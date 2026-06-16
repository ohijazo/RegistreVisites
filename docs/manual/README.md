# Manual del recepcionista — Registre de Visites

Document distribuïble per email al personal d'oficina que utilitzarà el panell `/admin` amb rol `receptionist`.

## Com regenerar el manual

```bash
# Una vegada (instal·la la dependència)
pip install python-docx

# Cada vegada que vulguis regenerar
python scripts/build_manual.py
```

Sortida: `docs/manual/Manual_Recepcionista_Visites.docx`

## Captures de pantalla

Les captures van a `docs/manual/img/` amb el nom exacte indicat a `CAPTURES_TODO.md`. Si una captura encara no existeix, l'script insereix un placeholder `[CAPTURA: nom_arxiu.png]` al document. Així pots anar fent captures progressivament i tornar a generar.

Llista completa de captures pendents: vegeu `CAPTURES_TODO.md`.

## Edició

El text del manual viu directament dins `scripts/build_manual.py`. Si vols modificar paraules concretes, edita el script i torna a generar. Per a retocs cosmètics finals (afegir comentari, canviar una frase puntual), obre el `.docx` resultant a Word i edita-hi directament — però recorda que es perdran si tornes a regenerar.
