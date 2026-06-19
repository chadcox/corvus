from enum import StrEnum


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class EvidencePlatform(StrEnum):
    UNKNOWN = "unknown"
    WINDOWS = "windows"
    MACOS = "macos"
    LINUX = "linux"
    MEMORY = "memory"


class KapeCategory(StrEnum):
    """Common KAPE module output folder names."""
    EVIDENCE_OF_EXECUTION = "EvidenceOfExecution"
    REGISTRY = "Registry"
    EVENT_LOGS = "EventLogs"
    BROWSER_HISTORY = "BrowserHistory"
    ACCOUNT_USAGE = "AccountUsage"
    FILE_SYSTEM = "FileSystem"
    NETWORK = "Network"
    RAW_COLLECTION = "C"


KAPE_MODULE_CSV_HINTS = (
    "EvtxECmd",
    "MFTECmd",
    "PECmd",
    "RECmd",
    "Amcache",
    "JLECmd",
    "LECmd",
)

# KAPE collection logs (raw triage without !EZParser)
KAPE_LOG_CSV_HINTS = (
    "CopyLog",
    "SkipLog",
)
