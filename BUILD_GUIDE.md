# Phase 1 Possession System — Build Guide and Implementation Prompt

## 1. Purpose and status

This document is a build specification for a future, reproducible possession-labeling system for
More than a Hack 2027, Phase 1. It consolidates the organizer's repository materials and the
additional organizer clarification supplied with this project. **No model or submission is
implemented by this document.**

The clarification image explicitly says that its rules take precedence over information previously
received, including documentation and individual answers. Follow it wherever it is stricter than
the repository. If a proposed method is near a boundary, ask the organizers before relying on it.

The intended end product is a public, inspectable repository that takes the permitted match inputs
and deterministically generates one CSV row per tactical-video frame. The labels must be produced
by an algorithm—not by a person.

## 2. Global truths (non-negotiable project invariants)

In this guide, **global truths** means project-wide facts and constraints that every implementation
must preserve. They are not tunable model assumptions.

1. **The task is frame-level possession classification.** For each frame, label the home team, away
   team, dead ball, or abstention.
2. **The tactical recording is the submission timeline.** Row `i` means tactical video frame `i`.
   Do not index the submission to the broadcast video.
3. **The required output has exactly 199,319 rows**, in frame order from `0` through `199318`.
4. **The allowed label set is exactly `H`, `A`, `D`, `X`.** On graded frames the ground truth uses
   only `H`, `A`, and `D`; `X` is a system abstention, not a fourth ground-truth state.
5. **A possession is an interval.** It is a maximal run of one team's live-ball possession. A
   stoppage ends the possession; a team switch starts another.
6. **A dead ball is not a possession.** Do not guess which team "owns" a ball that is out of play.
7. **Possession changes require control.** A touch, deflection, or aerial-duel win alone is not a
   change. While a live ball is loose or contested, retain the previous possessor until evidence of
   control or a stoppage/restart supports another state.
8. **The ranking metric is `spellF1`, not accuracy.** `macroF1` is reported and is the first
   tie-breaker. The two can reward very different temporal behavior.
9. **The provided match assets are restricted.** Do not redistribute them, commit them, or upload
   them or extracts to hosted/cloud AI services. Check dataset licenses before using external data.
10. **The output must be reproducible.** A clean run of the public repository, with the authorized
    data available locally, must regenerate the same submission file.
11. **No manual labels or manual output correction.** The final CSV must come from the system.
12. **Organizer clarification overrides conflicting prior guidance.** In particular, do not check
    predictions against the video and do not train, fit, calibrate, or tune on the provided video
    or ground-truth possession data.

## 3. Organizer clarification: permitted and prohibited work

### Prohibited

- Checking a prediction/output against the video.
- Hand labels, human-produced data, or any other data manually created on the provided match.
- Uploading provided data (including video, tracking, tags, or derived extracts) to AI services.
- Training, fitting, or calibrating the algorithm on ground-truth possession labels or the provided
  video.
- Tuning algorithm parameters on the ground-truth possession data or provided video.
- Hand-editing the generated submission, including frame-by-frame corrections.
- Using the private full-match ground truth or any possession data derived from it.

### Permitted, subject to the other rules

- Automatic checks using only the provided data, such as checking row counts, frame continuity,
  timestamp conversions, missing values, and output-file schema.
- Inspecting the provided data and video to understand the task's possession concepts. This is for
  understanding only: do not compare a generated prediction with the video or turn observations
  into frame labels, training data, fitted parameters, or calibration decisions.
- Using video, automatic tracking, Smart Tagging, homography, and other automatically generated
  data as **inference-time inputs**, provided the algorithm was not trained or tuned on the
  provided video or ground-truth possession data.
- Training or retraining on external data only. Any algorithm parameters that need tuning must be
  tuned on external data, never on this match's ground truth or video.
- Using datasets for which the team has the rights. Respect their licenses and disclose them.
- Providing files of intermediate steps, as long as those files are algorithmically generated,
  permitted, and do not expose restricted data.

The repository includes a public five-minute ground-truth file and an evaluation script. The main
organizer documents describe that window as a way to check pipeline correctness, not a leaderboard
or a model-selection set. Under the stricter clarification, do **not** use public possession labels
or scores to train, fit, calibrate, tune parameters, or choose between model variants. If it is
unclear whether a particular automated comparison is allowed, ask the organizers first. In all
cases, never validate predictions by watching the video.

## 4. Challenge and dataset facts

