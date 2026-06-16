from worker.chainsaw.evaluate import evaluate_chainsaw_hunt
from worker.chainsaw.hunt import hit_correlation_keys, hit_engine, hit_rule_id, hit_title


def test_hit_rule_id_slug():
    hit = {"group": "Log Tampering", "detections": "Security Audit Logs Cleared"}
    assert hit_rule_id(hit).startswith("chainsaw:log-tampering:")


def test_hit_title_from_detections():
    hit = {"detections": ["Windows Defender"]}
    assert "Windows Defender" in hit_title(hit)


def test_hit_correlation_keys_chainsaw_2_json():
    hit = {
        "group": "Account Tampering",
        "name": "User Added to Global Group",
        "document": {
            "data": {
                "Event": {
                    "System": {
                        "EventID": 4728,
                        "EventRecordID": 73497,
                        "Computer": "chad-win11vm",
                    }
                }
            }
        },
    }
    assert hit_correlation_keys(hit) == ("4728", "73497", "chad-win11vm")


def test_hit_engine_sigma_source():
    hit = {"source": "sigma", "group": "Sigma", "name": "User Logoff Event", "id": "abc-123"}
    assert hit_engine(hit) == "sigma"
    assert hit_rule_id(hit) == "sigma:abc-123"


def test_evaluate_correlates_chainsaw_2_nested_hit():
    events = [
        {
            "id": "ev-1",
            "data": {
                "EventId": "4728",
                "RecordNumber": "73497",
                "Computer": "chad-win11vm",
                "Channel": "Security",
            },
        }
    ]
    hits = [
        {
            "group": "Account Tampering",
            "name": "User Added to Global Group",
            "level": "info",
            "document": {
                "data": {
                    "Event": {
                        "System": {
                            "EventID": 4728,
                            "EventRecordID": 73497,
                            "Computer": "chad-win11vm",
                        }
                    }
                }
            },
        }
    ]

    from unittest.mock import patch

    with patch("worker.chainsaw.evaluate.run_chainsaw_hunt_parallel", return_value=hits):
        with patch("worker.chainsaw.evaluate.collect_evtx_for_hunt", return_value=[__import__("pathlib").Path("/x.evtx")]):
            detections, updated = evaluate_chainsaw_hunt("/pkg", events, "src-1")

    assert len(detections) == 1
    assert detections[0]["engine"] == "chainsaw"
    assert updated[0]["sigma_hits"][0]["title"] == "User Added to Global Group"


def test_evaluate_correlates_event_id():
    events = [
        {
            "id": "ev-1",
            "data": {
                "EventId": "1102",
                "RecordNumber": "37",
                "Computer": "WIN10",
                "Channel": "Security",
            },
        }
    ]
    hits = [
        {
            "group": "Log Tampering",
            "detections": "Security Audit Logs Cleared",
            "level": "critical",
            "Event ID": "1102",
            "Record ID": "37",
            "Computer": "WIN10",
        }
    ]

    from unittest.mock import patch

    with patch("worker.chainsaw.evaluate.run_chainsaw_hunt_parallel", return_value=hits):
        with patch("worker.chainsaw.evaluate.collect_evtx_for_hunt", return_value=[__import__("pathlib").Path("/x.evtx")]):
            detections, updated = evaluate_chainsaw_hunt("/pkg", events, "src-1")

    assert len(detections) == 1
    assert detections[0]["engine"] == "chainsaw"
    assert updated[0]["sigma_hits"][0]["engine"] == "chainsaw"
