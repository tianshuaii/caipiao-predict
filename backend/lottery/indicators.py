"""Past-only indicator ablations. Features are evidence to learn, not betting rules."""
from functools import lru_cache
import numpy as np

STRATEGIES = {
    'freq_odd': ('odd',),
    'freq_size': ('size',),
    'freq_thirds': ('thirds',),
    'freq_prime': ('prime',),
    'freq_omission': ('omission',),
    'freq_odd_omission': ('odd', 'omission'),
    'freq_structure': ('odd', 'size', 'thirds', 'prime'),
    'freq_numeric': ('numeric',),
    'freq_association': ('association',),
    'freq_all': ('odd', 'size', 'thirds', 'prime', 'omission', 'numeric', 'association'),
}

STRATEGIES.update({name: STRATEGIES['freq_all'] for name in ('forest_all', 'neural_all')})

def omission_features(past):
    n, maximum = past.shape
    result = []
    for j in range(maximum):
        positions = np.flatnonzero(past[:, j])
        gaps = np.diff(positions)-1
        result.append([n-1-positions[-1] if len(positions) else n,
                       gaps.max() if len(gaps) else 0,
                       gaps.mean() if len(gaps) else 0,
                       gaps[-1]+1 if len(gaps) else 0,
                       not len(positions), not len(gaps)])
    return np.asarray(result, dtype=float)


def group_features(past, labels):
    """Membership, recent per-number group rate, last draw group count."""
    columns = []
    for label in np.unique(labels):
        member = (labels == label).astype(float)
        recent = past[-30:, labels == label].mean()
        last = past[-1, labels == label].sum()
        columns.extend([member, member*recent, member*last])
    return np.stack(columns, axis=1)


def feature_groups(past):
    n, maximum = past.shape
    numbers = np.arange(1, maximum+1)
    last = past[-1]
    chosen = numbers[last.astype(bool)]
    count = len(chosen)
    prime = np.array([v>=2 and all(v%d for d in range(2,int(v**.5)+1)) for v in numbers])
    # 1 is neither prime nor composite.
    prime_labels = np.where(numbers == 1, 0, np.where(prime, 1, 2))
    differences = {int(b-a) for i,a in enumerate(chosen) for b in chosen[i+1:]}
    numeric = np.array([chosen.sum(),np.ptp(chosen),chosen.mean(),
                        len(differences)-max(0,count-1),sum(chosen%10)],dtype=float)
    position = numbers/maximum
    # Context alone is constant across numbers. Interactions let it affect ranking.
    numeric_features = np.column_stack([np.tile(numeric,(maximum,1)),
                                        position[:,None]*numeric,
                                        (numbers%2)[:,None]*numeric])
    joint = past[-100:].T @ past[-100:]
    np.fill_diagonal(joint,0)
    distance = np.abs(numbers[:,None]-numbers)
    neighbors = distance == 1
    same_tail = (numbers[:,None]%10 == numbers%10) & (distance>0)
    association = np.column_stack([last, neighbors@last, same_tail@last,
                                   np.sum(joint*neighbors,axis=1)/min(n,100),
                                   np.sum(joint*same_tail,axis=1)/min(n,100),
                                   joint@last/(min(n,100)*count)])
    return {
        'odd': group_features(past,numbers%2),
        'size': group_features(past,(numbers>maximum//2).astype(int)),
        'thirds': group_features(past,np.minimum((numbers-1)*3//maximum,2)),
        'prime': group_features(past,prime_labels),
        'omission': omission_features(past),
        'numeric': numeric_features,
        'association': association,
    }


def indicator_features(matrix, stop, groups):
    past=matrix[:stop]
    base=np.stack([past[-30:].mean(axis=0),past[-100:].mean(axis=0),past[-1]],axis=1)
    available=feature_groups(past)
    columns=[base]
    for group in groups:
        values=available[group]
        # Explicit frequency interactions, including frequency × parity × omission.
        columns.extend([values,base[:,0,None]*values])
    if 'odd' in groups and 'omission' in groups:
        odd=np.arange(1,matrix.shape[1]+1)%2
        current=available['omission'][:,0]
        columns.extend([(odd*current)[:,None],(base[:,0]*odd*current)[:,None]])
    return np.concatenate(columns,axis=1)


@lru_cache(maxsize=4)
def _bank(raw, shape):
    matrix=np.frombuffer(raw,dtype=np.float64).reshape(shape)
    # Cache shared groups across strategies; no labels/target draw are used.
    return [(np.stack([matrix[max(0,t-30):t].mean(axis=0),matrix[max(0,t-100):t].mean(axis=0),matrix[t-1]],axis=1),
             feature_groups(matrix[:t])) for t in range(30,len(matrix)+1)]


def feature_sequence(matrix, groups):
    bank=_bank(np.asarray(matrix,dtype=np.float64).tobytes(),matrix.shape)
    result=[]
    odd=np.arange(1,matrix.shape[1]+1)%2
    for base,available in bank:
        columns=[base]
        for group in groups:
            values=available[group]
            columns.extend([values,base[:,0,None]*values])
        if 'odd' in groups and 'omission' in groups:
            current=available['omission'][:,0]
            columns.extend([(odd*current)[:,None],(base[:,0]*odd*current)[:,None]])
        result.append(np.concatenate(columns,axis=1))
    return result
