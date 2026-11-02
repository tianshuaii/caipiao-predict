import pytest


def test_new_game_bayesian_probabilities_are_normalized_per_zone_or_position():
    from lottery.model_training import zone_probability_vectors
    qlc=[{'issue':'2026125','zones':{'basic':[1,2,3,4,5,6,7],'special':[8]}}] * 3
    qxc=[{'issue':'2026125','zones':{'positions':[2,9,4,5,6,3,2]},'rule_version':'qxc-20201011'}] * 3
    assert sum(zone_probability_vectors('qlc',qlc)['basic']) == pytest.approx(7)
    assert sum(zone_probability_vectors('qlc',qlc)['special']) == pytest.approx(1)
    assert [sum(values) for values in zone_probability_vectors('qxc',qxc)['positions']] == pytest.approx([1] * 7)


def test_qxc_research_refuses_mixed_rule_versions():
    from lottery.model_training import zone_probability_vectors
    rows=[{'issue':'2020099','zones':{'positions':[1]*7},'rule_version':'qxc-classic'},
          {'issue':'2020100','zones':{'positions':[1,1,1,1,1,1,14]},'rule_version':'qxc-20201011'}]
    with pytest.raises(ValueError, match='rule version'):
        zone_probability_vectors('qxc',rows)
