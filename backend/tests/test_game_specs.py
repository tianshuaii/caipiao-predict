import pytest

from lottery.game_specs import game_spec, validate_draw, validate_ticket_data


@pytest.mark.parametrize('game,issue,zones', [
    ('ssq', '2026121', {'front': [2, 7, 20, 24, 26, 30], 'back': [1]}),
    ('dlt', '2026120', {'front': [1, 2, 3, 4, 5], 'back': [1, 2]}),
])
def test_legacy_games_keep_their_front_back_shapes(game, issue, zones):
    assert validate_draw(game, issue, zones) == zones
    assert validate_ticket_data(game, issue, zones) == zones


def test_qlc_requires_seven_basic_numbers_and_a_distinct_special_number():
    zones = {'basic': [2, 5, 10, 15, 22, 23, 28], 'special': [3]}
    assert validate_draw('qlc', '2026125', zones) == zones

    with pytest.raises(ValueError, match='distinct'):
        validate_draw('qlc', '2026125', {'basic': zones['basic'], 'special': [2]})


def test_qxc_is_ordered_and_allows_repeated_digits():
    zones = {'positions': [2, 9, 4, 5, 6, 3, 2]}
    assert validate_ticket_data('qxc', '2026125', zones) == zones
    assert game_spec('qxc', '20099').rule_version == 'qxc-classic'
    assert game_spec('qxc', '20100').rule_version == 'qxc-20201011'


def test_qxc_rejects_an_invalid_seventh_value():
    with pytest.raises(ValueError, match='out of range'):
        validate_draw('qxc', '2026125', {'positions': [2, 9, 4, 5, 6, 3, 15]})