The match is FC Barcelona (`H`) vs Athletic Club (`A`), LaLiga EA Sports 2024–25, matchday 2.
There are 199,319 tactical frames at 25 fps (1920×1080). The match is also recorded by a broadcast
camera, but that recording has a separate timeline, cuts and replays, and no provided mapping to
tactical frames.

### Inputs

- **Tactical video:** reference timeline; 199,319 frames.
- **Tactical ATD (Automatic Tracking Data):** one record per frame, with player track slots and
  ball positions/speeds where detected. Coordinates are normalized to 0–1. Tracking is automatic,
  can have gaps and identity switches, and does not provide stable player identities. There are 46
  track slots for 22 players; slots are tracklets, not shirt numbers or people.
- **Tactical Smart Tagging:** 638 automatic phase/set-piece intervals. These are useful evidence,
  not ground truth or possession boundaries. They can contain false positives/negatives; 36
  instances have `Team = N/A`, including every throw-in. A tagged phase can cover part of, one, or
  multiple possessions.
- **Tactical homography:** one 3×3 pitch-to-image matrix per frame. Coordinates are normalized
  pitch coordinates, matching ATD. Check `valid` before using a matrix; `reprojection_error`
  indicates how much to trust a valid transform.
- **Optional broadcast video, ATD, and homography:** inputs only if the team can lawfully and
  reliably map their information to the tactical timeline. No synchronization map is supplied.
  The broadcast has 164,488 frames; using its row index directly will fail the submission contract.

The ball is missing on about 41% of graded frames. **Missing ball data does not mean the ball is
dead.** Treat missingness as uncertainty and use other evidence or temporal state.

### Alignment rules

Use the provided loaders/helpers where practical; they encode established file conventions.

| Asset | Frame conversion |
|---|---|
| Tactical submission | `frame = 0 … 199318` |
| Tactical ATD | `video_frame = frame_id - 1` (`frame_id` is 1-based) |
| Tactical Smart Tagging | `video_frame = round(seconds * 25)` |
| Tactical homography | `frame` is already zero-based |

Never apply a single guessed offset across the match. Do not mix broadcast indices with tactical
indices. Check record counts, continuity, bounds, and time conversions automatically.

### Graded and ungraded frame ranges

The published graded ranges are `11185–90651` and `110808–190197`, inclusive. Other frames are
ungraded and can be output as `X` if the system has no answer. The second half's graded range begins
before its kickoff: frames `110808–113741` are documented as dead ball (`D`). Do not assume every
graded frame begins at kickoff.

## 5. Label semantics and football decision policy

| Label | Meaning | Decision policy |
|---|---|---|
| `H` | Home (Barcelona) has controlled possession while the ball is in play | Use evidence that supports live play and home control. |
| `A` | Away (Athletic Club) has controlled possession while the ball is in play | Use evidence that supports live play and away control. |
| `D` | Ball is out of play / play is stopped | Infer a stoppage; do not encode the last-touch or restart team as possessor. |
| `X` | The system abstains / has no answer | Use for uncertainty, not as a substitute for detecting dead ball. Its scoring behavior is special. |

Operational principles:

- The referee's in-play state determines whether the label is a team or `D`.
- During a live loose-ball or contested phase, keep the previous team until control changes; do
  not invent a separate contested label.
- A controlled reception/recovery is the meaningful turnover event. A touch, deflection that does
  not intercept, or aerial duel without subsequent control is not enough.
- A restart establishes a possessor, but a set-piece interval is only evidence of a phase, not a
  license to label its entire duration `D` or assign its `Team` tag to every frame.
- `X` differs from `D`: `X` means the system declines to guess; `D` means it predicts that play is
  stopped.

The public five-minute ground truth is the reference for interpreting ambiguous football cases.
Do not use it to develop labels, train, fit, tune, calibrate, or select a system under the
organizer's additional clarification.

## 6. Recommended algorithm and processing pipeline

This is a technically grounded starting design, not a claim that the model has already been built.
The team may use any inspectable method permitted by the rules. A deterministic tracking-first
pipeline is a practical baseline; externally trained components are optional.

### Stage 1 — Load and validate inputs

1. Resolve asset paths through `games.asset_paths()` and the `MTAH_DATA_DIR` environment variable;
   avoid duplicating filenames in code.
2. Load tactical ATD and optional Smart Tagging/homography with the starter helpers or a documented
   equivalent.
3. Assert expected tactical frame counts, frame ID continuity, unique/in-range indexes, and the
   alignment conversions above.
