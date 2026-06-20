import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.modules.entry import OOSProbaEntry

class _Ctx:
    def __init__(self, date): self.day = {"date": date}

def test_oos_proba_entry_membership():
    e = OOSProbaEntry(pass_dates=["2020-03-23", "2020-03-24"])
    assert e.should_market_buy(_Ctx("2020-03-23")) is True
    assert e.should_market_buy(_Ctx("2020-01-01")) is False
    assert e.should_place_limits(_Ctx("2020-03-23")) is False

if __name__ == "__main__":
    test_oos_proba_entry_membership()
    print("OK")
