"""Constants for the energy agent integration."""
from datetime import timedelta

DOMAIN = "energy_agent"

BASE_URL = "https://app.energy-agent.at/api/v0"

CONF_API_KEY = "api_key"
CONF_COMMUNITY_ID = "community_id"
CONF_COMMUNITY_NAME = "community_name"

TARGETS = ("generation", "consumption")

SCAN_INTERVAL = timedelta(minutes=5)
INTERVAL = timedelta(minutes=15)

# kWh pro 15-Minuten-Intervall -> mittlere Leistung in kW (60 / 15)
KWH_TO_KW = timedelta(hours=1) / INTERVAL
