import numpy as np
import pytest
from lottery.experiments import probability_vectors, weighted_tickets, encoded
from lottery.predict import generate_tickets
from lottery.domain import validate_ticket


def test_indicator_features_are_past_only_and_combine_groups():
    from lottery.indicators import indicator_features, STRATEGIES
    rows=[generate_tickets('ssq',i,1)[0] for i in range(170)]
    x=encoded(rows,'front',33)
    a=indicator_features(x,160,('odd','omission'))
    x[160:]=1
    assert np.array_equal(a,indicator_features(x,160,('odd','omission')))
    assert a.shape[1]>indicator_features(x,160,('odd',)).shape[1]
    assert len(STRATEGIES)==12


def test_omission_uses_completed_gaps_and_marks_unseen():
    from lottery.indicators import omission_features
    x=np.array([[1,0],[0,0],[0,0],[1,0],[0,0]],dtype=float)
    f=omission_features(x)
    # current, maximum completed gap, mean completed gap, latest cycle, unseen, no completed cycle
    assert np.allclose(f[0],[1,2,2,3,0,0])
    assert np.allclose(f[1],[5,0,0,0,1,1])


@pytest.mark.parametrize('game',['ssq','dlt'])
def test_every_indicator_strategy_produces_replayable_five_tickets(game):
    from lottery.indicators import STRATEGIES
    from lottery.prospective import versions
    rows=[generate_tickets(game,i,1)[0] for i in range(160)]
    assert len(versions())==14
    for name in STRATEGIES:
        p=probability_vectors(game,rows,name)
        for key,count in [('front',6 if game=='ssq' else 5),('back',1 if game=='ssq' else 2)]:
            assert np.isfinite(p[key]).all()
            assert all(0<v<1 for v in p[key])
            assert sum(p[key])==pytest.approx(count)
        tickets=weighted_tickets(game,p,31)
        assert len(tickets)==len({str(t) for t in tickets})==5
        assert tickets==weighted_tickets(game,p,31)
        for t in tickets: validate_ticket(game,**t)


def test_cached_training_features_do_not_see_targets_or_future():
    from lottery.indicators import feature_sequence, STRATEGIES, indicator_features
    rows=[generate_tickets('ssq',i,1)[0] for i in range(165)]
    x=encoded(rows,'front',33)
    before=feature_sequence(x,STRATEGIES['freq_all'])
    expected=indicator_features(x,130,STRATEGIES['freq_all'])
    assert np.array_equal(before[100],expected)
    x[130:]=0
    x[130:,:6]=1
    after=feature_sequence(x,STRATEGIES['freq_all'])
    assert all(np.array_equal(a,b) for a,b in zip(before[:101],after[:101]))


def test_structure_numeric_and_association_feature_values():
    from lottery.indicators import feature_groups
    # One is separately classified; 2,3,5 are prime; 4,6 are composite.
    x=np.array([[1,1,0,0,0,0],[0,1,1,0,0,0],[0,0,1,0,1,0]],dtype=float)
    g=feature_groups(x)
    assert np.array_equal(g['prime'][:,0],[1,0,0,0,0,0])
    assert np.array_equal(g['prime'][:,3],[0,1,1,0,1,0])
    assert np.array_equal(g['odd'][:,0],[0,1,0,1,0,1])
    # Last set 3,5: sum8, span2, mean4, AC0, tail sum8.
    assert np.allclose(g['numeric'][0,:5],[8,2,4,0,8])
    assert g['association'][3,1]==2  # 4 neighbors both last-draw balls.
    assert np.array_equal(g['association'][:,0],x[-1])
