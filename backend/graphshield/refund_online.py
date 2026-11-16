"""Online learning under drift: does GraphShield keep up when providers change?

WHAT THIS MEASURES
    A stream of 150 refund-desk cases arrives one at a time. Each case needs the
    `resolve_order` capability, which three providers offer (primary / replica /
    cache). Their reliability CHANGES twice during the stream (see PHASES), as
    real services do after a deploy or an incident.

    Three systems handle the same stream:
      * static_primary_first   - the naive default: always try primary, then replica, then cache.
      * static_tuned_at_launch - an operator measured phase 1, found replica best,
                                 and hard-coded replica first. Never updated again.
      * graphshield_learned    - ranks providers from success scores stored in HydraDB
                                 (ToolVersion.reward), updates them after every attempt,
                                 and probes the least-recently-tried provider every 10th case.

    All three get the same retry budget (up to 3 providers per case), so the
    comparison is "failed attempts and first-try success", not "who retries".

HONESTY NOTES (also written into the results file)
    * Failure rates are SIMULATED, declared in PHASES. They are not production data.
    * Evaluation is prequential: the route for case i is chosen BEFORE its outcome
      is known, and only then is the score updated. No future information is used.
    * Outcomes are paired across systems: the same (seed, case, provider) draws the
      same random number, so differences come from routing, not luck.
    * Probe attempts that fail are counted as failures. Exploration is not free.
    * With backend=hydradb, the scores live in HydraDB and the first-choice provider
      comes from a real `resolve()` traversal. With backend=memory (dry run), the
      result file is named differently and must not be cited as HydraDB evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / 'results' / 'refund_desk_online_learning.json'
OUTPUT_DRYRUN = ROOT / 'results' / 'refund_desk_online_learning_MEMORY_DRYRUN.json'

PROVIDERS = ['orders_primary', 'orders_replica', 'orders_cache']   # default order = tie-break order
TASK_KEY = 'refund_desk_first_request'
CAPABILITY = 'resolve_order'
NEUTRAL_PRIOR = 50          # starting score (0-100) for every provider
MAX_ATTEMPTS = 3            # same retry budget for every system
WINDOW = 10                 # cases per reporting window

# Simulated failure probability per provider, by case-index phase.
PHASES = [
    {'name': 'phase 1: replica is best',  'start': 0,   'rates': {'orders_primary': 0.45, 'orders_replica': 0.07, 'orders_cache': 0.15}},
    {'name': 'phase 2: replica degrades', 'start': 50,  'rates': {'orders_primary': 0.05, 'orders_replica': 0.55, 'orders_cache': 0.15}},
    {'name': 'phase 3: cache is best',    'start': 100, 'rates': {'orders_primary': 0.40, 'orders_replica': 0.45, 'orders_cache': 0.04}},
]
# Control: nothing ever changes. A static config tuned for this regime should do
# best here, and the learner should pay a small exploration cost. Reported honestly.
STATIONARY = [{'name': 'no drift: replica is best throughout', 'start': 0, 'rates': PHASES[0]['rates']}]
SCENARIOS = {'drift': PHASES, 'stationary': STATIONARY}
SYSTEMS = ['static_primary_first', 'static_tuned_at_launch', 'graphshield_learned']


def phase_at(index, phases=PHASES):
    return [p for p in phases if p['start'] <= index][-1]


def fails(seed, case_id, provider, rate):
    """Stable Bernoulli draw shared by every system (paired comparison)."""
    digest = hashlib.sha256(f'{seed}|{case_id}|{provider}'.encode()).digest()
    return int.from_bytes(digest[:8], 'big') / 2 ** 64 < rate


def _round_half_up(x):
    return int(math.floor(x + 0.5))


# --------------------------------------------------------------------------- stores
class MemoryStore:
    """Scores in a dict. For tests and dry runs only; never cite as HydraDB evidence."""
    backend = 'memory'

    def __init__(self):
        self.scores = {}

    def reset(self):
        self.scores = {p: NEUTRAL_PRIOR for p in PROVIDERS}

    def ranking(self):
        return sorted(PROVIDERS, key=lambda p: (-self.scores[p], PROVIDERS.index(p)))

    def update(self, provider, ok, alpha):
        self.scores[provider] = _ewma(self.scores[provider], ok, alpha)

    def restore(self):
        pass

    def close(self):
        pass


class HydraStore:
    """Scores live on ToolVersion.reward in HydraDB, using the same anchored query
    shapes the rest of the app already runs. The first-choice provider comes from a
    real Task->Skill->Tool traversal (`RealHydra.resolve`)."""
    backend = 'hydradb'

    def __init__(self, db=None):
        from .real_mcp import RealHydra, stable_id
        self._stable_id = stable_id
        self.db = db or RealHydra()
        self.keys = {p: f'{p}::{CAPABILITY}' for p in PROVIDERS}
        self.original = {}
        for provider, key in self.keys.items():           # remember state so we can restore it
            row = self._read(provider)
            if row is None:
                raise ValueError(f'{key} is not seeded in HydraDB; discover MCP tools and seed first')
            self.original[provider] = row

    def _tid(self, provider):
        return self._stable_id('tool', self.keys[provider])

    def _read(self, provider):
        rows = self.db.run('MATCH (t:Tool {id: $tid})-[:HAS_VERSION]->(v:ToolVersion) RETURN v.reward AS reward',
                           tid=self._tid(provider))
        return None if not rows else int(rows[0].get('reward') or 0)

    def _write(self, provider, value):
        self.db.run('MATCH (t:Tool {id: $tid})-[:HAS_VERSION]->(v:ToolVersion) SET v.reward = $reward',
                    tid=self._tid(provider), reward=max(0, min(100, int(value))))

    def reset(self):
        for provider in PROVIDERS:
            self._write(provider, NEUTRAL_PRIOR)

    def ranking(self):
        route = self.db.resolve(TASK_KEY)                  # real graph traversal
        first = next((t['server'] for t in route['tools'] if t['name'] == CAPABILITY), None)
        scores = {p: self._read(p) for p in PROVIDERS}
        by_score = sorted(PROVIDERS, key=lambda p: (-scores[p], PROVIDERS.index(p)))
        if first in PROVIDERS:
            return [first] + [p for p in by_score if p != first]
        return by_score

    def update(self, provider, ok, alpha):
        self._write(provider, _ewma(self._read(provider), ok, alpha))

    def restore(self):
        for provider, value in self.original.items():
            self._write(provider, value)

    def close(self):
        self.db.close()


def _ewma(old, ok, alpha):
    """Exponentially weighted success score on a 0-100 scale."""
    target = 100 if ok else 0
    return max(0, min(100, _round_half_up(old + alpha * (target - old))))


# --------------------------------------------------------------------------- routers
class StaticRouter:
    def __init__(self, order):
        self.order = list(order)

    def plan(self, index):
        return list(self.order)

    def observe(self, index, provider, ok):
        pass


class LearnedRouter:
    def __init__(self, store, alpha=0.2, probe_every=10):
        self.store, self.alpha, self.probe_every = store, alpha, probe_every
        self.last_tried = {}
        self.probes = 0

    def plan(self, index):
        order = self.store.ranking()
        if self.probe_every and index > 0 and (index + 1) % self.probe_every == 0:
            stale = min(order, key=lambda p: (self.last_tried.get(p, -1), order.index(p)))
            if stale != order[0]:
                order = [stale] + [p for p in order if p != stale]
                self.probes += 1
        return order

    def observe(self, index, provider, ok):
        self.last_tried[provider] = index
        self.store.update(provider, ok, self.alpha)


# --------------------------------------------------------------------------- experiment
def run_stream(router, case_ids, seed, phases=PHASES):
    rows = []
    for index, case_id in enumerate(case_ids):
        rates = phase_at(index, phases)['rates']
        order = router.plan(index)               # chosen BEFORE the outcome is known
        failed, resolved = 0, False
        for provider in order[:MAX_ATTEMPTS]:
            ok = not fails(seed, case_id, provider, rates[provider])
            router.observe(index, provider, ok)  # learning happens AFTER the outcome
            if ok:
                resolved = True
                break
            failed += 1
        rows.append({'index': index, 'first_try_success': failed == 0, 'failed_attempts': failed,
                     'resolved': resolved, 'first_provider': order[0]})
    return rows


def _spread(values):
    return {'mean': round(statistics.mean(values), 4), 'min': round(min(values), 4), 'max': round(max(values), 4)}


def _windows(rows, size=WINDOW):
    return [rows[i:i + size] for i in range(0, len(rows), size)]


def aggregate(per_seed, phases=PHASES):
    """per_seed[system] = list of per-seed row lists. Returns window summaries + totals."""
    summary, totals = [], {}
    for system, seeds in per_seed.items():
        n_windows = len(_windows(seeds[0]))
        for w in range(n_windows):
            chunks = [_windows(rows)[w] for rows in seeds]
            first_index = chunks[0][0]['index']
            summary.append({
                'system': system, 'window': w + 1,
                'cases': f'{first_index + 1}-{first_index + len(chunks[0])}',
                'phase': phase_at(first_index, phases)['name'],
                'first_try_success': _spread([statistics.mean(r['first_try_success'] for r in c) for c in chunks]),
                'failed_attempts_per_case': _spread([statistics.mean(r['failed_attempts'] for r in c) for c in chunks]),
            })
        totals[system] = {
            'failed_attempts_total': _spread([sum(r['failed_attempts'] for r in rows) for rows in seeds]),
            'first_try_success_overall': _spread([statistics.mean(r['first_try_success'] for r in rows) for rows in seeds]),
            'unresolved_cases': _spread([sum(not r['resolved'] for r in rows) for rows in seeds]),
        }
    return summary, totals


def headline(totals):
    learned = totals['graphshield_learned']['failed_attempts_total']['mean']
    out = {}
    for base in ('static_primary_first', 'static_tuned_at_launch'):
        b = totals[base]['failed_attempts_total']['mean']
        out[f'failed_attempts_reduction_vs_{base}_pct'] = round(100 * (b - learned) / b, 1) if b else None
    return out


def _reference(phases=PHASES):
    """Analytic first-try failure rate of an all-knowing router, per phase (context line, not a system)."""
    return [{'phase': p['name'], 'start_case': p['start'] + 1, 'best_provider': min(p['rates'], key=p['rates'].get),
             'best_first_try_failure_rate': min(p['rates'].values()), 'rates': p['rates']} for p in phases]


def default_case_ids():
    path = ROOT / 'data' / 'refund_desk_cases.json'
    if path.exists():
        ids = [c['case_id'] for c in json.loads(path.read_text(encoding='utf-8'))['cases']]
        if len(ids) >= 150:
            return ids[:150], 'data/refund_desk_cases.json (historical Olist order-linked cases)'
    return [f'stream_case_{i:03d}' for i in range(150)], 'generated case ids (Olist cases file not found)'


def run(backend='hydradb', seeds=(7, 17, 29), case_ids=None, alpha=0.2, probe_every=10, store_factory=None,
        scenario='drift'):
    if len(seeds) < 3:
        raise ValueError('Use at least 3 seeds')
    if scenario not in SCENARIOS:
        raise ValueError('scenario must be drift or stationary')
    phases = SCENARIOS[scenario]
    source = 'caller supplied'
    if case_ids is None:
        case_ids, source = default_case_ids()
    store = store_factory() if store_factory else (HydraStore() if backend == 'hydradb' else MemoryStore())
    started = time.perf_counter()
    per_seed = {s: [] for s in SYSTEMS}
    probes = []
    try:
        for seed in seeds:
            store.reset()
            learned = LearnedRouter(store, alpha=alpha, probe_every=probe_every)
            routers = {'static_primary_first': StaticRouter(PROVIDERS),
                       'static_tuned_at_launch': StaticRouter(['orders_replica', 'orders_primary', 'orders_cache']),
                       'graphshield_learned': learned}
            for system, router in routers.items():
                per_seed[system].append(run_stream(router, case_ids, seed, phases))
            probes.append(learned.probes)
    finally:
        try:
            store.restore()
        finally:
            store.close()
    summary, totals = aggregate(per_seed, phases)
    return {
        'experiment': 'Online provider learning under drifting simulated faults (prequential evaluation)',
        'scenario': scenario,
        'backend': store.backend,
        'citable_as_hydradb_evidence': store.backend == 'hydradb',
        'cases_per_stream': len(case_ids), 'case_source': source, 'window_size': WINDOW,
        'seeds': list(seeds), 'retry_budget_per_case': MAX_ATTEMPTS,
        'learner': {'score': 'EWMA success score 0-100 stored in HydraDB ToolVersion.reward',
                    'alpha': alpha, 'probe_every_n_cases': probe_every, 'probes_per_seed': probes,
                    'initial_score': NEUTRAL_PRIOR},
        'phases': phases, 'reference_best_router': _reference(phases),
        'systems': SYSTEMS, 'summary': summary, 'totals': totals, 'headline': headline(totals),
        'duration_seconds': round(time.perf_counter() - started, 2),
        'limitations': [
            'Provider failure rates are SIMULATED assumptions declared in PHASES, not production outages.',
            'Phase boundaries and rates were chosen by the author; results show adaptation under drift, not a universal gain.',
            'Evaluation is prequential (route chosen before the outcome, score updated after).',
            'Probe attempts that fail are counted; exploration cost is included.',
            'Only provider selection for one capability (resolve_order) is learned here.',
            'No LLM, token or real tool-success claim is made by this experiment.',
            'Original HydraDB reward values are restored after the run.',
        ],
    }


def save(result):
    path = OUTPUT if result['citable_as_hydradb_evidence'] else OUTPUT_DRYRUN
    if result['scenario'] != 'drift':
        path = path.with_name(path.stem + '_' + result['scenario'] + path.suffix)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2), encoding='utf-8')
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--backend', choices=['hydradb', 'memory'], default='hydradb')
    parser.add_argument('--seeds', type=int, nargs='+', default=[7, 17, 29])
    parser.add_argument('--scenario', choices=list(SCENARIOS), default='drift')
    args = parser.parse_args()
    result = run(backend=args.backend, seeds=tuple(args.seeds), scenario=args.scenario)
    path = save(result)
    print('Saved', path, '| backend:', result['backend'], '| scenario:', result['scenario'])
    for system, t in result['totals'].items():
        print(f"{system:26s} failed attempts: {t['failed_attempts_total']['mean']:6.1f}  "
              f"first-try success: {100 * t['first_try_success_overall']['mean']:5.1f}%")
    print(result['headline'])


if __name__ == '__main__':
    main()
