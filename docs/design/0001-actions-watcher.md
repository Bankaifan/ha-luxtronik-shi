# 0001 Actions watcher (Refs #137)

Status: proposal. Facts I could not measure are marked **open**. Note: `tools/failure_watch.py` and
`tools/trusted_issues.py` cite "design 0008"; that file is not in the repo, so the code is the source here.

## 1. Goal
When a workflow run fails, times out, fails to start, is cancelled unexpectedly or does not do what was expected
(#135, #136), the owner must not have to notice it. Within minutes:
1. the cause class is analysed by a script (no model),
2. exactly one trusted, signed issue exists for it, with a slip an agent can start without the orchestrator,
3. stuck or failed items start again, even if the orchestrator, `status` or the watcher itself is broken (self-healing),
4. nothing loops, floods or duplicates, and Limits 1-5 of AGENTS.md hold.

## 2. Current state
- `tools/failure_watch.py`: signed issue `Failing workflow: <wf> / <job> / <step>`, dedup by title, flood cap
  (`MAX_NEW=5`), `Reopened:` counter, `needs-human` at 3, auto-close when green. **Gaps:** `KEPT` has no `cancelled`
  (the #136 run is invisible); it runs only inside `status.yml`; `SELF = status.yml` is excluded, so nobody watches `status`.
- `.github/workflows/status.yml`: triggers = cron every 30 min + `workflow_run` of agent-dev/agent-fix/agent-review only.
  A failed `validate`, `orchestrator`, `scout`, `release` run waits up to 30-60 min. Concurrency group `status`, no cancel.
- `tools/status.py`: orphan issues/PRs (retrigger once, then needs-human), conflicts, review:3, red-main rebase.
  `tools/stalled_dev.py`: `agent:dev` without run/PR for 60 min -> label set again once (`stalled:1`), then needs-human.
- `tools/liveness.py`: `Overdue scheduled run: <label>` for 5 scheduled workflows, plus `Nightly heavy tests failed`.
  `status_run_stale` only feeds the weekly summary. `agent_guard.py`: `Denied command in ...`.
- `tools/trusted_issues.py`: `GUARD_TITLES` + HMAC (`tools/guard_mark.py`, `GUARD_KEY`) make a guard issue trusted.
- `orchestrator.yml`: job concurrency group `orchestrator`, `cancel-in-progress: false`. A pending run is replaced by a
  newer pending one; GitHub then ends the replaced run `cancelled` ("Canceling since a higher priority waiting
  request..."). PR #139 removes one source (status issue edits); the class of failure stays.
- Nothing restarts the orchestrator. If it is dead, a trusted issue without `agent:dev` waits for the 24 h schedule.

## 3. Options
| | A: extend `status.yml` triggers | B: new `watch.yml`, shares `failure_watch.py` | C: model analyses logs |
|---|---|---|---|
| Latency | seconds (all workflows) | seconds | seconds + model start |
| Single point of failure | yes: `status` broken = blind, and it cannot watch itself | no: two scripts watch each other | worse (quota, prompt injection from logs) |
| Cost | status run (~10 min budget, many steps) per event | one tiny job per bad run | quota, scarce (AGENTS.md) |
| Trust | unchanged | unchanged | log text in issues: not allowed (signed bodies are fixed text) |

## 4. Chosen approach: B, plus the sweeper in `status`
### 4.1 Triggers (`.github/workflows/watch.yml`, no model)
- `workflow_run: types [completed]` for every workflow except `watch`. Job `if`: conclusion in `failure, timed_out,
  startup_failure, cancelled`. Other conclusions create a skipped run, no job, no minutes. Same zizmor rationale as
  `status.yml`: default-branch checkout only, no PR code, fork runs are dropped by `keep()`.
  The list is explicit (**open:** whether `workflows: ["*"]` is accepted); a test requires that it covers every file in
  `.github/workflows/` except `watch.yml`, so a new workflow cannot be forgotten.
- `schedule` every 30 min (offset from `status`) and `workflow_dispatch`: the sweeper for events GitHub did not deliver.
- Concurrency group `failure-watch` (shared with the watch step of `status`), `cancel-in-progress: false`. A replaced
  pending run is harmless here: every run scans from the anchor (`Failure watch since:`), it is idempotent, so the
  #136 mechanism cannot lose work. This is the reason the watcher is not per-event.
- The app token is created in the job (`permission-issues: write`, `permission-actions: write`; no contents, no PRs).

### 4.2 Classification (script, `tools/actions_watch.py`, names from workflow files only, sanitised by `clean`)
| Run outcome | Class | Action |
|---|---|---|
| `failure`, `timed_out` | `Failing workflow: wf / job / step` (existing) | issue |
| `startup_failure` | same, step `-` | rerun once, then issue |
| `cancelled`, job has no steps (never started: displaced by concurrency, the #136 shape; **open**: verify on a real API response) | `Failing workflow: wf / job / cancelled` | rerun once, then issue |
| `cancelled` with started steps | expected only for `agent-review.yml` (`cancel-in-progress: true`) and `validate.yml` with a newer run for the same head branch; a table `EXPECTED_CANCEL` in the script, everything else is unexpected | issue |
| "Skipped unexpectedly" | no run-level test: label events make most runs `skipped` by design. Instead *expected-vs-actual* (4.4) | see 4.4 |
`rerun once` = `gh run rerun` only while `run_attempt == 1`; no state, no second rerun. A rerun that fails again is
a normal failure and reaches the existing path. The bodies stay fixed script text; the conclusion, run URL and names are
the only run data in them (design rule of `failure_watch.py`).

### 4.3 The slip in the issue (so the orchestrator, or the fallback, can start at once)
Title and priority as today (`prio:1` for merge gates and recurrences, else `prio:2`), signed with `GUARD_KEY`. Body,
fixed text plus the names:
```
The workflow <wf> ended <conclusion> in job <job>, step <step>.   Last run: <url>   Failures: n
Slip: read the failure with `gh run view <id> --log-failed`, fix the cause in <workflow file> or the tool it calls,
add a test that fails on today's code, grep the repo for the same pattern. Done when: a run of <wf> is green.
Refs: none. Model: sonnet.
```
`model:sonnet` is set as a label by the app. No log text, no model text, so the signature stays honest.

### 4.4 Self-healing, independent of the orchestrator
1. **Rerun once** (4.2) for infrastructure-shaped endings.
2. **Fallback start.** Per tick, for each open signed watch issue without `agent:dev`, `needs-human` or a PR that closes
   it: if the orchestrator is *unhealthy* (its newest run in the last 2 h is `cancelled`/`failure`, or an approved or
   guard issue is older than 15 min and no orchestrator run started its model step since) **and** fewer than
   `MAX_DEV` (repo variable, default 2) issues carry `agent:dev`, the watcher sets `agent:dev` itself. The cap stays
   with the watcher in that case; with a healthy orchestrator it does nothing and the orchestrator decides.
   The signed body is the slip (4.3), so `agent-dev.yml` can run it. **Open:** confirm in implementation that agent-dev
   needs no trust beyond the label (no check found in `agent-dev.yml`); a test pins it.
3. **Restart of failed work.** A failed or cancelled `agent-dev`/`agent-fix` run for an issue with no open PR: re-add
   `agent:dev` once (`stalled:1`, the mechanism of `stalled_dev.py`, reused, not copied). Second time: `needs-human`,
   `OWNER` assigned, the German yes/no note with the marker `restart-issue` / `close-issue` (existing action ids).
4. **Unstarted run** (the "skipped for a reason" case): an issue with `approved`/`auto-ok` set by the owner (the
   trigger of #136) and no orchestrator run whose gate or model step ran after the label time + 15 min -> the watcher
   dispatches `orchestrator.yml` once (`workflow_dispatch`, `actions: write`). The dispatch is recorded as a field
   `Kicked: n` in a signed issue `Unstarted run: orchestrator` (new `GUARD_TITLES` entry); `Kicked: 2` -> `needs-human`.
5. **Mutual watch.** `watch.yml` is added to `liveness.SCHEDULED` (60 min) so `status` flags a dead watcher with the
   existing `Overdue scheduled run:` issue; `status` is already listed. `failure_watch.SELF` becomes a parameter: the
   watch run excludes itself, the status run excludes itself, each watches the other.

### 4.5 Loop protection
- Never triggered by its own workflow (`workflows` list, test) and by no issue event (it has no `issues` trigger).
- Issues are created with the app token; their events feed the orchestrator, not the watcher. A failing orchestrator
  run caused by such an issue has the same signature, so it only bumps `Failures:`.
- Per-signature `Reopened: 3` -> `needs-human` (existing); `Kicked: 2` and `stalled:1` bound restarts; at most 1 rerun.
- Flood cap: `MAX_NEW=5` per tick (existing) and at most 10 open watch issues; beyond that one signed
  `Failing workflow: many` issue and `needs-human`.
- Fix PRs failing on `agent/*` stay with agent-fix (`AGENT_OWNED`, existing).

### 4.6 De-duplication with what exists
One title family and one parser: `failure_watch.py` is extended, not copied. `Overdue scheduled run`, `Nightly heavy
tests failed`, `Denied command in`, the `status.py` orphan/stall steps and the weekly failure classes keep their jobs.
The watcher only adds the cases they cannot see (4.2 `cancelled`, 4.4). An open issue of any family for the same
workflow suppresses a second one: the title is the key, and the new title prefix is checked against the open list first.

### 4.7 Trust and permissions
Script steps only; `GUARD_KEY` never reaches a model step (the existing `tests/test_guard_mark.py` scan is extended to
`watch.yml`). Permissions: workflow `contents: read`; app token issues + actions write. No secrets in issues or logs
(Limit 1); nothing irreversible (Limit 2); no push, no tags (Limit 3); no access to the heat pump (Limit 4). The new
workflow, `GUARD_TITLES` (`tools/trusted_issues.py`, CODEOWNERS: Daniel) and the `status.yml` change go through the
security reviewer (Limit 5); the `trusted_issues.py` PR needs Daniel as code owner, that is the PR approval, not a design decision.

### 4.8 Failure modes
| Failure | Effect | Cover |
|---|---|---|
| `GUARD_KEY` or app key missing | nothing signed, nothing trusted | watch run red (job step fails loudly), `Overdue` via `status` |
| `workflow_run` not delivered | no instant issue | sweeper tick <= 30 min |
| `status` and `watch` both dead | blind | the existing weekly summary (`status_run_stale`); GitHub e-mail to the owner is the last line |
| API rate limit / 5xx | tick ends early | anchor not advanced, next tick retries (existing) |
| Orchestrator healthy but slow | fallback waits 15 min | no double start: label/`MAX_DEV` check first |
| Watcher bug floods | cap 5/tick, 10 open | `FAILURE_WATCH=off` repo variable (existing) disables both paths |

## 5. Migration and compatibility
No user-visible change; the integration is untouched. No release (CI only). Open issues of the family keep their title.
`FAILURE_WATCH=off` stays the kill switch. `status.yml` keeps its failure-watch step; it becomes the second watcher.

## 6. Test and verification plan
Each test must fail on today's code:
1. `keep()` on a fixture of the #136 run (`orchestrator.yml`, `cancelled`, job without steps): today `False`, expected an issue.
2. A run list where `watch.yml` itself fails: no issue (loop test); a failed `status.yml` run: issue (today excluded).
3. Trigger test: `watch.yml`'s `workflows` equals all other workflow names (today no such file).
4. Rerun only at `run_attempt == 1`; fallback sets `agent:dev` only when orchestrator unhealthy and `MAX_DEV` free;
   `Kicked: 2` -> `needs-human` with the marker line; unsigned or foreign-author issues are never touched.
5. Body test: no field of a generated body comes from log text (injection string in a job name is sanitised).
6. Before rollout: `workflow_dispatch` on a branch-free dry run (`DRY_RUN=1` prints actions, writes nothing), then one
   real failing test workflow on a throwaway branch; both measured and pasted into the PR.

## 7. Rollback
Delete or disable `watch.yml` (one revert PR) or set `FAILURE_WATCH=off`. The signed issues stay valid, nothing migrates.

## 8. Split into implementation issues (each <= ~400 lines, in this order)
1. `Failure watch: cancelled and startup runs, parametrised SELF` - `tools/failure_watch.py`, `tests/test_failure_watch.py`,
   `tools/status.py` (SELF argument). No new trigger yet.
2. `Actions watcher workflow` - `.github/workflows/watch.yml`, `tools/actions_watch.py` (single-run entry, rerun once,
   DRY_RUN), `tests/test_actions_watch.py`, `tests/test_guard_mark.py` scan. Security reviewer.
3. `Watcher self-healing` - `tools/actions_watch.py` (fallback start, restart of failed agent work, Kicked counter, German
   note), `tests/test_actions_watch.py`. Needs 1 and 2.
4. `Trust the Unstarted run family` - `tools/trusted_issues.py` (`GUARD_TITLES`), `tests/test_trusted_issues.py`. Daniel as code owner.
5. `Mutual watch and unstarted-run check` - `tools/liveness.py` (`SCHEDULED`), `tools/status.py`, `.github/workflows/status.yml`
   if the schedule offset needs it, tests. Needs 2 and 4.

## 9. Owner decisions
none
