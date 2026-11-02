import json
from pathlib import Path


FIXTURES = Path(__file__).parent / 'fixtures'


def test_parse_qlc_primary_keeps_basic_and_special_numbers_separate():
    from lottery.collectors import parse_qlc_primary

    row = json.loads((FIXTURES / 'qlc_primary_page.json').read_text())['result'][0]
    actual = parse_qlc_primary(row)

    assert actual['game'] == 'qlc'
    assert actual['issue'] == '2026125'
    assert actual['draw_date'] == '2026-10-30'
    assert actual['zones'] == {'basic': [2, 5, 10, 15, 22, 23, 28], 'special': [3]}
    assert actual['prizes']['1'] == {'amount': '1324430', 'count': 2, 'raw_amount': '1324430'}
    assert actual['prizes']['7'] == {'amount': '5', 'count': 79379, 'raw_amount': '5'}


def test_parse_qlc_primary_keeps_missing_award_values_unknown():
    from lottery.collectors import parse_qlc_primary

    actual = parse_qlc_primary({'code': '2026125', 'date': '2026-10-30(五)', 'red': '02,05,10,15,22,23,28', 'blue': '03', 'prizegrades': [{'type': 1, 'typenum': '', 'typemoney': ''}]})

    assert actual['prizes']['1'] == {'amount': None, 'count': None, 'raw_amount': ''}


def test_parse_qlc_secondary_keeps_basic_and_special_numbers_separate():
    from lottery.collectors import parse_qlc_secondary

    actual = parse_qlc_secondary({'issue': '2026125', 'draw_date': '2026-10-30(五)', 'numbers': '02 05 10 15 22 23 28 03', 'source_url': 'https://example.test/qlc'})

    assert actual['zones'] == {'basic': [2, 5, 10, 15, 22, 23, 28], 'special': [3]}


def test_qlc_secondary_rejects_malformed_number_text():
    from lottery.collectors import parse_qlc_secondary
    import pytest

    with pytest.raises(ValueError, match='Invalid qlc basic numbers'):
        parse_qlc_secondary({'issue': '2026125', 'draw_date': '2026-10-30', 'numbers': '02 05 bad 15 22 23 28 03', 'source_url': 'https://example.test/qlc'})


def test_parse_qxc_primary_keeps_order_and_allows_repeated_digits():
    from lottery.collectors import parse_qxc_primary

    row = json.loads((FIXTURES / 'qxc_primary_page.json').read_text())['value']['list'][0]
    actual = parse_qxc_primary(row)

    assert actual['game'] == 'qxc'
    assert actual['issue'] == '2026125'
    assert actual['draw_date'] == '2026-11-01'
    assert actual['zones'] == {'positions': [2, 9, 4, 5, 6, 3, 2]}
    assert actual['prizes']['1'] == {'amount': None, 'count': 0, 'raw_amount': '---'}
    assert actual['prizes']['2'] == {'amount': '40875', 'count': 8, 'raw_amount': '40,875'}


def test_qxc_parser_rejects_wrong_position_count():
    from lottery.collectors import parse_qxc_primary
    import pytest

    with pytest.raises(ValueError, match='seven ordered digits'):
        parse_qxc_primary({'lotteryDrawNum': '26125', 'lotteryDrawTime': '2026-11-01', 'lotteryDrawResult': '2 9 4'})


def test_parse_qxc_secondary_preserves_position_order():
    from lottery.collectors import parse_qxc_secondary

    actual = parse_qxc_secondary({'issue': '26125', 'draw_date': '2026-11-01', 'numbers': '2 9 4 5 6 3 2', 'source_url': 'https://example.test/qxc'})

    assert actual['issue'] == '2026125'
    assert actual['zones']['positions'] == [2, 9, 4, 5, 6, 3, 2]


def test_secondary_pages_keep_their_independent_number_records():
    from lottery.collectors import parse_qlc_secondary_page, parse_qxc_secondary_page

    qlc = parse_qlc_secondary_page((FIXTURES / 'qlc_secondary_page.html').read_text())
    qxc = parse_qxc_secondary_page((FIXTURES / 'qxc_secondary_page.html').read_text())

    assert qlc[0]['zones'] == {'basic': [2, 5, 10, 15, 22, 23, 28], 'special': [3]}
    assert qxc[0]['zones']['positions'] == [2, 9, 4, 5, 6, 3, 2]
