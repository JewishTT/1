# UtilityScorer Contract (Scheduler + Feedback)

Drives optimization of Useful Information Yield / Resource Cost — not req/sec (Spec FR-027, R-3, §14/§15).

## Score function (baseline heuristic)

```text
Utility(task) =
  ( ExpectedInformationGain
    × Relevance
    × Novelty
    × FreshnessValue
    × DiscoveryPotential
    × SourceQuality )
  /
  ( NetworkCost + ComputeCost + DuplicateRisk )
```

## Interface

```text
score(task, context) -> UtilityScore
    // utility, priority, expected_novelty, expected_cost
    // context = investigation policy/budget/freshness + source/host state

feature_vector(host_key) -> AdaptiveState
    // EWMA latency, EWMA error rate, EWMA payload, success rate,
    // retry rate, change rate, concurrency, cooldown, last_request,
    // discovery yield

adjust(action, outcome) -> void
    // online update of AdaptiveState per source/host after each outcome
```

## Requirements

- The scorer is replaceable: a learned model can implement the same contract (feature store + ML service) without scheduler changes (FR-027, R-3).
- Scheduler adapts per source/host: concurrency, delay, priority, retry, recrawl interval, worker class.
- Admission scores are separate (I-7): admission decision vectors NEVER equal priority/utility.
- Backpressure: scorer surfaces lag signals from downstream (queue depth, projection lag) and the scheduler reduces acquisition rate before Kafka backlog grows (FR-028, R-11).
- Stopping policy: when marginal information gain drops, priority decays → SLEEP → STOP per branch; discovery expansion gates on feedback from accepted knowledge (§58, R-11).