4. Preserve explicit missing-value masks. Never convert `NaN` or a missing ball observation to
   zero coordinates or to `D`.
5. Keep feature rows keyed to the zero-based tactical frame index throughout the pipeline.

### Stage 2 — Build frame-level evidence

Extract evidence without manually labeling the match. Useful candidate features include:

- Ball visibility, normalized position, speed, and short-window motion when observations are
  continuous. Do not bridge long gaps as if they were observed.
- Nearest player distance by team, using pitch dimensions to avoid distorting the geometry
  (`105.3 × 68.0 m` in `games.py`). Consider team-level nearest/aggregate evidence rather than
  trusting one noisy track slot.
- Player counts, spatial density around the ball, team shape, and relative movement as supporting
  signals; account for fragmented tracks and duplicate detections.
- Automatically generated Smart Tagging codes, interval bounds and tags as weak evidence. Map team
  names to `H`/`A` explicitly; handle `N/A`; account for spelling/case variations. Treat
  `SET PIECES` as restart context, not a possession annotation.
- Homography-derived image/pitch geometry when useful. Check validity and reprojection error.
  Homography is not needed to compare ATD positions to each other on the pitch.
- Video as an inference-time input only if the method is trained/tuned exclusively on permitted
  external data. Never use video to inspect or correct the algorithm's output.

The starter baseline illustrates a nearest-player method: assign the team of the nearest player to
the visible ball, then apply a centered majority vote. It ignores tags, homography, structured
possession, and has weak dead-ball inference; the ball-missing frames are not evidence of a
stoppage. Use it as a reproducible baseline, not a finished solution.

### Stage 3 — Infer temporal states and possession spells

The target states are `H`, `A`, and `D`; optionally emit `X` for uncertainty. Make the model
temporal rather than treating frames as unrelated classifications. Suitable methods include:

- A deterministic state machine with explicit evidence thresholds and persistence/hysteresis.
- A Hidden Markov Model (HMM), where emission scores represent frame evidence and transition
  probabilities encode state persistence.
- A semi-Markov model or duration-aware decoder, where states have explicit duration distributions.
- A sequence model trained only on external data, with inference-time inputs from this match.

For any such method:

1. Separate **live/dead-ball inference** from **which team controls a live ball**; do not let an
   absent ball automatically force `D`.
2. Penalize rapid `H ↔ A` flicker and require evidence of controlled possession before switching.
   The previous possessor is a useful prior during live loose-ball intervals.
3. Treat stoppages as possession boundaries. After a stoppage, use restart evidence to initialize
   the next live possessor, but do not assume the whole tag interval is dead or that tag team always
   identifies the next possessor.
4. Use duration constraints only when they are established from permitted external data or fixed
   a priori. Do not fit them to this fixture's public labels or video.
5. Make the `X` policy explicit. The official scorer forward-fills abstentions with the previous
   non-`X` label within each half (and back-fills at the head), so `X` across a real handover can
   extend the wrong possession. It can be less harmful inside a possession than a noisy guess.
6. Ensure halftime is a boundary: state carryover must not cross from the first half to the second.

### Stage 4 — Generate and freeze the submission

1. Produce exactly one label for every tactical frame; no missing rows, blank labels, or extra
   index column.
2. Write UTF-8 CSV with exact header `frame,label`, rows in ascending order, frame values
   `0…199318`, and labels from `H`, `A`, `D`, `X`.
3. Do not edit the generated CSV by hand. Fix the algorithm and regenerate instead.
4. Validate the exact final file with:

   ```bash
   python evaluation/validate_submission.py <team_name>.csv
   ```

5. Keep the generation command, pinned dependencies, and configuration in the public repository.
   Set random seeds and deterministic options; the same inputs and environment should give the same
   output.

## 7. Scoring and development discipline

### Metrics

- **`macroF1`:** unweighted mean of frame-level F1 for `H`, `A`, and `D`. `X` on a graded frame is
  charged as a miss.
- **`spellF1`:** ranking metric. A possession is a maximal `H` or `A` interval. Predicted and true
  spells are matched one-to-one using temporal intersection-over-union (IoU); F1 is averaged over
  IoU thresholds `0.3, 0.4, 0.5, 0.6, 0.7`.
- Before spell matching, `X` is filled with the last label within each half (back-filled at the
  beginning). Thus `X` does not mean "skip this interval" to `spellF1`.
