"""Pure tests (no Django):  python tests/test_vendor_my_performance_pure.py
Vendor ke apne Performance dashboard ke qaide (accept rate, prep accuracy, quality score, tips)."""
import importlib.util
import os

_p = os.path.join(os.path.dirname(__file__), '..', 'app', 'utils', 'vendor_perf_rules.py')
_s = importlib.util.spec_from_file_location('vendor_perf_rules', _p)
r = importlib.util.module_from_spec(_s)
_s.loader.exec_module(r)

GOOD = dict(orders=40, accept_rate=95.0, rating=4.5, rating_n=10, prep_on_time_pct=80.0, prep_n=20,
            cancel_rate=5.0, disputes=1)


def test_accept_rate():
    assert r.accept_rate(8, 1, 1) == 80.0
    assert r.accept_rate(5, 0, 0) == 100.0
    assert r.accept_rate(0, 0, 0) is None          # jawab dene ko koi order nahi


def test_prep_on_time_uses_grace():
    assert r.prep_on_time(20, 18) is True
    assert r.prep_on_time(20, 25) is True           # 20 + 5 grace
    assert r.prep_on_time(20, 25.1) is False
    assert r.prep_on_time(None, 10) is None
    assert r.prep_on_time(20, None) is None


def test_score_needs_minimum_orders():
    assert r.quality_score({**GOOD, 'orders': 4}) is None
    assert r.quality_score({}) is None
    assert r.quality_score(None) is None


def test_good_vendor_scores_high():
    s = r.quality_score(GOOD)
    assert 85 <= s <= 100, s
    assert r.score_label(s) == ('Zabardast', 'good')


def test_bad_vendor_scores_low():
    bad = dict(orders=40, accept_rate=40.0, rating=2.0, rating_n=10, prep_on_time_pct=30.0, prep_n=20,
               cancel_rate=40.0, disputes=8)
    s = r.quality_score(bad)
    assert s < 50, s
    assert r.score_label(s) == ('Nazar rakhein', 'bad')


def test_score_ignores_missing_parts():
    only_accept = dict(orders=10, accept_rate=100.0, rating=None, rating_n=0, prep_on_time_pct=None, prep_n=0,
                       cancel_rate=0.0, disputes=0)
    assert r.quality_score(only_accept) == 100       # jo data nahi, wo score ko girata nahi
    few_ratings = {**GOOD, 'rating': 1.0, 'rating_n': 1}   # 1 rating se score nahi girta
    assert r.quality_score(few_ratings) == r.quality_score({**GOOD, 'rating': None, 'rating_n': 0})


def test_score_always_between_0_and_100():
    worst = dict(orders=10, accept_rate=0.0, rating=1.0, rating_n=10, prep_on_time_pct=0.0, prep_n=10,
                 cancel_rate=100.0, disputes=50)
    assert r.quality_score(worst) == 0
    best = dict(orders=10, accept_rate=100.0, rating=5.0, rating_n=10, prep_on_time_pct=100.0, prep_n=10,
                cancel_rate=0.0, disputes=0)
    assert r.quality_score(best) == 100


def test_score_label_bands():
    assert r.score_label(None) == ('Abhi data kam hai', 'na')
    assert r.score_label(85)[1] == 'good'
    assert r.score_label(70)[1] == 'ok'
    assert r.score_label(50)[1] == 'warn'
    assert r.score_label(49)[1] == 'bad'


def test_delta():
    assert r.delta(80, 70) == 10
    assert r.delta(70, 80) == -10
    assert r.delta(None, 70) is None
    assert r.delta(70, None) is None


def test_tips_empty_for_healthy_or_low_data():
    assert r.tips(GOOD) == []
    assert r.tips({**GOOD, 'orders': 3, 'missed': 3}) == []
    assert r.tips({}) == []


def test_tips_point_to_the_problem():
    t = r.tips({**GOOD, 'missed': 2})
    assert len(t) == 1 and '2 order' in t[0]
    t = r.tips({**GOOD, 'accept_rate': 70.0, 'rejected': 3})
    assert any('reject' in x for x in t)
    t = r.tips({**GOOD, 'prep_on_time_pct': 50.0})
    assert any('prep time' in x for x in t)
    t = r.tips({**GOOD, 'cancel_rate': 30.0, 'rating': 3.0, 'disputes': 4})
    assert len(t) == 3


if __name__ == '__main__':
    n = 0
    for name, fn in list(globals().items()):
        if name.startswith('test_'):
            fn(); n += 1
            print('ok ', name)
    print(n, 'tests passed')
