"""Content-addressed experiment recipes with explicit legacy identity aliases."""
import ast
import hashlib
import inspect
import json
import textwrap
from .generation_versions import LEGACY_VERSIONS

SCHEMA='experiment-recipe-v1'
EVIDENCE_PROTOCOL='prospective-e-v1'
LEGACY_SELECTION='numpy-weighted-without-replacement-five-unique-v1'
# Filled once from the probability-equivalent T10 baseline, never regenerated at runtime.
BASELINE_HASHES={'frequency': '47e069efec4c20ac7425ac451f101daa7a3f867f22485c10613e35013f944396', 'logistic': 'f53bc70d0c4724818eac37fb9f472d11887aa6ada26b0499d5405c50787efee0', 'freq_odd': 'd1e68be7748cc1402a0a190c340411085c776eb274231976df97e95ee7bdbe33', 'freq_size': '260e28b6b9cb8165d01a882fc1e7fd702f91a92565413b1cae1445c92d539d9f', 'freq_thirds': 'd7e7d917ecbd2aeb7587817d69f2d7f52d7951a7472c1a05053293f64bf525d8', 'freq_prime': 'b70d0d738e77ab4022b8565e670285fbaf462c087e5dca506ec23d86cd71ac58', 'freq_omission': 'b6c05f2a3090ba8a082afd074fddf380c04b4dc9dbd8f8cf4788245b4cf97044', 'freq_odd_omission': '9d9a1c69c32cf6a5c4a2ccc5048bc6952a5d1171051dbd6170b1d2a04936ccad', 'freq_structure': 'cb1cfd3470a2d183cebf8c1ac228b4340734fd6ab08b10cf4178af1124989b29', 'freq_numeric': 'ba02e8ce020f44d2fde0701d9773e212d5709807eb09e8f28d1130a5a88685b2', 'freq_association': '91b99c5fa2fc94d8d29d0279b297bf0d0e0a5edf0528ca639bdf6fc7d9b6742d', 'freq_all': 'f36f2d7b84fe1d814862c8bc4b28d40a763984f91acf020de64625f144284f5d', 'forest_all': '49a7194f7599cac470333c6c552a65fd5727ca945e7f015fa985ef343b49ab3b', 'neural_all': '6cd8e30d4a3c32df548b4ef153b4c869c3923d98379bd16b71041859f9ade9e2'}


class _WithoutDocstrings(ast.NodeTransformer):
    def visit_FunctionDef(self,node):
        self.generic_visit(node)
        if node.body and isinstance(node.body[0],ast.Expr) and isinstance(node.body[0].value,ast.Constant) and isinstance(node.body[0].value.value,str):
            node.body=node.body[1:]
        return node


def source_digest(source):
    tree=_WithoutDocstrings().visit(ast.parse(textwrap.dedent(source)))
    return hashlib.sha256(ast.dump(tree,include_attributes=False).encode()).hexdigest()


def _digest(function):
    return source_digest(inspect.getsource(function))


def describe(strategy,selection_protocol=None):
    from . import selection
    selection_protocol=selection_protocol or selection.WEIGHTED
    if selection_protocol not in (LEGACY_SELECTION,selection.WEIGHTED): raise ValueError('Unsupported candidate selection protocol')
    from . import experiments as e, indicators as i, model_training as m
    from .domain import GAMES, validate_ticket, prize_level, rule_version
    from .settlement import settle_ticket
    from . import prospective as prospective
    if strategy not in ('uniform','frequency','logistic',*i.STRATEGIES):
        raise ValueError('Unknown strategy')
    learned=strategy not in ('uniform','frequency')
    config={key:e.PROTOCOL[key] for key in ('training_window','seed','tickets_per_draw')}
    if learned: config['calibration_draws']=e.PROTOCOL['calibration_draws']
    components={'fit':_digest(m.fit_model),'predict':_digest(m.predict_model),
                'encode':_digest(e.encoded),'validation':_digest(validate_ticket),
                'selection':_digest(e.weighted_tickets)}
    if learned:
        factory=m.forest_estimator if strategy=='forest_all' else m.neural_estimator if strategy=='neural_all' else m.logistic_estimator
        components.update(estimator=_digest(factory),scores=_digest(m.model_scores),calibration=_digest(m.calibrate_scores))
        if strategy in i.STRATEGIES:
            components.update({name:_digest(getattr(i,name)) for name in ('feature_sequence','_bank','feature_groups','group_features','omission_features')})
        else: components['features']=_digest(e.features)
    if selection_protocol==selection.WEIGHTED:
        components.update(selection=_digest(selection.select_tickets),selection_validation=_digest(selection._validated),selection_metadata=_digest(selection.selection_metadata))
        config['selection_max_attempts']=selection.MAX_ATTEMPTS
    env=m.environment()
    return {'schema':SCHEMA,'strategy':strategy,'config':config,
            'feature_groups':list(i.STRATEGIES.get(strategy,())),
            'feature_version':m.FEATURE_VERSION if learned else 'frequency-prior-v1',
            'components':components,'environment':env,
            'games':{game:{zone:list(spec[zone]) for zone in ('front','back')} for game,spec in GAMES.items()},
            'selection_protocol':selection_protocol,
            'evidence_protocol':EVIDENCE_PROTOCOL,
            'evidence':{'minimum_samples':prospective.MIN_SAMPLES,'lambdas':list(prospective.LAMBDAS),
                        'score':_digest(prospective.score_candidates),'gate':_digest(prospective.evidence),
                        'aggregation':_digest(prospective.status),'choice':_digest(prospective.choose),
                        'promotion':_digest(prospective.select_strategy),
                        'settlement':_digest(settle_ticket),'prize':_digest(prize_level),'rule':_digest(rule_version)}}


def fingerprint(strategy,selection_protocol=None):
    return hashlib.sha256(json.dumps(describe(strategy,selection_protocol),sort_keys=True,separators=(',',':')).encode()).hexdigest()


def registered_versions(selection_protocol=None):
    from .indicators import STRATEGIES
    result={}
    for strategy in ('frequency','logistic',*STRATEGIES):
        digest=fingerprint(strategy,selection_protocol)
        result[strategy]=LEGACY_VERSIONS[strategy] if digest==BASELINE_HASHES.get(strategy) else f'{strategy}-v2-{digest[:32]}'
    return result
