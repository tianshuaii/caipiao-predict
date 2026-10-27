import pytest
from lottery.domain import validate_ticket, prize_level
from lottery.predict import generate_tickets

def test_invalid_numbers_are_rejected():
    with pytest.raises(ValueError):
        validate_ticket('ssq', [1, 1, 2, 3, 4, 5], [1])
    with pytest.raises(ValueError):
        validate_ticket('dlt', [1, 2, 3, 4, 36], [1, 2])
    with pytest.raises(ValueError):
        validate_ticket('ssq', [1, 2, 3, 4, 5, 6], [17])

@pytest.mark.parametrize('issue,hits,level', [
    ('2019018', (4, 1), 4), ('2019019', (4, 1), 5),
    ('2026013', (4, 2), 4), ('2026014', (4, 2), 3),
    ('2026014', (3, 0), 7), ('2026013', (3, 0), 9),
    ('2026014', (0, 1), None), ('2026014', (0, 2), 7),
])
def test_historical_dlt_rules(issue, hits, level):
    assert prize_level('dlt', issue, *hits) == level

def test_ssq_awards():
    assert prize_level('ssq', '2026121', 6, 1) == 1
    assert prize_level('ssq', '2026121', 0, 1) == 6
    assert prize_level('ssq', '2026121', 3, 0) is None

@pytest.mark.parametrize('game', ['ssq', 'dlt'])
def test_five_unique_reproducible_tickets(game):
    result = generate_tickets(game, 42)
    assert result == generate_tickets(game, 42)
    assert len(result) == len({str(t) for t in result}) == 5
    for ticket in result:
        validate_ticket(game, ticket['front'], ticket['back'])
