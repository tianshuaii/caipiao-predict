import pytest
from lottery.uncertainty import rate_interval,block_interval,paired_uncertainty


def test_wilson_zero_all_and_empty():
    assert rate_interval(0,0)['interval'] is None
    low,high=rate_interval(0,60)['interval']
    assert low==0 and .05<high<.07
    low,high=rate_interval(60,60)['interval']
    assert .93<low<.95 and high==1
    with pytest.raises(ValueError):rate_interval(3,2)


def issues(n):return [f'2026{i+1:03d}' for i in range(n)]


def test_blocks_reproducible_and_refuse_false_precision():
    values=[0.,1.,-1.]*20
    a=block_interval(issues(60),values)
    assert a==block_interval(issues(60),values)
    assert a['sample_unit']=='draw-block' and a['periods']==60 and a['block_length']==5
    assert a['interval'][0]<0<a['interval'][1]
    assert block_interval(issues(10),values[:10])['reason']=='insufficient_periods'
    assert block_interval(issues(60),[0.]*60)['reason']=='constant_observed_difference'
    broken=issues(60);broken[1]='2026100'
    with pytest.raises(ValueError):block_interval(broken,values)
    gaps=issues(4)+[f'2026{i+10:03d}' for i in range(56)]
    assert block_interval(gaps,values)['reason']=='short_contiguous_segment'


def test_paired_unit_and_unknown_money_not_zero():
    from lottery.portfolio import group_result
    loss=group_result([{'level':None,'amount':'0'}],'r',10)
    win=group_result([{'level':6,'amount':'5'}],'r',10)
    unknown=group_result([{'level':1,'amount':None}],'r',10)
    entries=[(i,win if j%2 else loss) for j,i in enumerate(issues(60))]
    controls={i:[loss]*100 for i in issues(60)}
    entries[0]=(issues(60)[0],unknown)
    result=paired_uncertainty(entries,controls,entries[1:])
    assert result['any_prize']['periods']==60
    assert result['net_per_period']['periods']==59
    assert result['first_prize']['interval'] is None
    assert result['first_prize']['reason']=='rare_first_prize_events'
    assert result['control_groups']==100


def test_portfolio_exposes_100_tracks_and_intervals():
    from lottery.portfolio import comparison,group_result,aggregate
    loss=group_result([{'level':None,'amount':'0'}],'r')
    result=comparison([('2026001',loss)],{'2026001':[loss]*100})
    assert len(result['random_tracks'])==100
    assert result['uncertainty']['any_prize']['periods']==1
    assert aggregate([loss])['first_prize_interval']['interval'][1]>0


def test_unequal_segments_preserve_period_weights_and_suppress_degeneracy():
    periods=issues(5)+[f'2026{i+10:03d}' for i in range(55)]
    degenerate=block_interval(periods,[100.]*5+[0.]*55)
    assert degenerate['interval'] is None
    assert degenerate['reason']=='degenerate_resampling_distribution'
    result=block_interval(periods,[100.]*5+([0.,1.,-1.]*19)[:55])
    assert result['interval'][0]>7
    assert [s['periods'] for s in result['segments']]==[5,55]
    assert result['replicates_performed']==2000
