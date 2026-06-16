from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = (
        "postgresql+psycopg://forensicflow:forensicflow@localhost:5432/forensicflow"
    )
    search_backend: str = "postgres"
    opensearch_url: str = "http://localhost:9200"
    opensearch_index_prefix: str = "ff"
    redis_url: str = "redis://localhost:6379/0"
    evidence_root: str = "/data/evidence"
    eztools_root: str = "/opt/eztools"
    sigma_rules_root: str = "/opt/sigma/rules"
    sigma_rules_bundled: str = "/opt/sigma-bundled"
    sigma_ref: str = "master"
    sigma_profile: str = "dfir"
    sigma_refresh_interval_hours: float = 24.0
    chainsaw_bin: str = "/usr/local/bin/chainsaw"
    chainsaw_rules_root: str = "/opt/chainsaw/rules"
    chainsaw_rules_bundled: str = "/opt/chainsaw-bundled"
    chainsaw_mappings_root: str = "/opt/chainsaw/mappings"
    chainsaw_ref: str = "master"
    chainsaw_enabled: bool = True
    chainsaw_include_sigma: bool = True
    chainsaw_hunt_batch_timeout_seconds: int = 300
    chainsaw_evtx_mode: str = "priority"
    chainsaw_evtx_max: int = 64
    chainsaw_evtx_parallel: int = 4
    chainsaw_evtx_batch_size: int = 16
    chainsaw_sigma_profile: str = "dfir"
    chainsaw_sigma_dfir_cache: str = "/opt/sigma/rules-dfir-cache"
    yara_enabled: bool = True
    yara_rules_root: str = "/opt/yara/rules"
    yara_rules_bundled: str = "/opt/yara-bundled/signature-base"
    yara_ref: str = "master"
    yara_scan_max_file_bytes: int = 10485760
    yara_scan_max_matches: int = 5000
    hindsight_enabled: bool = True
    hindsight_bin: str = "/usr/local/bin/hindsight"
    hindsight_max_profiles: int = 8
    hindsight_timeout_seconds: int = 900
    delete_evidence_after_ingest: bool = False
    plaso_enabled: bool = True
    plaso_log2timeline_bin: str = "log2timeline"
    plaso_psort_bin: str = "psort"
    plaso_workers: int = 4
    plaso_parallel_enabled: bool = True
    plaso_parallel_jobs: int = 2
    plaso_linux_families: str = (
        "logs=systemd_journal,utmp,text;"
        "db=sqlite,jsonl;"
        "browser=chrome_cache,firefox_cache2;"
        "fs=filestat"
    )
    plaso_macos_families: str = (
        "system=asl_log,bsm_log,utmpx,systemd_journal,text;"
        "db=sqlite,plist,binary_cookies;"
        "macos=fseventsd,spotlight_storedb,unified_logging;"
        "fs=filestat"
    )
    plaso_unknown_families: str = (
        "core=systemd_journal,utmp,utmpx,text;"
        "db=sqlite,plist,jsonl;"
        "fs=filestat"
    )
    plaso_macos_parsers: str = (
        "asl_log,bsm_log,utmpx,sqlite,plist,binary_cookies,systemd_journal,"
        "fseventsd,spotlight_storedb,unified_logging,text,filestat"
    )
    plaso_linux_parsers: str = (
        "systemd_journal,utmp,sqlite,jsonl,text,filestat,chrome_cache,firefox_cache2"
    )
    plaso_unknown_parsers: str = (
        "systemd_journal,utmp,utmpx,asl_log,bsm_log,sqlite,plist,jsonl,text,filestat"
    )
    plaso_timeout_seconds: int = 1800
    mac_apt_enabled: bool = True
    mac_apt_bin: str = "mac_apt.py"
    mac_apt_timeout_seconds: int = 1800
    volatility3_enabled: bool = True
    volatility3_bin: str = "vol"
    volatility3_timeout_seconds: int = 1800
    volatility3_plugins: str = "windows.info,windows.pslist,windows.netscan,windows.cmdline"


settings = WorkerSettings()
