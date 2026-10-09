"""Measure win rates per table at no/some/all power items (see game/tables.py)."""
import sys, random, time
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "apbo"))
from game.engine import Table, Seat, State
from game import ai
def run(opp, levels, stock, opp_stock, hand=5, slots=4, bonus=0, me="hard", n=200, seed=1):
    rng=random.Random(seed); wins=0; turns=0; nowild=0; big=0; t=time.time()
    for _ in range(n):
        seats=[Seat("You",[],hand_size=hand,discard_slots=slots)]+[Seat(f"CPU{i}",[]) for i in range(opp)]
        tb=Table.deal(rng,seats,[stock]+[opp_stock]*opp,bonus_wilds={0:bonus})
        ai.autoplay(tb,[me]+[levels]*opp)
        turns+=tb.turns
        if tb.winner==0:
            wins+=1; nowild+= seats[0].wilds_played==0
            big += all(len(s.stock)>=opp_stock/2 for s in seats[1:])
    return wins/n, nowild/n, big/n, turns/n, (time.time()-t)/n
for args in []:# [(1,"easy",10,10),(1,"normal",10,10),(1,"hard",10,10),(1,"hard",20,20),(3,"hard",20,20),(3,"easy",20,20)]:
    print(args, ["%.2f"%x for x in run(*args,n=100)])
print("---")
T=[(1,"easy",10),(2,"easy",10),(1,"normal",10),(3,"easy",15),(2,"normal",15),(1,"hard",15),(3,"normal",20),(2,"hard",20),(3,"hard",25),(3,"hard",30)]
for i,(o,l,st) in enumerate(T,1):
    base=run(o,l,st,st,hand=5,slots=2,n=150)
    mid=run(o,l,st-2,st,hand=6,slots=3,bonus=1,n=150)
    full=run(o,l,max(5,st-6),st,hand=7,slots=4,bonus=3,n=150)
    print(i,o,l,st,"base %.2f/%.2f mid %.2f/%.2f full %.2f/%.2f"%(base[0],base[2],mid[0],mid[2],full[0],full[2]))
