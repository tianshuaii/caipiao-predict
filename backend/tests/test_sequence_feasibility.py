from lottery.predict import generate_tickets


def test_sequence_feasibility_uses_time_split_and_does_not_adopt_runtime():
    from lottery.sequence_feasibility import assess
    history=[dict(generate_tickets('ssq',seed,1)[0],issue=f'2025{seed:03d}')
             for seed in range(163)]
    report=assess('ssq',history,holdouts=3)
    assert report['decision']=='not_adopted'
    assert report['future_isolation'] is True
    assert report['sequence_runtime']=='not_installed'
    assert len(report['splits'])==3
    assert all(row['cutoff_issue']<row['target_issue'] for row in report['splits'])
    assert report['elapsed_seconds']>=0
