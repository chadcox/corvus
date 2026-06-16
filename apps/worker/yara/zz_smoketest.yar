rule FF_YARA_SMOKETEST
{
  meta:
    description = "ForensicFlow YARA smoke test"
    level = "low"
  strings:
    $a = "FORensicsFLOW_YARA_SMOKE_2026"
  condition:
    $a
}
