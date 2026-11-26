"""Costanti per l'integrazione Daikin intelligent Touch Manager."""

DOMAIN = "daikin_itm"
DEFAULT_SCAN_INTERVAL = 120  # secondi: login, lettura di tutte le unità, logout
REFRESH_AFTER_COMMAND = 15   # secondi: l'iTM impiega diversi secondi ad applicare i comandi sul bus

# Testo del modo nel portale -> modo HVAC di Home Assistant (stringhe di HVACMode)
MODE_TO_HVAC = {"Caldo": "heat", "Freddo": "cool", "Vent": "fan_only"}
HVAC_TO_MODE = {v: k for k, v in MODE_TO_HVAC.items()}
