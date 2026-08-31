# Contribution metrics

All three metrics derive from a single **binary contribution matrix** `M`, where
`M[member][workstream] = 1` iff the member has at least one activity item
attributed to that workstream during the reporting window, and `0` otherwise.

There are six canonical workstreams (see `bin/workstream_map.py`): **SNO, TNA,
TNF, LVMS, USHIFT, TOPO**. Breadth is always reported "of 6".

An activity item is attributed to a workstream by mapping its Jira component(s)
through `workstream_map.component_to_workstream`. Items that map to nothing (an
unknown component, or the `Planning` cutline component) are **unattributed**:
they are counted and reported separately, but never placed in the matrix.

## Breadth (IC, per member)

The number of distinct workstreams a member touched:

```text
breadth(m) = sum over w of M[m][w]
```

Reported as "N of 6".

## Flexibility (team, per workstream + scalar)

Per workstream, the number of distinct contributors:

```text
flexibility(w) = sum over m of M[m][w]
```

The vector covers **all six** workstreams, including any with zero contributors.

The team scalar is the mean over all six workstreams:

```text
team_flexibility = total_ones / 6
```

where `total_ones` is the number of 1s in the matrix (equivalently, the sum of
every member's breadth). A high value means the team is broadly cross-trained;
a low value, or zeros in the vector, flags workstreams with thin coverage.

## Opportunity (team, per member + scalar)

Per member, the count of workstreams touched — identical to breadth:

```text
opportunity(m) = breadth(m)
```

The team scalar is the mean over **active** members (those with at least one
contribution), reported alongside the active/total roster count:

```text
team_opportunity = total_ones / active_count      (0.0 when active_count == 0)
```

Averaging over active members answers "when someone contributes, across how many
workstreams do they spread?" without inactive members deflating the number.

## Edge-case contract

- **Empty roster / no workstreams** → both team scalars are `0.0` (no division by
  zero).
- **All-zero matrix** → `active_count == 0`, `team_opportunity == 0.0`, and every
  `flexibility(w) == 0`.
- **Single active member** → `team_opportunity == breadth(that member)`.
- **Zero-contributor workstream** → still present in the flexibility vector as `0`.

These are enforced by `bin/tests/test_metrics.py`.
