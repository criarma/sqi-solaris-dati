# Changelog dei dati SQI per Solaris

Una riga per ogni versione del contratto passata al dal vivo (`manifest.json` alla radice). L'ora è quella UTC del
primo commit del manifest nella versione nuova. Il testo di ogni versione sta in `contratto/`, lo schema in `schema/`.
Dalla v1.4 ogni versione passa prima da `/next/` per almeno 48 ore (CP3).

| versione | dal vivo da (UTC) | commit | in breve |
|---|---|---|---|
| 1.3 | 2026-10-21 15:26 | edbf2d5 | `next_expected_at`, `points.lite_file`, `place_hint`, `name_source` e `nomi_curati.json`, `low_cloud`, `tier`, `canvas_last_light`, `places`; `within_calibrated_lead` deprecato; corsa ICON-EU per serata, quella che copre la serata (domani dell'Appennino di nuovo completo) |
| 1.2 | 2026-10-15 12:26 | 6a3f023 | prima pubblicazione dal vivo |

## Cambi del motore senza cambio di formato

| data (UTC) | versione | in breve |
|---|---|---|
| 2026-11-18 | 1.3 | ingressi completi in produzione (temperatura a 925 hPa, copertura e quota a 975, 950, 925 e 900 hPa dalla stessa corsa ICON-D2); nessun cambio di formato; nelle serate collaudate nessuna differenza visibile; le differenze sono attese solo con strati bassi fra 500 e 1000 m (inversioni invernali) |
