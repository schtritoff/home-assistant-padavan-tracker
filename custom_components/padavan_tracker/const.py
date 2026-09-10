"""Constants for the padavan-ng Tracker integration."""

from datetime import timedelta

DOMAIN = "padavan_tracker"

DEFAULT_NAME = "padavan-ng Router"
DEFAULT_SCAN_INTERVAL = timedelta(seconds=60)

LAN_CLIENTS_PATH = "/lan_clients.asp"
SYSINFO_PATH = "/state.js"
SYSTEM_PAGE = "/Advanced_System_Content.asp"
FIRMWARE_PAGE = "/Advanced_FirmwareUpgrade_Content.asp"
REQUEST_TIMEOUT = 10

CONF_TRACK_UNKNOWN = "track_unknown"
CONF_REQUIRE_IP = "require_ip"
CONF_UPDATE_INTERVAL = "scan_interval"

KEY_SENSORS = "sensors"
KEY_METHOD = "method"
KEY_COORDINATOR = "coordinator"

SENSORS_CONNECTED_DEVICE = ("sensors_connected_devices",)
SENSORS_SYSINFO = (
    "sensors_load_avg_1m",
    "sensors_load_avg_5m",
    "sensors_load_avg_15m",
    "sensors_mem_total",
    "sensors_mem_used",
    "sensors_mem_free",
    "sensors_mem_cached",
    "sensors_mem_buffers",
    "sensors_mem_percent",
    "sensors_swap_total",
    "sensors_swap_used",
    "sensors_uptime",
    "sensors_last_boot",
)

SENSORS_TYPE_COUNT = "sensors_count"
SENSORS_TYPE = "sensors"

DEFAULT_TRACK_UNKNOWN = True
DEFAULT_REQUIRE_IP = True
