"""Tests for graphshield.refund_online. Pure Python; no HydraDB or MCP servers needed."""
import re

from graphshield import refund_online as ro

CASES = [f'case_{i:03d}' for i in range(150)]


def total_failed(result, system):
    return result['totals'][system]['failed_attempts_total']['mean']


def test_deterministic_for_same_seeds():
    a = ro.run(backend='memory', case_ids=CASES)
    b = ro.run(backend='memory', case_ids=CASES)
    assert a['summary'] == b['summary'] and a['totals'] == b['totals']


def test_learner_beats_both_static_configs_under_drift():
    r = ro.run(backend='memory', case_ids=CASES)
    learned = total_failed(r, 'graphshield_learned')
    assert learned < total_failed(r, 'static_primary_first') * 0.7
    assert learned < total_failed(r, 'static_tuned_at_launch') * 0.7


def test_learner_recovers_after_drift_but_tuned_static_does_not():
    r = ro.run(backend='memory', case_ids=CASES)
    def late(system):  # windows 8-10: end of phase 2, after the replica degraded
        rows = [x for x in r['summary'] if x['system'] == system and x['window'] in (8, 9, 10)]
        return sum(x['failed_attempts_per_case']['mean'] for x in rows) / len(rows)
    assert late('graphshield_learned') < 0.5 * late('static_tuned_at_launch')


def test_stationary_control_reports_the_exploration_cost_honestly():
    r = ro.run(backend='memory', case_ids=CASES, scenario='stationary')
    # A static config tuned for the unchanging regime should win; the learner pays a tax.
    assert total_failed(r, 'static_tuned_at_launch') < total_failed(r, 'graphshield_learned')
    assert r['headline']['failed_attempts_reduction_vs_static_tuned_at_launch_pct'] < 0
    # ...but it must still beat the naive default.
    assert total_failed(r, 'graphshield_learned') < total_failed(r, 'static_primary_first')


def test_route_is_chosen_before_outcome_is_known():
    events = []

    class Spy(ro.StaticRouter):
        def plan(self, index):
            events.append(('plan', index))
            return super().plan(index)

        def observe(self, index, provider, ok):
            events.append(('observe', index))

    ro.run_stream(Spy(ro.PROVIDERS), CASES[:5], seed=7)
    for index in range(5):
        assert events.index(('plan', index)) < events.index(('observe', index))


def test_same_random_draw_is_shared_across_systems():
    assert ro.fails(7, 'case_001', 'orders_primary', 0.5) == ro.fails(7, 'case_001', 'orders_primary', 0.5)


def test_probe_fires_every_nth_case_and_is_counted():
    store = ro.MemoryStore(); store.reset()
    router = ro.LearnedRouter(store, probe_every=10)
    for provider in ro.PROVIDERS:
        router.last_tried[provider] = 5
    router.last_tried['orders_cache'] = 0           # least recently tried
    store.scores.update({'orders_replica': 90, 'orders_primary': 40, 'orders_cache': 30})
    assert router.plan(3)[0] == 'orders_replica'    # normal case: best score first
    assert router.plan(9)[0] == 'orders_cache'      # 10th case: probe stale provider
    assert router.probes == 1


def test_scores_stay_within_bounds_and_follow_outcomes():
    assert ro._ewma(50, True, 0.2) > 50 and ro._ewma(50, False, 0.2) < 50
    assert ro._ewma(100, True, 0.2) == 100 and ro._ewma(0, False, 0.2) == 0


def test_memory_dry_run_is_not_citable_and_writes_a_separate_file(tmp_path, monkeypatch):
    monkeypatch.setattr(ro, 'OUTPUT', tmp_path / 'real.json')
    monkeypatch.setattr(ro, 'OUTPUT_DRYRUN', tmp_path / 'dry.json')
    r = ro.run(backend='memory', case_ids=CASES)
    assert r['citable_as_hydradb_evidence'] is False
    assert ro.save(r).name == 'dry.json'
    assert any('SIMULATED' in text for text in r['limitations'])


class FakeRealHydra:
    """Stands in for RealHydra: stores rewards like ToolVersion.reward, answers resolve()."""
    def __init__(self):
        self.reward = {}
        self.closed = False
        self.queries = 0

    def run(self, query, **kw):
        self.queries += 1
        tid = kw['tid']
        if 'RETURN v.reward' in query:
            return [{'reward': self.reward[tid]}] if tid in self.reward else []
        if 'SET v.reward' in query:
            self.reward[tid] = kw['reward']
            return []
        raise AssertionError('unexpected query: ' + query)

    def resolve(self, key):
        best = max(ro.PROVIDERS, key=lambda p: (self.reward[self.tid(p)], -ro.PROVIDERS.index(p)))
        return {'tools': [{'name': ro.CAPABILITY, 'server': best}]}

    def close(self):
        self.closed = True

    def tid(self, provider):
        from graphshield.real_mcp import stable_id
        return stable_id('tool', f'{provider}::{ro.CAPABILITY}')


def test_hydra_store_uses_hydradb_queries_and_restores_original_rewards():
    db = FakeRealHydra()
    for p in ro.PROVIDERS:
        db.reward[db.tid(p)] = 7                    # pre-existing state to preserve
    result = ro.run(backend='hydradb', case_ids=CASES, store_factory=lambda: ro.HydraStore(db))
    assert result['backend'] == 'hydradb' and result['citable_as_hydradb_evidence'] is True
    assert db.queries > 1000                        # scores really round-trip through the DB layer
    assert all(db.reward[db.tid(p)] == 7 for p in ro.PROVIDERS)   # restored
    assert db.closed                                # connection closed even on success


def test_hydra_store_refuses_unseeded_graph():
    db = FakeRealHydra()                            # nothing seeded
    try:
        ro.HydraStore(db)
    except ValueError as exc:
        assert re.search('not seeded', str(exc))
    else:
        raise AssertionError('expected ValueError')
