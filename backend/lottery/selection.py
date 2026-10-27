"""Selection protocols; frozen legacy kernels are retained for exact replay."""
import math
import random
import numpy as np
from .domain import GAMES, validate_ticket

def generate_tickets(game, seed, count=5):
    if not 1 <= count <= 10:
        raise ValueError('Count must be between 1 and 10')
    rng = random.Random(seed)
    result, seen = [], set()
    while len(result) < count:
        ticket = {key: sorted(rng.sample(range(1, GAMES[game][key][0] + 1), GAMES[game][key][1])) for key in ['front', 'back']}
        validate_ticket(game, **ticket)
        signature = tuple(ticket['front'] + ticket['back'])
        if signature not in seen:
            seen.add(signature)
            result.append(ticket)
    return result

def weighted_tickets(game, probabilities, seed):
    rng=np.random.default_rng(seed)
    result, seen=[],set()
    while len(result)<5:
        ticket={}
        for key in ['front','back']:
            size,count=GAMES[game][key]
            weights=np.array(probabilities[key],dtype=float)
            ticket[key]=sorted(int(x) for x in rng.choice(np.arange(1,size+1),size=count,replace=False,p=weights/weights.sum()))
        marker=str(ticket)
        if marker not in seen: result.append(ticket);seen.add(marker)
    return result

UNIFORM='uniform-checked-v2'
WEIGHTED='weighted-checked-v2'
EXACT='systematic-marginals-v1'
MAX_ATTEMPTS=2000


def selection_metadata(protocol):
    if protocol not in (UNIFORM,WEIGHTED,EXACT): raise ValueError('Unknown selection protocol')
    return {'protocol':protocol,'input_semantics':'inclusion-marginals' if protocol==EXACT else 'sampling-weights' if protocol==WEIGHTED else 'uniform',
            'actual_inclusion':'equals-input-for-one-ticket' if protocol==EXACT else 'uniform-symmetry' if protocol==UNIFORM else 'not-equal-to-input-in-general',
            'batch_unique':True,'max_attempts':1 if protocol==EXACT else MAX_ATTEMPTS,
            'model_probability_is_sampling_weight':protocol==WEIGHTED,
            'dependency':{'numpy':np.__version__} if protocol!=UNIFORM else {'python_random':'sample-v1'}}


def _validated(game, seed, count, protocol, probabilities):
    if game not in GAMES: raise ValueError('Unknown game')
    if type(seed) is not int or seed<0: raise ValueError('Seed must be a nonnegative integer')
    if type(count) is not int or not 1<=count<=10: raise ValueError('Count must be between 1 and 10')
    selection_metadata(protocol)
    if protocol==UNIFORM:
        if probabilities is not None: raise ValueError('Uniform protocol takes no probabilities')
        return None
    if not isinstance(probabilities,dict) or set(probabilities)!= {'front','back'}:
        raise ValueError('Both probability zones required')
    vectors={};support=1
    for zone in ('front','back'):
        maximum,k=GAMES[game][zone]
        try: values=np.array(probabilities[zone],dtype=float)
        except (TypeError,ValueError) as exc: raise ValueError('Invalid vector') from exc
        if values.shape!=(maximum,) or not np.isfinite(values).all() or (values<0).any():
            raise ValueError('Invalid probability vector')
        total=float(values.sum())
        if not math.isfinite(total) or total<=0: raise ValueError('Invalid probability sum')
        if protocol==EXACT:
            if count!=1 or (values>1).any() or abs(total-k)>1e-10:
                raise ValueError('Exact protocol requires one ticket and marginals in [0,1] summing to pick count')
            vectors[zone]=values
        else: vectors[zone]=values/total
        positive=int(np.count_nonzero(vectors[zone]))
        if positive<k: raise ValueError('Insufficient support')
        support*=math.comb(positive,k)
    if support<count: raise ValueError('Insufficient support for a unique batch')
    return vectors


def select_tickets(game, seed, count=5, *, protocol=UNIFORM, probabilities=None):
    vectors=_validated(game,seed,count,protocol,probabilities)
    rng=random.Random(seed) if protocol==UNIFORM else np.random.default_rng(seed)
    result=[];seen=set()
    for _ in range(1 if protocol==EXACT else MAX_ATTEMPTS):
        ticket={}
        for zone in ('front','back'):
            maximum,k=GAMES[game][zone]
            if protocol==UNIFORM:
                values=sorted(rng.sample(range(1,maximum+1),k))
            elif protocol==WEIGHTED:
                values=sorted(int(v) for v in rng.choice(np.arange(1,maximum+1),size=k,replace=False,p=vectors[zone]))
            else:
                cumulative=np.cumsum(vectors[zone]);cumulative[-1]=float(k)
                values=(np.searchsorted(cumulative,rng.random()+np.arange(k),side='right')+1).tolist()
            ticket[zone]=values
        validate_ticket(game,**ticket)
        signature=tuple(ticket['front']+ticket['back'])
        if signature not in seen:
            seen.add(signature);result.append(ticket)
        if len(result)==count:return result
    raise ValueError('Selection retry budget exhausted; no partial batch returned')


def replay_tickets(game, seed, probabilities, protocol, count=5):
    # Legacy records keep their original RNG and control flow; only trusted stored records use this path.
    if protocol=='legacy-uniform-v1':return generate_tickets(game,seed,count)
    if protocol=='legacy-weighted-v1':
        if count!=5:raise ValueError('Legacy weighted protocol requires five tickets')
        return weighted_tickets(game,probabilities,seed)
    return select_tickets(game,seed,count,protocol=protocol,probabilities=probabilities if protocol!=UNIFORM else None)
