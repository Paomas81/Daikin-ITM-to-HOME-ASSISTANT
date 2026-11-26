# Daikin intelligent Touch Manager (iTM) per Home Assistant

Integrazione custom che controlla un iTM Daikin (testato su firmware Ver1.20.00) attraverso il
protocollo del suo portale web Flash, senza opzioni a licenza (BACnet/HTTP Interface).

## Entità

Ogni unità dell'iTM diventa un dispositivo in Home Assistant, collegato al dispositivo dell'iTM.

**Unità interne** (gruppo "U/I"):
- `climate`: on/off, modo (Caldo → heat, Freddo → cool, Vent → fan_only), setpoint con il range
  impostato sull'iTM, velocità ventilazione: low/high sulle unità a 2 tacche, low/medium/high su quelle a 3.
- `sensor` "Temperatura mandata": la temperatura letta dall'unità. Non è la temperatura ambiente,
  per questo il termostato non mostra una temperatura attuale.

**Ventilazione** (gruppo "Ventilatore", VAM): `switch` Avvia/Arresta.

**Limiti del setpoint** (entità di configurazione, **disattivate di default**): per ogni unità interna
Limite caldo/freddo attivo (`switch`) e Max/Min (`number`, gradi interi). Compaiono solo nella pagina
del dispositivo, sezione Configurazione, e non nelle dashboard automatiche. Vengono letti solo per le
unità dove almeno una di queste entità è attivata, una volta all'ora e dopo ogni modifica, perché
richiedono di aprire le impostazioni dettagliate dell'unità.

Le unità senza setpoint sono trattate come VAM. Se un'unità mostra un'icona di velocità non
riconosciuta, la velocità non compare e il codice grezzo è nell'attributo `icona_ventilazione`.

## Sessione unica

L'iTM accetta un solo accesso web alla volta. L'integrazione fa login, legge tutte le unità e fa
logout ogni 60 secondi (modificabile nelle Opzioni dell'integrazione, minimo 30); ogni comando apre e chiude una sessione propria. Se qualcuno è collegato
dal browser, la lettura viene rimandata (attributo `portale_occupato`) e i comandi danno un errore.

Dopo un comando lo stato si aggiorna subito in modo ottimistico e viene riletto dopo 15 secondi,
perché l'iTM impiega diversi secondi ad applicare i comandi sul bus.

Consigliato un utente iTM dedicato all'integrazione.

## Installazione

- **HACS**: aggiungi questo repository come repository personalizzato (tipo *Integrazione*).
- **Manuale**: copia `custom_components/daikin_itm` nella cartella `config/custom_components/`.

Riavvia Home Assistant, poi Impostazioni → Dispositivi e servizi → Aggiungi integrazione →
*Daikin intelligent Touch Manager*.

## Debug

```yaml
logger:
  logs:
    custom_components.daikin_itm: debug
```
