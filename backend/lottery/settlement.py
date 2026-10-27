"""Shared settlement for basic single tickets; amounts use the actual bulletin.

Compound/banker/add-on purchases are not accepted by this interface. Unknown
winning amounts remain None. Historical prize groups are resolved by issue.
"""
from decimal import Decimal
from .domain import prize_level, validate_ticket


def settle_ticket(game, ticket, draw):
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