- The baseline `baseline_smooth50` has full-match `spellF1 = 0.2433`; it is a useful published
  reference floor, not a promise about performance on the public window.

### Safe validation plan

- Always run automatic file/schema, row-count, index, range, dependency, and determinism checks.
- Use `evaluation/validate_submission.py` for output-contract validation; it does not need ground
  truth.
- The repository's `evaluation/run_evaluation.py` scores against public GT. Because the additional
  clarification forbids training/fitting/calibration/tuning on possession GT, do not use its score
  to optimize thresholds, select variants, or make model changes. Consult organizers if unsure
  whether a proposed use of the public score is permitted.
- Do not use the private ground truth or seek other corrected labels for this fixture.
- Do not visually compare predicted labels with the video. A manual video review must not become
  output checking, correction, annotation, training data, or parameter tuning.
- Analyze model behavior using permitted automatic diagnostics and, for performance development,
  separate external labeled data. Explain limitations rather than tuning on the prohibited source.

The public window has only 17 possessions and is not representative enough for reliable ranking or
model selection. The organizer documentation shows that tuning a simple smoothing window on it
chooses the wrong variant for the full match.

## 8. Code, privacy, reproducibility, and team requirements

- Public repository contents should include source, pinned dependencies, installation/run
  instructions, the command that regenerates the submission, and a technical explanation.
- Do not commit `data/`, raw videos, tracking exports, or other restricted match assets. Do not
  publish derived data that could reconstruct the match (for example frame-level tracking exports
  or clipped video). Confirm that `.gitignore` protects the data folder.
- Do not send the data to cloud or hosted LLMs/AI services. Keep inference local unless the
  organizers explicitly clarify an allowed alternative.
- Any external model, API, dataset, or dependency must be accessible/inspectable by the organizers
  and explained. Do not rely on private in-house models or unavailable internal datasets. Verify
  license/terms for external assets.
- Reproduction should include environment setup, a single clear generation command, expected
  inputs/outputs, and deterministic behavior. The final CSV must be regenerable exactly, not merely
  approximately.
- Eligible teams have **3–5 members**. Teams under three are not eligible for the Innovation
  Challenge and Final Pitch.
- Submission is through the organizer's Google Form: team name, possession CSV, public repository
  URL, and short technical document. Name the CSV and document after the team (`<team_name>.csv`
  and `<team_name>.md` or `.pdf`); submit one response per team and verify the exact file before
  upload. Deadline stated in the repository: **November 17, 2026**.

## 9. Required technical documentation for the eventual system

When the algorithm is eventually implemented, its technical note should state:

- The method, architecture, algorithmic steps, and why they were chosen.
- Which provided assets and external data/models were used or deliberately omitted.
- How team control, dead ball, loose-ball continuity, turnovers, restarts, and abstention are
  represented.
- How the algorithm handles missing/noisy ball and player tracks, tag errors, and timeline
  alignment.
- What was trained or tuned, the source of training/validation data, and evidence that none of it
  was fitted to the provided video or possession ground truth.
- Known failure modes and limitations.
- Dependencies, environment, exact reproduction command, and output validation result.
- License/access notes for external models and datasets.

## 10. Glossary

| Term | Definition |
|---|---|
| **Global truths** | Invariants every implementation must obey, listed in Section 2; not learned model parameters. |
| **ATD** | Automatic Tracking Data: per-frame coordinates/speeds for track slots and the ball where detected. |
| **Track slot / tracklet** | A tracker output channel that may appear, disappear, or switch identity; it is not a stable player identity. |
| **Smart Tagging** | Automatically inferred tactical phase/set-piece intervals and tags; evidence, not ground truth or possession labels. |
| **Homography** | A 3×3 projective transform between normalized pitch coordinates and image pixels. |
| **Ground truth (GT)** | The reference possession/dead-ball labels used for scoring. Full-match GT is private; only the published five-minute file is present in the repository. |
| **Private GT** | Full-match labels withheld from participants and prohibited for use in development. |
| **Possession / spell** | A maximal contiguous run of one team (`H` or `A`) controlling a live ball. `D` ends a spell. |
| **Controlled possession** | Team control sufficient to establish/retain possession; not merely a touch, deflection, or aerial-duel contact. |
| **Dead ball** | Ball not in play due to a stoppage; label `D`, never a team possession. |
| **Abstention** | The model declines to predict; label `X`. It is not the same as `D`, and scorer filling affects `spellF1`. |
| **Temporal IoU** | Intersection length divided by union length for two time intervals; used to match possession spells. |
| **Emission** | Evidence/score that a frame belongs to a state in a temporal model. |
| **Transition / persistence** | State-change likelihood / preference for staying in a state across adjacent frames. |
| **HMM** | Hidden Markov Model: a state sequence model with per-frame emissions and transition probabilities. |
| **Semi-Markov model** | A sequence model that represents state durations explicitly. |
| **Hysteresis** | Different evidence requirements for switching into versus out of a state, reducing flicker. |
| **Training** | Learning model parameters from examples. For this challenge, use external data only. |
| **Fitting / calibration** | Estimating model or decision parameters from data, including thresholds/probabilities. Do not do this on the provided video or possession GT. |
| **Tuning / model selection** | Choosing parameters or a model based on measured results. Use external data only; do not optimize against this match's possession GT/video. |
| **Inference** | Applying a fixed algorithm/model to permitted inputs to generate labels. The match data may be an inference input. |
| **Deterministic reproducibility** | Re-running the same pipeline with the same inputs/environment yields the same output file. |

