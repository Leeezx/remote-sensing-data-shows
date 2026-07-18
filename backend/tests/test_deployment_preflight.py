from scripts import check_deployment_data


def test_preflight_returns_zero_when_ready(monkeypatch, capsys):
    monkeypatch.setattr(check_deployment_data, "collect_readiness_failures", lambda: [])
    assert check_deployment_data.main() == 0
    assert "deployment data ready" in capsys.readouterr().out.lower()


def test_preflight_returns_one_with_stable_identifiers(monkeypatch, capsys):
    monkeypatch.setattr(
        check_deployment_data,
        "collect_readiness_failures",
        lambda: ["county_vector"],
    )
    assert check_deployment_data.main() == 1
    assert capsys.readouterr().err.strip() == "missing or invalid: county_vector"
