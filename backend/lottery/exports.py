"""Read-only research report; exports do not train, collect or notify."""
import hashlib
import json
from datetime import datetime,timezone
from pathlib import Path
from sqlalchemy import select
from .models import Draw,Experiment
from .ingestion import coverage
from .evaluation import prospective_records
from .performance import performance_report
from .ranking import ranking_status,OBJECTIVES
from .portfolio import portfolio_status

VERSION='research-export-v1'


def canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def statistics_snapshot(directory,game):
    from .statistics import read_report
    unreadable=[]
    # Each artifact keeps its own frozen dataset, not the export's current window.
    for path in sorted(Path(directory).glob('*.json'),key=lambda p:(p.stat().st_mtime,p.name),reverse=True):
        try:
            saved=read_report(path.stem,directory)
            if game not in saved['snapshot']['games']:continue
            rows=saved['snapshot']['games'][game]
            return {'status':'available','id':path.stem,'report':saved['report'],
                    'scope':'完整原报告（可能包含两个彩种），校正检验族不裁剪',
                    'selected_game_cutoff':max((r['issue'] for r in rows),default=None),'unreadable':unreadable}
        except (OSError,ValueError,KeyError,TypeError):unreadable.append({'id':path.stem,'status':'integrity_or_format_error'})
    return {'status':'unavailable','report':None,'unreadable':unreadable}


def build_export(session,game,statistics_directory):
    if game not in ('ssq','dlt'):raise ValueError('Unknown game')
    draws=list(session.scalars(select(Draw).where(Draw.game==game).order_by(Draw.issue)))
    latest=draws[-1] if draws else None
    records=prospective_records(session,game)
    experiment=session.scalar(select(Experiment).where(Experiment.game==game).order_by(Experiment.id.desc()).limit(1))
    historical=None
    if experiment:
        fields=('protocol','dataset_hash','data_mode','evaluation_periods','from_issue','to_issue','training_cutoff',
                'strategies','comparison','performance','random_simulations','random_hit_interval','conclusion')
        historical={'id':experiment.id,'created_at':experiment.created_at.isoformat()+'Z',
                    **{key:experiment.result.get(key) for key in fields},
                    'note':'历史探索性回测，不是前瞻证据；旧报告缺失字段保持null。'}
    data={'version':VERSION,'generated_at':datetime.now(timezone.utc).isoformat(),'game':game,
          'code_sha256':hashlib.sha256(b''.join(p.read_bytes() for p in sorted(Path(__file__).parent.glob('*.py')))).hexdigest(),
          'cutoff':{'issue':latest.issue if latest else None,'draw_date':latest.draw_date.isoformat() if latest else None,
                    'evaluation_issue':max((r['issue'] for r in records),default=None)},
          'draw_manifest':[{'issue':d.issue,'revision':d.revision,'fingerprint':d.fingerprint,'conflict':d.conflict} for d in draws],
          'evaluation_manifest':[{key:r.get(key) for key in ('kind','source_id','issue','cutoff_issue','strategy','status','rule_version','experiment_version','draw_fingerprint')} for r in records],
          'quality':coverage(session,game),
          'rankings':{objective:ranking_status(session,game,objective) for objective in OBJECTIVES},
          'performance':performance_report(records),'portfolio':portfolio_status(session,game),
          'historical_experiment':historical,'statistics':statistics_snapshot(statistics_directory,game),
          'limitations':['公平独立开奖下，历史统计不能保证提高中奖概率。',
                        '当前修订数据的描述性快照；历史回测、前瞻绩效和统计检验使用各自窗口，不可直接混排。',
                        '未知奖金、失败、缺失与未结算状态保留；完整金额交集不代表全部期次收益。',
                        '随机分位数不是置信区间；统计检验为探索性，跨报告挑选不在单报告Holm校正内。',
                        '报表不产生购买建议，不改变策略晋升或微信发送频率。'],
          'hash_method':'sha256 of UTF-8 JSON(data), sorted keys, compact separators, ensure_ascii=False'}
    return {'sha256':hashlib.sha256(canonical(data)).hexdigest(),'data':data}


def encode(report):
    data=report['data'];pretty=json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)
    quality=data['quality'];cutoff=data['cutoff']
    summary=[]
    for objective,ranking in data['rankings'].items():
        summary.append('### 模型比较 · '+objective)
        if not ranking['groups']:summary.append('暂无共同有效样本。')
        for group in ranking['groups']:
            summary.append(f"规则 {group['rule_version']}：共同{len(group['issues'])}期，金额完整{len(group['money_issues'])}期。")
            for row in group['rows']:
                summary.append(f"- {row['strategy']}：值={row['value']}；名次={row['rank']}；原因={row['reason']}")
    summary.append('## 规则绩效')
    if not data['performance']['groups']:summary.append('暂无可统计绩效。')
    for group in data['performance']['groups']:
        summary.append(f"- {group['strategy']} / {group['rule_version']}：{group['periods']}期，净收益={group['net']}，ROI={group['roi']}，待确认{group['pending_tickets']}注。")
    summary.extend(['## 统计检验', '状态：'+data['statistics']['status'], '统计报告使用自身冻结样本；完整检验族、校正值及跳过原因见完整指标。'])
    markdown='\n'.join(['# 彩票研究报表',f"生成于：{data['generated_at']}",f"彩种：{data['game']} · 版本：{data['version']}",
        f"内容 SHA256：{report['sha256']}",f"开奖截止：{cutoff['issue'] or '暂无'} · {cutoff['draw_date'] or '暂无'}",
        f"评估记录目标期截止（可能尚未开奖）：{cutoff['evaluation_issue'] or '暂无'}",
        '## 数据质量',f"记录 {quality['count']} 期；缺失 {quality['missing_count']}；冲突 {quality['conflicts']}；覆盖完整：{quality['complete']}",
        *summary, '## 局限说明',*['- '+line for line in data['limitations']],
        '## 完整指标', '下方保留四目标比较、规则绩效、随机对照、统计检验及缺失/区间原值。null表示未知或不可用，不代表零。',
        '```json',pretty,'```',''])
    return {'report':report,'json':pretty,'markdown':markdown}
