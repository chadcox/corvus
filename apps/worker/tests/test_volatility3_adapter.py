from worker.sources.volatility3 import _is_windows_memory_from_banners


def test_windows_memory_banner_detection_matches_kernel_pdb_lines():
    output = (
        "0x2219e40       ntkrnlmp.pdb|8B11040A5928757B11390AC78F6B6925|1\n"
        "0x9d5fb80       ntoskrnl.pdb|F4A45A63EC854C8681DCAC9F6DCAD908|1\n"
    )
    assert _is_windows_memory_from_banners(output)


def test_windows_memory_banner_detection_rejects_non_windows_banners():
    output = "0x1000 linux_banner|Ubuntu 22.04|1\n"
    assert not _is_windows_memory_from_banners(output)
