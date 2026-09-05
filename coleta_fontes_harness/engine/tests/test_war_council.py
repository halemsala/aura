from engine.agents.war_council import convene, record_result
from engine.agents_glm.elo_rating_agent import EloRatingAgent
from engine.agents_glm.red_team_adversary import RedTeamAdversary


def test_red_team_vetoes_kill_zone() -> None:
    audit = RedTeamAdversary().audit_decision(
        {"score": "0-0", "minute": 88, "attack_pressure_diff": 40, "shots_off_target": 1, "corners": 4},
        {"odd": 1.85, "decision": "ENTRA"},
    )
    assert audit["verdict"] == "VETOED"


def test_council_veto_is_advisory_only() -> None:
    result = convene(
        {"minute": 88, "score": "0-0", "attack_pressure_diff": 40, "home": "A", "away": "B"},
        {"decision": "ENTRA", "odd": 1.9, "score": 80},
    )
    assert result["verdict"] == "VETOED"
    assert result["execution_allowed"] is False
    assert result["paper_trade"] is True
    assert result["red_team"]["verdict"] == "VETOED"


def test_elo_inspect_is_paper_only() -> None:
    agent = EloRatingAgent()
    info = agent.inspect("Alpha", "Beta", 2.2)
    assert info["execution_allowed"] is False
    assert "fair_odd_home" in info


def test_forensics_records_loss() -> None:
    out = record_result({"minute": 42, "score": 60}, "LOSS")
    assert out["execution_allowed"] is False
    assert out["ok"] is True
