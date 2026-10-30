"""Fit/calibrate once; retain estimators and next-context inputs for exact replay."""
from dataclasses import dataclass
import hashlib
import json
import platform
import warnings
import numpy as np
import scipy
import sklearn
from scipy.optimize import brentq
from scipy.special import expit, logit
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.neural_network import MLPClassifier
from sklearn.exceptions import ConvergenceWarning
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from .domain import GAMES, validate_ticket
from .indicators import STRATEGIES
from .feature_service import feature_sequence

MODEL_FORMAT='trained-context-v1'
FEATURE_VERSION='legacy-indicators-v1'


def environment():
    return {'python':platform.python_version(),'numpy':np.__version__,
            'scipy':scipy.__version__,'sklearn':sklearn.__version__}


@dataclass
class TrainedModel:
    metadata: dict
    zones: dict


def model_scores(estimator, values, nonlinear):
    if nonlinear:
        return logit(np.clip(estimator.predict_proba(values)[:,1],1e-8,1-1e-8))
    return estimator.decision_function(values)


def calibrate_scores(scores, labels, seed):
    calibrator=LogisticRegression(C=1,max_iter=500,random_state=seed)
    calibrator.fit(scores.reshape(-1,1),labels)
    return calibrator


def parameters(estimator):
    if hasattr(estimator,'steps'):
        return {name:parameters(step) for name,step in estimator.steps}
    return {'class':type(estimator).__name__,'parameters':estimator.get_params(deep=False)}


def forest_estimator(seed):
    return RandomForestClassifier(n_estimators=64,max_depth=4,min_samples_leaf=30,n_jobs=1,random_state=seed)


def neural_estimator(seed):
    return make_pipeline(StandardScaler(),MLPClassifier(hidden_layer_sizes=(16,),activation='tanh',solver='lbfgs',alpha=10,max_iter=500,max_fun=15000,tol=1e-3,early_stopping=False,random_state=seed))


def boost_estimator(seed):
    return HistGradientBoostingClassifier(max_iter=48,learning_rate=.05,max_leaf_nodes=8,
                                         l2_regularization=10,early_stopping=False,random_state=seed)


def ensemble_weights():
    """Pre-registered, target-independent blend; no target-period tuning."""
    return {'forest_all': 1/3,'boost_all': 1/3,'neural_all': 1/3}


def logistic_estimator(seed):
    return make_pipeline(StandardScaler(),LogisticRegression(C=.1,max_iter=500,random_state=seed))


def fit_model(game, history, strategy):
    # Imported at call time to keep the public experiment protocol authoritative.
    from .experiments import PROTOCOL, encoded, features
    from .generation_versions import generation_fingerprint
    from .experiment_registry import describe, fingerprint
    if game not in GAMES or strategy not in ('uniform','frequency','logistic',*STRATEGIES):
        raise ValueError('Unknown game or strategy')
    selected=history[-PROTOCOL['training_window']:]
    for row in selected:
        validate_ticket(game,row['front'],row['back'])
        if row.get('conflict'): raise ValueError('Unresolved source conflict')
    issues=[r.get('issue') for r in selected]
    if any(issues) and not all(issues): raise ValueError('Partial issue labels')
    if all(issues) and (issues!=sorted(issues) or len(set(issues))!=len(issues)):
        raise ValueError('History must be chronological and unique')
    n=len(selected);cut=n-PROTOCOL['calibration_draws']
    learned=strategy not in ('uniform','frequency') and n>=60
    if learned and cut<=30: raise ValueError('Insufficient fit/calibration history')
    snapshot=[{k:r.get(k) for k in ('issue','front','back')} for r in selected]
    metadata={'experiment':describe(strategy),'experiment_hash':fingerprint(strategy),'implementation_hash':generation_fingerprint(),'format':MODEL_FORMAT,'game':game,'strategy':strategy,'feature_version':FEATURE_VERSION,
              'feature_groups':list(STRATEGIES.get(strategy,())), 'environment':environment(),
              'protocol':dict(PROTOCOL),'seed':PROTOCOL['seed'],'training_window':PROTOCOL['training_window'],
              'history_issues':issues,'history_count':n,'cutoff_issue':issues[-1] if issues else None,
              'fit_issues':issues[30:cut] if learned else [],
              'calibration_issues':issues[cut:] if learned else [],
              'effective_model':strategy if n>=60 else 'uniform-short-history',
              'dataset_hash':hashlib.sha256(json.dumps(snapshot,sort_keys=True).encode()).hexdigest(),
              'parameters':{}}
    zones={}
    for key in ('front','back'):
        maximum,count=GAMES[game][key];prior=count/maximum
        matrix=encoded(selected,key,maximum)
        if strategy=='uniform' or n<60:
            zones[key]={'probabilities':np.full(maximum,prior)}
            metadata['parameters'][key]={'prior':prior}
        elif strategy=='frequency':
            zones[key]={'probabilities':(matrix[-100:].sum(axis=0)+20*prior)/(min(n,100)+20)}
            metadata['parameters'][key]={'window':100,'smoothing':20,'prior':prior}
        elif strategy=='ensemble_all':
            components={name:fit_model(game,history,name).zones[key] for name in ensemble_weights()}
            zones[key]={'components':components,'weights':ensemble_weights()}
            metadata['parameters'][key]={'blend':ensemble_weights()}
        else:
            sequence=feature_sequence(matrix,STRATEGIES[strategy]) if strategy in STRATEGIES else [features(matrix,t) for t in range(30,n+1)]
            x=np.concatenate(sequence[:cut-30]);y=matrix[30:cut].reshape(-1)
            if strategy=='forest_all':
                estimator=forest_estimator(PROTOCOL['seed'])
            elif strategy=='boost_all':
                estimator=boost_estimator(PROTOCOL['seed'])
            elif strategy=='neural_all':
                estimator=neural_estimator(PROTOCOL['seed'])
            else:
                estimator=logistic_estimator(PROTOCOL['seed'])
            nonlinear=strategy in ('forest_all','boost_all','neural_all')
            with warnings.catch_warnings():
                if nonlinear: warnings.simplefilter('error',ConvergenceWarning)
                estimator.fit(x,y)
            calibration_x=np.concatenate(sequence[cut-30:-1]);calibration_y=matrix[cut:].reshape(-1)
            calibrator=calibrate_scores(model_scores(estimator,calibration_x,nonlinear),calibration_y,PROTOCOL['seed'])
            zones[key]={'estimator':estimator,'calibrator':calibrator,'context':sequence[-1].copy(),'nonlinear':nonlinear}
            metadata['parameters'][key]={'estimator':parameters(estimator),'calibrator':parameters(calibrator)}
    return TrainedModel(metadata,zones)


def predict_model(trained):
    """Predict only the next context captured at training cutoff; never retrain on load."""
    result={};game=trained.metadata['game']
    for key,zone in trained.zones.items():
        if 'probabilities' in zone: p=zone['probabilities']
        elif 'components' in zone:
            p=sum(weight*_predict_zone(game,key,zone['components'][name])
                  for name,weight in zone['weights'].items())
        else:
            p=_predict_zone(game,key,zone)
        result[key]=p.tolist()
    return result


def _predict_zone(game,key,zone):
    scores=model_scores(zone['estimator'],zone['context'],zone['nonlinear'])
    p=zone['calibrator'].predict_proba(scores.reshape(-1,1))[:,1]
    logits=logit(np.clip(p,1e-8,1-1e-8));count=GAMES[game][key][1]
    shift=brentq(lambda v:float(expit(logits+v).sum()-count),-50,50)
    return expit(logits+shift)
