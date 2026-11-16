# Possession Model — Implementation Process

## What was built

The project now has a deterministic, tracking-first possession inference pipeline in
[`starter/possession_model.py`](./starter/possession_model.py). It reads the tactical ATD and
automatic Smart Tagging, creates one label for each tactical-video frame, and writes the required
`frame,label` CSV. It is an inference model made of fixed rules and temporal state; it is **not**
an XGBoost/LightGBM model and it has no trained weights.

This choice is deliberate. The organizer's additional clarification says training and parameter
tuning must use external data, not the provided match video or its possession ground truth. No
separate, legally usable external possession dataset was provided with this workspace. The local
Python interpreter also has neither LightGBM nor XGBoost installed. Training a boosted model on
the challenge's public labels, making pseudo-labels from the match and fitting to them, or choosing
parameters based on the match would violate the clarification. A fixed, interpretable system is
the honest runnable option until compliant external training data is available.

## Implemented pipeline

1. **Load the tactical inputs.** Asset locations come from `games.py` and its data-directory
   conventions. The process reads the ATD metadata, raw tracking records, and Smart Tagging XML. It
   does not open or decode either video.
2. **Check alignment while parsing.** Each ATD `frame_id` must equal the 1-based row number; each
   row must contain the same number of track slots as the metadata; and the total record count must
   equal the expected tactical-video frame count. A mismatch fails explicitly rather than silently
   shifting labels.
3. **Extract geometric evidence.** For frames with a detected ball, calculate each team's nearest
   tracked-player distance in metres. The pitch's length and width are applied separately because
   normalized x/y coordinates do not have the same physical scale. Retain the ball coordinates,
   ball speed, and number of tracked players for each frame. Missing ball coordinates remain
   missing; they are not converted to zero or treated as a dead ball.
4. **Use Smart Tagging narrowly.** Convert only `SET PIECES` intervals to a frame mask. Do not
   copy tag-team values into possession labels and do not treat an entire tactical phase as a
   possession. A stationary, tracked ball inside a set-piece interval is an explicit dead-ball
   cue.
5. **Infer control with a temporal state machine.** A team can become the owner when its nearest
   player is within 2.0 m of the ball and is at least 0.5 m closer than the opponent's nearest
   player. Both teams must have valid tracked distances; if one side is missing, the model does not
   assume the other side is closer. A new owner is accepted after 10 qualifying observations; up
   to two ambiguous/missing candidate frames may occur during that confirmation. This rejects
   isolated opponent touches and retains the current owner through short ball-tracking gaps.
6. **Infer dead ball conservatively.** Emit `D` for an out-of-bounds observation only when it
   persists for at least 3 consecutive frames, or for a ball moving no faster than 0.2 m/s inside a
   `SET PIECES` interval only when that evidence persists for at least 5 consecutive frames. Once
   confirmed, label the complete evidence run `D`. These fixed temporal rules avoid reacting to a
   one-frame coordinate spike or brief slow-down; they will still miss stoppages without those
   signals and may delay recognition of short stoppages.
7. **Abstain when there is no supported state.** Emit `X` before a team has enough control evidence
   or during sustained tracking disappearance. If the ball alone is missing while players remain
   tracked and an owner is established, preserve that owner rather than falsely calling `D`.
   A dead-ball cue resets possession; a team must establish control again after the restart.
8. **Write a deterministic submission.** The writer rejects wrong output lengths and invalid
   labels, then writes a UTF-8 CSV with exact header `frame,label`, ascending frame indices, and no
   extra index column.

## Why not use `XGBoost` or `LightGBM` now?

Gradient-boosted trees require labeled examples or another legitimate external training signal.
This project has no compliant external training set. The public five-minute possession labels are
challenge ground truth, so they were not used for training, fitting, calibration, parameter
selection, or model comparison. The public evaluator was run once as a report-only check: spellF1
0.4588 and macroF1 0.5679 on 17 public possessions. That score did not guide code changes. Later
logic changes are based on general robustness principles and synthetic tests, not that score. No
predictions were visually checked against the provided video by this implementation.

The architecture can be extended with a boosted model once the team supplies a legally usable
external dataset and confirms that its labels/features match the task. That model must be trained
and tuned only on that external data, with its source and license documented. This implementation
does not silently substitute the challenge labels or tracking-derived pseudo-labels.

## Tests and verification

`tests/test_possession_model.py` uses synthetic feature sequences only. It checks:

- delayed owner initialization until evidence persists;
- rejection of a single-frame apparent turnover after an owner has been established;
- confirmed team change after sustained evidence;
- abstention when one team's nearest-player tracking evidence is missing;
- confirmation that a Smart Tagging interval alone does not force `D`;
- rejection of one-frame out-of-bounds spikes;
- dead-ball output and owner reset on persistent out-of-bounds tracking;
- rejection of a brief slow-ball signal in a set-piece interval;
- dead-ball output for a persistent stationary-ball cue in a set-piece interval;
- owner persistence when the ball is temporarily missing; and
- abstention/reset behavior when player tracking disappears.

Run the unit tests:

```bash
python -m unittest discover -s tests -v
```

Generate and format-check a submission after the authorized match assets are installed locally:

```bash
python starter/possession_model.py --out evaluation/results/<team_name>.csv
python evaluation/validate_submission.py evaluation/results/<team_name>.csv
```

The format validator checks the required row count, frame ordering, header, and label alphabet. It
does **not** establish prediction quality. Do not use the public possession labels or video to tune
the algorithm. The challenge CSV under `evaluation/results/` is gitignored and must be submitted
through the organizer's submission form, not committed to the public repository.

On the current workspace, the model generated
`evaluation/results/possession_model.csv` with 199,319 rows: 77,801 `H`, 74,343 `A`, 4,635 `D`,
and 42,540 `X`. The official format validator passed. Two full regenerations produced the same
SHA-256 (`ef998b4591ae003165790262aefc90fb719e719b993f0dbcddaeab5b7bf0de86`). These are format and
reproducibility checks only, not a measure of label accuracy or challenge score.

## Limitations

- The rules are not trained or calibrated; the distance, persistence, and dead-ball conditions are
  transparent engineering heuristics, not learned probabilities.
- ATD tracklets can fragment, switch identity, or be absent. Team-level nearest distances reduce
  dependence on a single track but cannot remove tracking errors.
- A set-piece tag is noisy phase evidence. The stationary-ball cue can label a slow live restart as
  dead, while untagged dead balls and stoppages with missing ball tracking may be missed.
- Out-of-bounds coordinates are only one dead-ball signal; the model does not reconstruct referee
  decisions from video.
- `X` is filled by the official spell metric using the previous label within each half. Consequently,
  an abstention around a real handover can extend the old team's possession.
- No score or accuracy claim is made. The output requires review only through allowed automatic
  checks; the required organizer clarification forbids prediction-versus-video inspection.
