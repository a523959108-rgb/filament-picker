import numpy as np
import pytest

from filament_picker.kmeans import kmeans, sample_pixels


def _two_clusters() -> np.ndarray:
    rng = np.random.default_rng(1)
    return np.vstack(
        [
            np.array([20.0, 0.0, 0.0]) + rng.uniform(-0.5, 0.5, (500, 3)),
            np.array([80.0, 0.0, 0.0]) + rng.uniform(-0.5, 0.5, (500, 3)),
        ]
    )


def test_kmeans_two_clusters() -> None:
    centers, labels, shares = kmeans(_two_clusters(), 2)
    ordered = centers[np.argsort(centers[:, 0])]
    expected = np.array([[20.0, 0.0, 0.0], [80.0, 0.0, 0.0]])
    assert np.linalg.norm(ordered - expected, axis=1).max() < 1.0
    assert np.abs(shares - 0.5).max() <= 0.01
    assert shares.sum() == pytest.approx(1.0)
    assert labels.shape == (1000,)


def test_kmeans_is_deterministic() -> None:
    X = _two_clusters()
    centers1, labels1, _ = kmeans(X, 2)
    centers2, labels2, _ = kmeans(X, 2)
    assert np.array_equal(centers1, centers2)
    assert np.array_equal(labels1, labels2)


def test_kmeans_all_same_points() -> None:
    X = np.tile([50.0, 10.0, 10.0], (100, 1))
    centers, _, shares = kmeans(X, 4)
    assert centers.shape == (1, 3)
    assert shares.tolist() == [1.0]


def test_kmeans_limits_clusters_to_unique_points() -> None:
    X = np.vstack([np.tile([10.0, 0.0, 0.0], (50, 1)), np.tile([20.0, 0.0, 0.0], (50, 1))])
    centers, _, _ = kmeans(X, 6)
    assert centers.shape == (2, 3)


def test_kmeans_rejects_empty_input_and_invalid_k() -> None:
    with pytest.raises(ValueError):
        kmeans(np.zeros((0, 3)), 2)
    with pytest.raises(ValueError):
        kmeans(np.zeros((1, 3)), 0)


def test_sample_pixels_returns_input_when_small() -> None:
    X = np.zeros((10, 3))
    sampled = sample_pixels(X, 20)
    assert sampled.shape == (10, 3)


def test_sample_pixels_samples_unique_rows_deterministically() -> None:
    X = np.arange(300.0).reshape(100, 3)
    sampled1 = sample_pixels(X, 20)
    sampled2 = sample_pixels(X, 20)
    assert sampled1.shape == (20, 3)
    assert np.unique(sampled1, axis=0).shape[0] == 20
    assert np.array_equal(sampled1, sampled2)
