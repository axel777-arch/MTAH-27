import unittest

import numpy as np

from starter.possession_model import InferenceConfig, TrackingSignals, infer_labels


def signals(team_distances, ball_x=None, ball_y=None, ball_speed=None, player_count=None):
    distances = np.asarray(team_distances, dtype=np.float64)
    frames = len(distances)
    return TrackingSignals(
        team_distances_m=distances,
        ball_x=np.full(frames, 0.5) if ball_x is None else np.asarray(ball_x, dtype=np.float64),
        ball_y=np.full(frames, 0.5) if ball_y is None else np.asarray(ball_y, dtype=np.float64),
        ball_speed_mps=(
            np.ones(frames) if ball_speed is None
            else np.asarray(ball_speed, dtype=np.float64)
        ),
        player_count=(
            np.full(frames, 22) if player_count is None
            else np.asarray(player_count, dtype=np.int16)
        ),
    )


class InferLabelsTests(unittest.TestCase):
    def setUp(self):
        self.config = InferenceConfig(confirm_observations=3)

    def test_requires_persistent_control_before_initial_owner(self):
        data = signals([[1.0, 5.0]] * 2 + [[1.0, 5.0]] * 3)
        result = infer_labels(data, config=self.config)
        self.assertEqual(list(result), ["X", "X", "H", "H", "H"])

    def test_isolated_opponent_touch_does_not_change_owner(self):
        data = signals(
            [[1.0, 5.0]] * 3 + [[5.0, 1.0]] + [[1.0, 5.0]] * 2
        )
        result = infer_labels(data, config=self.config)
        self.assertEqual(list(result), ["X", "X", "H", "H", "H", "H"])

    def test_confirmed_opponent_control_changes_owner(self):
        data = signals(
            [[1.0, 5.0]] * 3 + [[5.0, 1.0]] * 3
        )
        result = infer_labels(data, config=self.config)
        self.assertEqual(list(result), ["X", "X", "H", "H", "H", "A"])

    def test_out_of_bounds_ball_is_dead_and_resets_owner(self):
        data = signals(
            [[1.0, 5.0]] * 3 + [[1.0, 5.0]] * 3 + [[5.0, 1.0]] * 3,
            ball_x=[0.5, 0.5, 0.5, 1.01, 1.01, 1.01, 0.5, 0.5, 0.5],
        )
        result = infer_labels(data, config=self.config)
        self.assertEqual(
            list(result), ["X", "X", "H", "D", "D", "D", "X", "X", "A"])

    def test_single_frame_out_of_bounds_spike_is_not_dead_ball(self):
        data = signals(
            [[1.0, 5.0]] * 4,
            ball_x=[0.5, 0.5, 1.01, 0.5],
        )
        result = infer_labels(data, config=self.config)
        self.assertNotIn("D", result)

    def test_stationary_ball_in_set_piece_interval_is_dead(self):
        data = signals(
            [[1.0, 5.0]] * 7,
            ball_speed=[0.0] * 5 + [1.0, 1.0],
        )
        result = infer_labels(
            data, set_piece_mask=[True] * 7, config=self.config
        )
        self.assertEqual(list(result), ["D", "D", "D", "D", "D", "X", "X"])

    def test_brief_stationary_ball_in_set_piece_interval_is_not_dead(self):
        data = signals(
            [[1.0, 5.0]] * 4,
            ball_speed=[0.0, 0.0, 1.0, 1.0],
        )
        result = infer_labels(
            data, set_piece_mask=[True] * 4, config=self.config
        )
        self.assertNotIn("D", result)

    def test_set_piece_tag_alone_does_not_mean_dead_ball(self):
        data = signals([[1.0, 5.0]] * 4)
        result = infer_labels(
            data, set_piece_mask=[True, True, True, True], config=self.config
        )
        self.assertNotIn("D", result)

    def test_missing_opponent_tracking_does_not_create_false_confidence(self):
        data = signals([[1.0, np.inf]] * 4)
        result = infer_labels(data, config=self.config)
        self.assertEqual(list(result), ["X", "X", "X", "X"])

    def test_missing_ball_keeps_current_owner(self):
        data = signals(
            [[1.0, 5.0]] * 3 + [[np.inf, np.inf]] * 2,
            ball_x=[0.5, 0.5, 0.5, np.nan, np.nan],
            ball_y=[0.5, 0.5, 0.5, np.nan, np.nan],
        )
        result = infer_labels(data, config=self.config)
        self.assertEqual(list(result), ["X", "X", "H", "H", "H"])

    def test_no_tracked_players_produces_abstention(self):
        data = signals(
            [[1.0, 5.0]] * 3 + [[np.inf, np.inf]] * 3 + [[5.0, 1.0]] * 3,
            player_count=[22, 22, 22, 0, 0, 0, 22, 22, 22],
        )
        config = InferenceConfig(confirm_observations=3, no_player_reset_frames=3)
        result = infer_labels(data, config=config)
        self.assertEqual(list(result), ["X", "X", "H", "X", "X", "X", "X", "X", "A"])


if __name__ == "__main__":
    unittest.main()
