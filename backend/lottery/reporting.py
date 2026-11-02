from datetime import datetime
import hashlib
from sqlalchemy import select
from .domain import GAMES, TZ
from .game_specs import game_spec, registered_games
from .models import Draw, Prediction, Settlement

def balls(ticket):
    if 'basic' in ticket:
        return ' '.join(f'{n:02d}' for n in ticket['basic']) + ' + 特别 ' + f'{ticket["special"][0]:02d}'
    if 'positions' in ticket:
        return ' '.join(str(n) for n in ticket['positions'][:6]) + ' + ' + str(ticket['positions'][6])
    return ' '.join(f'{n:02d}' for n in ticket['front']) + ' + ' + ' '.join(f'{n:02d}' for n in ticket['back'])


def hit_text(row):
    if 'basic_hits' in row: return f'命中 {row["basic_hits"]}+{row["special_hits"]}'
    if 'position_hits' in row: return f'命中位置 {row["position_hits"]}'
    return f'命中 {row["front_hits"]}+{row["back_hits"]}'

def build_report(session, run, now=None):
    now=now or datetime.now(TZ)
    day = now.strftime('%Y-%m-%d')
    title = f'拾数｜{day} 开奖复盘与下期号码'
    lines = [f'报告 #{run.id} · 北京时间 {now:%Y-%m-%d %H:%M}', '所有金额为单式、不追加的模拟奖金。']
    signature = ['morning-v2']
    for game, info in run.details.items():
        lines.extend(['', f'## {game_spec(game,"2020100" if game=="qxc" else "2026001").name}'])
        latest = session.scalar(select(Draw).where(Draw.game == game).order_by(Draw.issue.desc()).limit(1))
        if latest:
            lines.append(f'最新开奖 {latest.issue}（{latest.draw_date}）：{balls(latest.data)}')
        previous = session.scalar(select(Prediction).join(Draw, (Draw.game == Prediction.game) & (Draw.issue == Prediction.issue)).where(Prediction.game == game).order_by(Prediction.issue.desc()).limit(1))
        actual = session.scalar(select(Draw).where(Draw.game == game, Draw.issue == previous.issue)) if previous else None
        settlement = session.scalar(select(Settlement).where(Settlement.prediction_id == previous.id, Settlement.draw_fingerprint == actual.fingerprint).limit(1)) if actual and not actual.conflict else None
        if settlement:
            lines.append(f'上期复盘 {previous.issue}：')
            for i, row in enumerate(settlement.results, 1):
                amount = '待公布' if row['amount'] is None else row['amount']+' 元'
                level = f'{row["level"]} 等奖' if row['level'] else '未中奖'
                lines.append(f'{i}. {balls(row)} → {hit_text(row)}，{level}，{amount}')
            lines.append(f'成本 {settlement.summary["cost"]} 元；已确认奖金 {settlement.summary["known_amount"]} 元；待结算 {settlement.summary["pending"]} 注。')
            signature.append(settlement.draw_fingerprint)
        else:
            lines.append('上期复盘：开奖数据存在冲突或更正，等待重新核对。' if previous else '上期复盘：暂无可核对的正式预测。')
        if 'error' in info:
            lines.append('本次暂停生成：' + info['error'])
            signature.append(info['error'])
            continue
        p = session.get(Prediction, info['prediction_id'])
        signature.append(str(p.id))
        lines.extend(['', f'下一期 {p.issue} · {p.draw_date} 开奖 · 5 注单式', f'输入数据截止：{p.cutoff_issue}'])
        lines.extend(f'{i}. {balls(t)}' for i,t in enumerate(p.tickets,1))
        lines.append(f'正式策略：{p.strategy}。分析：{p.provenance["rationale"]} 所有预测已冻结入库。')
    return title, '\n\n'.join(lines), hashlib.sha256('|'.join(signature).encode()).hexdigest()


def send_morning_report(now=None):
    from .db import session_factory
    from .domain import next_target
    from .models import CalendarOverride, Run, utcnow
    from .calendar import load_calendar
    from .notify import queue_report, deliver
    from .workflow import workflow_lock
    now=(now or datetime.now(TZ)).astimezone(TZ)
    if now.hour!=8 or now.minute>=5:
        return {'status':'outside_send_window'}
    with workflow_lock(),session_factory()() as session:
        details={}
        for game in registered_games():
            try:
                load_calendar(session,now.year)
                latest=session.scalar(select(Draw).where(Draw.game==game).order_by(Draw.issue.desc()).limit(1))
                if not latest or latest.conflict: raise ValueError('最新开奖数据缺失或冲突')
                closed=list(session.scalars(select(CalendarOverride.day).where(CalendarOverride.game==game,CalendarOverride.closed.is_(True))))
                issue,day,deadline=next_target(game,latest.issue,latest.draw_date,now,[d.isoformat() for d in closed])
                if day.year!=now.year: load_calendar(session,day.year)
                p=session.scalar(select(Prediction).where(Prediction.game==game,Prediction.issue==issue))
                if not p or p.draw_date!=day or now>=datetime.fromisoformat(p.provenance['sales_cutoff']):
                    raise ValueError('本期推荐尚未生成或已经过期，未发送旧号码')
                details[game]={'prediction_id':p.id,'issue':p.issue}
            except Exception as exc:
                details[game]={'error':str(exc)[:200]}
        run=Run(kind='morning-report',status='partial' if any('error' in v for v in details.values()) else 'success',details=details,finished_at=utcnow())
        session.add(run);session.flush()
        title,body,key=build_report(session,run,now)
        notice=queue_report(session,run.id,title,body,key)
        session.commit()
        deliver(session,notice)
        return {'run_id':run.id,'status':run.status,'notification':notice.status}
