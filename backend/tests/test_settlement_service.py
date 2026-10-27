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
