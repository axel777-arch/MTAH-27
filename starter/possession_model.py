"""Deterministic, tracking-first possession inference for the tactical recording.

This model has no learned parameters. Its thresholds are fixed a priori and are not fitted to
this match, its video, or any possession labels. It reads the tracking and Smart Tagging as
inference inputs, then writes the official frame,label CSV.

    python starter/possession_model.py --out evaluation/results/submission.csv

The generated labels are not hand-corrected. Do not compare them visually with the video or use
the public possession labels to tune this model.
"""

import argparse
import math
import os
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from games import GAME, GAMES, require, source_frames  # noqa: E402
from starter.baseline import team_of_each_track  # noqa: E402


HOME, AWAY = 0, 1
LABEL_BY_TEAM = ("H", "A")


@dataclass(frozen=True)
class InferenceConfig:
    """Fixed physical/temporal heuristics; values are not learned from this fixture."""

    control_radius_m: float = 2.0
    team_distance_margin_m: float = 0.5
    confirm_observations: int = 10
    pending_gap_frames: int = 2
    no_player_reset_frames: int = 25
    out_of_bounds_margin: float = 0.005
    out_of_bounds_confirm_frames: int = 3
    set_piece_stationary_speed_mps: float = 0.2
    set_piece_stationary_confirm_frames: int = 5


@dataclass
class TrackingSignals:
    """Frame-indexed evidence parsed from the raw tactical ATD."""

    team_distances_m: np.ndarray
    ball_x: np.ndarray
    ball_y: np.ndarray
    ball_speed_mps: np.ndarray
    player_count: np.ndarray


def _read_point(group, frame_id, slot=None):
    """Return normalized x/y and optional speed, or None for a missing object."""
    if group.startswith("N"):
        return None

    values = group.split(",")
    if len(values) < 2:
        raise ValueError("malformed tracking value at frame {}".format(frame_id))
    try:
        x = float(values[0])
        y = float(values[1])
        speed = float(values[2]) if len(values) > 2 else float("nan")
    except ValueError as error:
        where = "frame {}".format(frame_id)
        if slot is not None:
            where += ", track slot {}".format(slot)
        raise ValueError("malformed tracking value at {}".format(where)) from error

    if not (math.isfinite(x) and math.isfinite(y)):
        return None
    return x, y, speed


def read_tracking_signals(raw_path, team_by_slot, n_frames, pitch):
    """Read ATD once and compute nearest-player distances for each team and frame."""
    team_by_slot = np.asarray(team_by_slot)
    if team_by_slot.ndim != 1 or not len(team_by_slot):
        raise ValueError("team_by_slot must be a non-empty one-dimensional array")
    if np.any((team_by_slot != HOME) & (team_by_slot != AWAY)):
        raise ValueError("team_by_slot values must be HOME(0) or AWAY(1)")

    length, width = pitch
    distances = np.full((n_frames, 2), np.inf, dtype=np.float64)
    ball_x = np.full(n_frames, np.nan, dtype=np.float64)
    ball_y = np.full(n_frames, np.nan, dtype=np.float64)
    ball_speed = np.full(n_frames, np.nan, dtype=np.float64)
    player_count = np.zeros(n_frames, dtype=np.int16)
    records_read = 0

    with open(raw_path, "r", encoding="utf-8") as tracking_file:
        for row_index, line in enumerate(tracking_file):
            if row_index >= n_frames:
                raise ValueError("ATD has more than {} records".format(n_frames))

            parts = line.rstrip("\r\n").split(":", 2)
            if len(parts) != 3:
                raise ValueError("malformed ATD row {}".format(row_index + 1))
            try:
                frame_id = int(parts[0])
            except ValueError as error:
                raise ValueError("invalid frame ID at ATD row {}".format(row_index + 1)) from error
            if frame_id != row_index + 1:
                raise ValueError(
                    "ATD frame IDs must be contiguous from 1; row {} has frame_id {}".format(
                        row_index + 1, frame_id))
            records_read += 1

            player_groups = parts[1].split(";")
            if len(player_groups) != len(team_by_slot):
                raise ValueError(
                    "frame {} has {} player slots; metadata describes {}".format(
                        frame_id, len(player_groups), len(team_by_slot)))

            ball = _read_point(parts[2], frame_id)
            if ball is not None:
                ball_x[row_index], ball_y[row_index], ball_speed[row_index] = ball
                bx, by = ball[0] * length, ball[1] * width

                for slot, group in enumerate(player_groups):
                    player = _read_point(group, frame_id, slot)
                    if player is None:
                        continue
                    player_count[row_index] += 1
                    dx = player[0] * length - bx
                    dy = player[1] * width - by
                    distance = math.hypot(dx, dy)
                    team = int(team_by_slot[slot])
                    if distance < distances[row_index, team]:
                        distances[row_index, team] = distance
            else:
                for group in player_groups:
                    if _read_point(group, frame_id) is not None:
                        player_count[row_index] += 1

    if records_read != n_frames:
        raise ValueError("ATD has {} records; expected {}".format(records_read, n_frames))

    return TrackingSignals(
        team_distances_m=distances,
        ball_x=ball_x,
        ball_y=ball_y,
        ball_speed_mps=ball_speed,
        player_count=player_count,
    )


