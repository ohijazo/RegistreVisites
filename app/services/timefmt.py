"""Format de timestamps en hora local per a la presentació.

Tots els timestamps a la BD es desen en UTC (columnes DateTime(timezone=True)
o crides explícites a `datetime.now(timezone.utc)`). Les plantilles han de
mostrar-los en hora local (Europe/Madrid). Aquest filtre fa la conversió
i el strftime en una sola passa.

Per a objectes `date` i `time` (sense informació de fus horari) es retorna
el strftime directament — no hi ha res a convertir.
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


LOCAL_TZ = ZoneInfo("Europe/Madrid")


def local(value, fmt: str = "%d/%m/%Y %H:%M") -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        # Naive: assumim UTC (el codi del projecte sempre desa en UTC).
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        value = value.astimezone(LOCAL_TZ)
    return value.strftime(fmt)
