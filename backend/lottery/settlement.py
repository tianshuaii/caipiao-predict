"""Shared settlement for basic single tickets; amounts use the actual bulletin.

Compound/banker/add-on purchases are not accepted by this interface. Unknown
winning amounts remain None. Historical prize groups are resolved by issue.
"""
from decimal import Decimal
from .domain import prize_level, validate_ticket
from .game_specs import validate_draw


def settle_ticket(game, ticket, draw):
    if game == 'qlc':
        validate_draw(game, draw['issue'], ticket)
        actual=draw['zones'];validate_draw(game, draw['issue'], actual)
        basic=len(set(ticket['basic']) & set(actual['basic']))
        special=int(ticket['special'][0] == actual['special'][0])
        levels={(7,1):1,(7,0):2,(6,1):3,(6,0):4,(5,1):5,(5,0):6,(4,1):6,(4,0):7,(3,1):7}
        level=levels.get((basic,special))
        return {'basic_hits':basic,'special_hits':special,'level':level,
                'amount':draw.get('prizes',{}).get(str(level),{}).get('amount') if level else '0'}
    if game == 'qxc':
        validate_draw(game, draw['issue'], ticket)
        actual=draw['zones'];validate_draw(game, draw['issue'], actual)
        front=sum(a==b for a,b in zip(ticket['positions'][:6],actual['positions'][:6]))
        back=int(ticket['positions'][6] == actual['positions'][6])
        levels={(6,1):1,(6,0):2,(5,1):3,(5,0):4,(4,1):4,(4,0):5,(3,1):5,(3,0):6,(2,1):6,(1,1):6,(0,1):6}
        level=levels.get((front,back))
        return {'position_hits':front+back,'front_hits':front,'back_hits':back,'level':level,
                'amount':draw.get('prizes',{}).get(str(level),{}).get('amount') if level else '0'}
    validate_ticket(game,ticket['front'],ticket['back'])
    validate_ticket(game,draw['front'],draw['back'])
    front=len(set(ticket['front']) & set(draw['front']))
    back=len(set(ticket['back']) & set(draw['back']))
    level=prize_level(game,draw['issue'],front,back)
    prizes=draw.get('prizes',{})
    special=prizes.get('7',{}).get('amount')
    if game=='ssq' and (front,back)==(3,0) and special and Decimal(special)>0:
        level=7
    amount=prizes.get(str(level),{}).get('amount') if level else '0'
    return {'front_hits':front,'back_hits':back,'level':level,'amount':amount}