def load_set_piece_mask(path, n_frames, fps):
    """Convert automatic SET PIECES intervals into a frame mask."""
    mask = np.zeros(n_frames, dtype=bool)
    for instance in ET.parse(path).iter("instance"):
        code = (instance.findtext("code") or "").strip().casefold()
        if code != "set pieces":
            continue

        start_s = float(instance.findtext("start"))
        end_s = float(instance.findtext("end"))
        start = max(0, int(round(start_s * fps)))
        end = min(n_frames, int(round(end_s * fps)))
        if end > start:
            mask[start:end] = True
    return mask


def _candidate_team(distances, config):
    """Return a team only when both sides are tracked and evidence is unambiguous.

    If one team's nearest distance is unavailable, the observed team cannot be considered
    unambiguously closer: the missing side may simply be a tracking gap.
    """
    home_distance, away_distance = distances
    home_visible = math.isfinite(home_distance)
    away_visible = math.isfinite(away_distance)
    if not (home_visible and away_visible):
        return None

    team = HOME if home_distance <= away_distance else AWAY
    nearest = distances[team]
    other = distances[1 - team]
    if nearest > config.control_radius_m:
        return None
    if other - nearest < config.team_distance_margin_m:
        return None
    return team


def _confirmed_runs(mask, minimum_length):
    """Keep only contiguous true-runs that persist for the requested frame count."""
    if minimum_length < 1:
        raise ValueError("minimum_length must be at least one frame")

    if len(mask) == 0:
        return np.zeros(0, dtype=bool)

    confirmed = np.zeros(len(mask), dtype=bool)
    starts = np.flatnonzero(mask & np.concatenate(([True], ~mask[:-1])))
    ends = np.flatnonzero(mask & np.concatenate((~mask[1:], [True]))) + 1
    for start, end in zip(starts, ends):
        if end - start >= minimum_length:
            confirmed[start:end] = True
    return confirmed


