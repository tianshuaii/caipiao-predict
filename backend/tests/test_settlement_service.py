import pytest
from test_workflow import draw

@pytest.mark.parametrize('amount,expected',[('5','5'),(None,None)])
def test_shared_settlement_preserves_pending_amount(amount,expected):
    from lottery.settlement import settle_ticket
    actual=draw();actual['prizes']={'6':{'amount':amount}}
    ticket={'front':[7,8,9,10,11,12],'back':[1]}
    assert settle_ticket('ssq',ticket,actual)=={'front_hits':0,'back_hits':1,'level':6,'amount':expected}


def test_shared_settlement_special_award_and_losing_ticket():
    from lottery.settlement import settle_ticket
    actual=draw();actual['prizes']['7']={'amount':'5'}
    assert settle_ticket('ssq',{'front':[1,2,3,10,11,12],'back':[2]},actual)['level']==7
    assert settle_ticket('ssq',{'front':[7,8,9,10,11,12],'back':[2]},actual)['amount']=='0'

@pytest.mark.parametrize('issue,level',[('2019018',4),('2019019',5),('2026014',4)])
def test_shared_settlement_honors_rule_boundaries(issue,level):
    from lottery.settlement import settle_ticket
    actual={'issue':issue,'front':[1,2,3,4,5],'back':[1,2],'prizes':{str(level):{'amount':'100'}}}
    result=settle_ticket('dlt',{'front':[1,2,3,4,6],'back':[1,3]},actual)
    assert result=={'front_hits':4,'back_hits':1,'level':level,'amount':'100'}


@pytest.mark.parametrize('basic,special,level', [
    (7, 1, 1), (7, 0, 2), (6, 1, 3), (6, 0, 4),
    (5, 1, 5), (5, 0, 6), (4, 1, 6), (4, 0, 7), (3, 1, 7),
])
def test_qlc_settlement_covers_every_award_level(basic, special, level):
    from lottery.settlement import settle_ticket
    draw = {'issue':'2026125','zones':{'basic':[1,2,3,4,5,6,7],'special':[8]},
            'prizes':{str(index):{'amount':str(index)} for index in range(1,8)}}
    ticket = {'basic':list(range(1, basic + 1)) + list(range(9, 16 - basic)),
              'special':[8 if special else 30]}
    assert settle_ticket('qlc', ticket, draw)['level'] == level


def test_qxc_settlement_is_position_based_and_allows_repeated_digits():
    from lottery.settlement import settle_ticket
    draw = {'issue':'2026125','zones':{'positions':[2,9,4,5,6,3,2]},
            'prizes':{'1':{'amount':'5000000'}, '2':{'amount':'100000'}}}
    assert settle_ticket('qxc', {'positions':[2,9,4,5,6,3,2]}, draw)['level'] == 1
    assert settle_ticket('qxc', {'positions':[2,9,4,5,6,3,1]}, draw)['level'] == 2
