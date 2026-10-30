"""Bounded sequence-model feasibility evidence; this does not register a candidate."""
import resource
import time
import numpy as np
from .domain import GAMES
from .experiments import encoded, probability_vectors


def assess(game,history,holdouts=3):
    """Compare a small existing neural proxy against uniform on chronological splits.

    The production image intentionally has no LSTM/Transformer runtime.  This
    report records that constraint and uses the existing compact neural model
    only to bound the likely cost before adding a new dependency.
    """
    if game not in GAMES or holdouts<1 or len(history)<160+holdouts:
        raise ValueError('Need at least 160 training rows plus requested holdouts')
    started=time.monotonic()
    rows=[]
    for index in range(len(history)-holdouts,len(history)):
        past=history[index-160:index]
        target=history[index]
        probabilities=probability_vectors(game,past,'neural_all')
        actual=np.concatenate([encoded([target],key,GAMES[game][key][0])[0] for key in ('front','back')])
        uniform=np.concatenate([np.full(GAMES[game][key][0],GAMES[game][key][1]/GAMES[game][key][0])
                                for key in ('front','back')])
        predicted=np.array(probabilities['front']+probabilities['back'])
        rows.append({'cutoff_issue':past[-1]['issue'],'target_issue':target['issue'],
                     'uniform_brier':float(np.mean((uniform-actual)**2)),
                     'neural_proxy_brier':float(np.mean((predicted-actual)**2))})
    return {'decision':'not_adopted','reason':'LSTM/Transformer runtime absent; compact proxy is exploratory only',
            'sequence_runtime':'not_installed','future_isolation':True,'training_window':160,
            'splits':rows,'elapsed_seconds':time.monotonic()-started,
            'max_rss_kib':int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)}
