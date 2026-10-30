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
BASELINE_HASHES={'frequency': 'edb2fc2d6487a866f6822fe6c313ff3f44e0bb67b5f7e405cd8decf8f2d7b18e', 'logistic': '911a28902e570b8d3b3eeeee82b4938957a4da449b015ab0ace81b022c65eccf', 'freq_odd': 'bc3932cf722058ee595a7a90062a38088aecf133c256affbdf00bda3c5c594dd', 'freq_size': '68e0bbbcdd13704b5cb23f53aec882cf386859593cd90995fb2389cd0ef1aff1', 'freq_thirds': '93c8351c2e438958e78977e7f56e5a3f832e2996638dd9b4d63f70839b9de7c5', 'freq_prime': 'df56de4565652f9a2dec1be2aafc052e50bca15f81e6f613e5d455bd2382637e', 'freq_omission': 'e1aad3db0241acd22d15fb5e381ada697804e77b3c07d8317a89e1a35af0f778', 'freq_odd_omission': 'd1674896e0fcad267e887d408367acf9b4431874e38a2955d4ab46415be6a9e5', 'freq_structure': '96d9a61bfcafc3e28d04d059bc647f12123718b182dde56df99870f11aba03b3', 'freq_numeric': '7da88d2acc36e6e291314e4d6bfbbed9189635e22bc3ce5dd1fc02bf0f52f37f', 'freq_association': 'bb3a4aaa84c8e6434c78dca46a48f05a531fe6f0b03ae01007059af58a924600', 'freq_all': 'db142dc7378382414f4b2368c2a6984bf8c1226b2b06a2883615fb6ff9f03643', 'forest_all': '51268a6b4bf787472af42c0121ae5d9a9ada1e17e6320d537931cbd635bb0a65', 'neural_all': '23ed213434659b370cd84c2ccebd2ed592aed31b2adb6c4f6629e7a8e0761744'}


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
        factory=(m.forest_estimator if strategy=='forest_all' else m.boost_estimator if strategy=='boost_all'
                 else m.neural_estimator if strategy=='neural_all' else m.ensemble_weights if strategy=='ensemble_all'
                 else m.logistic_estimator)
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
