"""Trusted local model store. Never use this loader for uploaded/external files.

Hash verification detects corruption, not an attacker who can write this directory.
Only a content ID is accepted; no public API exposes model loading or uploads.
"""
import hashlib
import json
import os
from pathlib import Path
import pickle
import re
import tempfile
from .model_training import MODEL_FORMAT, TrainedModel, environment
from .generation_versions import generation_fingerprint
from .experiment_registry import fingerprint, LEGACY_SELECTION


def save_model(model, directory):
    directory=Path(directory);directory.mkdir(mode=0o700,parents=True,exist_ok=True)
    header=json.dumps({'format':MODEL_FORMAT,'environment':model.metadata['environment'],'implementation_hash':model.metadata['implementation_hash'],'experiment_hash':model.metadata['experiment_hash'],'strategy':model.metadata['strategy'],'selection_protocol':model.metadata['experiment']['selection_protocol']},sort_keys=True).encode()
    raw=header+b'\n'+pickle.dumps(model,protocol=5)
    identity=hashlib.sha256(raw).hexdigest();target=directory/(identity+'.pkl')
    with tempfile.NamedTemporaryFile(dir=directory,delete=False) as stream:
        temporary=Path(stream.name)
        try:
            stream.write(raw);stream.flush();os.fsync(stream.fileno())
            try: os.link(temporary,target)
            except FileExistsError:
                if target.is_symlink() or target.read_bytes()!=raw:
                    raise ValueError('Existing model artifact hash mismatch')
        finally: temporary.unlink(missing_ok=True)
    return {'id':identity,'format':MODEL_FORMAT,'metadata':model.metadata}


def load_model(identity, directory):
    if not isinstance(identity,str) or not re.fullmatch(r'[0-9a-f]{64}',identity):
        raise ValueError('Invalid model artifact ID')
    path=Path(directory)/(identity+'.pkl')
    with os.fdopen(os.open(path,os.O_RDONLY|os.O_NOFOLLOW),'rb') as stream: raw=stream.read()
    if hashlib.sha256(raw).hexdigest()!=identity: raise ValueError('Model artifact hash mismatch')
    header,payload=raw.split(b'\n',1);manifest=json.loads(header)
    if manifest.get('format')!=MODEL_FORMAT: raise ValueError('Unsupported model format')
    if manifest.get('environment')!=environment(): raise ValueError('Model environment mismatch')
    if 'experiment_hash' in manifest:
        if manifest['experiment_hash']!=fingerprint(manifest['strategy'],manifest.get('selection_protocol',LEGACY_SELECTION)): raise ValueError('Model implementation mismatch')
    elif manifest.get('implementation_hash')!=generation_fingerprint(): raise ValueError('Model implementation mismatch')
    model=pickle.loads(payload)
    if not isinstance(model,TrainedModel) or model.metadata['environment']!=manifest['environment']:
        raise ValueError('Invalid trained model')
    return model