def infer_labels(signals, set_piece_mask=None, config=InferenceConfig()):
    """Infer H/A/D/X with controlled-turnover hysteresis and conservative dead-ball cues."""
    distances = np.asarray(signals.team_distances_m, dtype=np.float64)
    if distances.ndim != 2 or distances.shape[1] != 2:
        raise ValueError("team_distances_m must have shape (frames, 2)")
    n_frames = distances.shape[0]

    vectors = (
        signals.ball_x,
        signals.ball_y,
        signals.ball_speed_mps,
        signals.player_count,
    )
    if any(np.asarray(vector).shape != (n_frames,) for vector in vectors):
        raise ValueError("all signal arrays must have the same frame count")

    if set_piece_mask is None:
        set_piece_mask = np.zeros(n_frames, dtype=bool)
    set_piece_mask = np.asarray(set_piece_mask, dtype=bool)
    if set_piece_mask.shape != (n_frames,):
        raise ValueError("set_piece_mask must have shape (frames,)")

    x = np.asarray(signals.ball_x, dtype=np.float64)
    y = np.asarray(signals.ball_y, dtype=np.float64)
    speed = np.asarray(signals.ball_speed_mps, dtype=np.float64)
    player_count = np.asarray(signals.player_count)
    ball_visible = np.isfinite(x) & np.isfinite(y)
    outside_pitch_observed = ball_visible & (
        (x < -config.out_of_bounds_margin)
        | (x > 1.0 + config.out_of_bounds_margin)
        | (y < -config.out_of_bounds_margin)
        | (y > 1.0 + config.out_of_bounds_margin)
    )
    outside_pitch = _confirmed_runs(
        outside_pitch_observed, config.out_of_bounds_confirm_frames)
    stationary_set_piece_observed = (
        set_piece_mask & ball_visible & np.isfinite(speed)
        & (speed <= config.set_piece_stationary_speed_mps)
    )
    stationary_set_piece = _confirmed_runs(
        stationary_set_piece_observed, config.set_piece_stationary_confirm_frames)

    labels = np.full(n_frames, "X", dtype="<U1")
    owner = None
    pending_team = None
    pending_count = 0
    pending_gap = 0
    no_player_run = 0

    for frame in range(n_frames):
        if outside_pitch[frame] or stationary_set_piece[frame]:
            labels[frame] = "D"
            owner = None
            pending_team = None
            pending_count = 0
            pending_gap = 0
            no_player_run = 0
            continue

        if player_count[frame] == 0:
            no_player_run += 1
            labels[frame] = "X"
            pending_team = None
            pending_count = 0
            pending_gap = 0
            if no_player_run >= config.no_player_reset_frames:
                owner = None
            continue
        no_player_run = 0

        candidate = None
        if ball_visible[frame]:
            candidate = _candidate_team(distances[frame], config)

        if candidate is None:
            if pending_team is not None:
                pending_gap += 1
                if pending_gap > config.pending_gap_frames:
                    pending_team = None
                    pending_count = 0
                    pending_gap = 0
        elif candidate == owner:
            pending_team = None
            pending_count = 0
            pending_gap = 0
        else:
            if candidate != pending_team:
                pending_team = candidate
                pending_count = 1
            else:
                pending_count += 1
            pending_gap = 0

            if pending_count >= config.confirm_observations:
                owner = candidate
                pending_team = None
                pending_count = 0
                pending_gap = 0

        if owner is not None:
            labels[frame] = LABEL_BY_TEAM[owner]

    return labels


def write_submission(path, labels, expected_frames):
    """Write and validate the submission contract without consulting ground truth."""
    labels = np.asarray(labels)
    if labels.shape != (expected_frames,):
        raise ValueError("expected {} labels, got shape {}".format(expected_frames, labels.shape))
    if not np.isin(labels, ("H", "A", "D", "X")).all():
        raise ValueError("labels may contain only H, A, D, or X")

    folder = os.path.dirname(os.path.abspath(path))
    if not os.path.isdir(folder):
        os.makedirs(folder)
    with open(path, "w", encoding="utf-8", newline="") as submission:
        submission.write("frame,label\n")
        for frame, label in enumerate(labels):
            submission.write("{},{}\n".format(frame, label))
    return path


def build_submission(output_path, data_dir=None, game=GAME):
    """Run inference using the tactical ATD and automatic Smart Tagging."""
    n_frames = source_frames("tactical", game)
    meta_path, raw_path, tag_path = require(
        ["atd_meta", "atd_raw", "smart_tagging"], game, data_dir, source="tactical")
    team_by_slot = team_of_each_track(meta_path)
    signals = read_tracking_signals(
        raw_path, team_by_slot, n_frames, GAMES[game]["pitch"])
    set_piece_mask = load_set_piece_mask(tag_path, n_frames, GAMES[game]["fps"])
    labels = infer_labels(signals, set_piece_mask)
    write_submission(output_path, labels, n_frames)
    return labels


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--out",
        default=os.path.join(ROOT, "evaluation", "results", "possession_model.csv"),
        help="submission CSV path (default: evaluation/results/possession_model.csv)",
    )
    parser.add_argument("--data-dir", help="match data directory (overrides MTAH_DATA_DIR)")
    args = parser.parse_args()

    labels = build_submission(args.out, args.data_dir)
    counts = {label: int(np.sum(labels == label)) for label in ("H", "A", "D", "X")}
    print("wrote {} frame labels to {}".format(len(labels), args.out))
    print("labels: {}".format("  ".join("{} {}".format(k, v) for k, v in counts.items())))
    print("format check: python evaluation/validate_submission.py {}".format(args.out))


if __name__ == "__main__":
    main()