## 11. Reusable implementation prompt for a future coding model

> **Task:** Implement a reproducible Phase 1 football-possession labeling pipeline for the
> More than a Hack 2027 repository. First inspect the organizer files and starter code; treat
> `BUILD_GUIDE.md`, `RULES.md`, the attached organizer clarification summarized in this guide,
> `CHALLENGE.md`, `DATA.md`, `EVALUATION.md`, and `SUBMISSION.md` as requirements. The organizer
> clarification takes precedence over conflicting older documentation.
>
> **Do not implement or run training/tuning on the provided video or any ground-truth possession
> labels.** Do not upload match assets to hosted/cloud AI. Do not hand-label, visually check
> predictions against the video, hand-correct output, access private GT, or publish restricted
> data/derived exports. Train or tune only on permitted external data. Use the supplied match
> assets only as authorized algorithm inputs/inference inputs and for automatic data-integrity
> checks.
>
> Build a temporal `H`/`A`/`D` inference pipeline with an explicit optional `X` policy. Account for
> missing ball observations without treating them as dead ball; require evidence for controlled
> turnovers; preserve the previous possessor during uncertain live-ball intervals; use Smart
> Tagging as noisy phase/restart evidence, not as possession truth; and respect tactical-frame
> alignment. Consider a state machine, HMM, or duration-aware/semi-Markov decoder. All tuned
> parameters must come from external data or be fixed before inference on this match.
>
> Keep changes surgical and consistent with repository patterns. Add code, tests, and directly
> related documentation only when asked to implement the model. The pipeline must generate a
> deterministic UTF-8 CSV with exact header `frame,label`, exactly 199,319 ordered rows indexed
> `0…199318`, and labels only `H`, `A`, `D`, `X`. Include a clear reproduction command and run
> `python evaluation/validate_submission.py <file>` on the generated file. Do not use the public
> evaluation score to choose parameters or model variants; ask the organizers if its use is
> unclear. Never commit or publish match data.
>
> In your final report, identify the algorithm and features, external training/tuning sources,
> assumptions, limitations, deterministic reproduction steps, and validation outcome. Clearly
> disclose any requirement that cannot be met rather than silently bypassing it.

## 12. Organizer source documents

The current deterministic inference implementation and its processing record are in
[starter/possession_model.py](starter/possession_model.py) and [MODEL_PROCESS.md](MODEL_PROCESS.md).
It is not a trained LightGBM/XGBoost model because no permitted external labeled training set was
provided; it uses fixed, non-fitted temporal rules instead.

This guide is a practical synthesis, not a replacement for the authoritative rules and metric
implementation. Read these files for full context:

- [Challenge definition](CHALLENGE.md)
- [Rules and eligibility](RULES.md)
- [Asset formats and frame alignment](DATA.md)
- [Scoring definitions](EVALUATION.md)
- [Submission contract](SUBMISSION.md)
- [FAQ and edge cases](FAQ.md)
- [Starter baseline](starter/baseline.py)
- [ATD loader and alignment](starter/load_atd.py)
- [Deterministic inference model](starter/possession_model.py)
- [Model implementation process](MODEL_PROCESS.md)
- [Smart Tagging loader](starter/load_smart_tagging.py)
- [Homography loader](starter/load_homography.py)
- [Official validation script](evaluation/validate_submission.py)
- [Metric implementation](evaluation/possession_metrics.py)
