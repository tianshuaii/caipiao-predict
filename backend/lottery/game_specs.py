"""Immutable game structures used by collection and later analysis layers."""
from dataclasses import dataclass

from .domain import canonical_issue


@dataclass(frozen=True)
class ZoneSpec:
    name: str
    count: int
    minimum: int
    maximum: int
    ordered: bool = False
    distinct: bool = True
    position_maxima: tuple[int, ...] = ()


@dataclass(frozen=True)
class GameSpec:
    game: str
    name: str
    first: str
    days: tuple[int, ...]
    rule_version: str
    zones: tuple[ZoneSpec, ...]


_SPECS = {
    'ssq': GameSpec('ssq', '双色球', '2003001', (1, 3, 6), 'ssq-current',
                    (ZoneSpec('front', 6, 1, 33), ZoneSpec('back', 1, 1, 16))),
    'dlt': GameSpec('dlt', '超级大乐透', '2007001', (0, 2, 5), 'dlt-current',
                    (ZoneSpec('front', 5, 1, 35), ZoneSpec('back', 2, 1, 12))),
    'qlc': GameSpec('qlc', '七乐彩', '2005001', (1, 3, 6), 'qlc-current',
                    (ZoneSpec('basic', 7, 1, 30), ZoneSpec('special', 1, 1, 30))),
    'qxc-classic': GameSpec('qxc', '七星彩', '2004001', (1, 4, 6), 'qxc-classic',
                            (ZoneSpec('positions', 7, 0, 9, ordered=True, distinct=False),)),
    'qxc-20201011': GameSpec('qxc', '七星彩', '2004001', (1, 4, 6), 'qxc-20201011',
                             (ZoneSpec('positions', 7, 0, 14, ordered=True, distinct=False,
                                       position_maxima=(9, 9, 9, 9, 9, 9, 14)),)),
}


def game_spec(game, issue):
    issue = canonical_issue(issue)
    if game == 'qxc':
        return _SPECS['qxc-20201011' if issue >= '2020100' else 'qxc-classic']
    try:
        return _SPECS[game]
    except KeyError as exc:
        raise ValueError('Unknown game') from exc


def registered_games():
    return ('ssq', 'dlt', 'qlc', 'qxc')


def _validate_zone(spec, values):
    if not isinstance(values, list) or len(values) != spec.count:
        raise ValueError(f'Wrong {spec.name} number count')
    if any(type(value) is not int for value in values):
        raise ValueError(f'Invalid {spec.name} number')
    maxima = spec.position_maxima or (spec.maximum,) * spec.count
    if any(value < spec.minimum or value > maximum for value, maximum in zip(values, maxima)):
        raise ValueError(f'{spec.name} number out of range')
    if spec.distinct and len(set(values)) != len(values):
        raise ValueError(f'Duplicate {spec.name} number')


def validate_draw(game, issue, zones):
    spec = game_spec(game, issue)
    if not isinstance(zones, dict) or set(zones) != {zone.name for zone in spec.zones}:
        raise ValueError('Wrong zone payload')
    for zone in spec.zones:
        _validate_zone(zone, zones[zone.name])
    if game == 'qlc' and zones['special'][0] in zones['basic']:
        raise ValueError('QLC special number must be distinct from basic numbers')
    return zones


def validate_ticket_data(game, issue, zones):
    return validate_draw(game, issue, zones)


def draw_zones(data):
    if 'zones' in data:
        return data['zones']
    return {key: data[key] for key in ('front', 'back')}
