"""Compatibility bridge for the unchanged pre-refactor generation protocol.

Only a matching generation fingerprint can retain the historical model IDs.
Full model/feature/selection registries are a later migration (T10).
"""
import hashlib
import inspect
import json
from pathlib import Path
import numpy as np
import scipy
import sklearn

BASELINE_GENERATION_SHA256 = '049ae6d9ffeb1018543cdfff492efba418dee1b2a17089860530b5aacceb91e6'
REFACTORED_GENERATION_SHA256 = '6ec0893574bcebd8fb15869f086585cc330f1b62e987a632e62ddf9c03ba6248'
LEGACY_VERSIONS = {'frequency': 'frequency-v1-4b309d2ad9b6d8c3', 'logistic': 'logistic-v1-4b309d2ad9b6d8c3', 'freq_odd': 'freq_odd-v1-4b309d2ad9b6d8c3', 'freq_size': 'freq_size-v1-4b309d2ad9b6d8c3', 'freq_thirds': 'freq_thirds-v1-4b309d2ad9b6d8c3', 'freq_prime': 'freq_prime-v1-4b309d2ad9b6d8c3', 'freq_omission': 'freq_omission-v1-4b309d2ad9b6d8c3', 'freq_odd_omission': 'freq_odd_omission-v1-4b309d2ad9b6d8c3', 'freq_structure': 'freq_structure-v1-4b309d2ad9b6d8c3', 'freq_numeric': 'freq_numeric-v1-4b309d2ad9b6d8c3', 'freq_association': 'freq_association-v1-4b309d2ad9b6d8c3', 'freq_all': 'freq_all-v1-4b309d2ad9b6d8c3', 'forest_all': 'forest_all-v1-4b309d2ad9b6d8c3', 'neural_all': 'neural_all-v1-4b309d2ad9b6d8c3'}


def generation_fingerprint():
    from . import experiments, indicators, model_training
    parts=[inspect.getsource(getattr(experiments,name)) for name in
           ('encoded','features','probability_vectors','weighted_tickets')]
    raw=''.join(parts)+Path(indicators.__file__).read_text()+json.dumps(experiments.PROTOCOL,sort_keys=True)+np.__version__+scipy.__version__+sklearn.__version__
    raw+=Path(model_training.__file__).read_text()
    return hashlib.sha256(raw.encode()).hexdigest()


def registered_versions():
    from .experiment_registry import registered_versions as registered
    return registered()
