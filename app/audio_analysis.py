"""Audio accents and randomized, frame-aligned edit decisions."""
from __future__ import annotations
import numpy as np
from scipy import signal, ndimage

SAMPLE_RATE = 22050
HOP = 220


def detect_accents(samples: np.ndarray, sr: int = SAMPLE_RATE):
    """Return (seconds, strengths); bass-weighted transient heuristic, not AI separation."""
    if len(samples) < 1024 or np.max(np.abs(samples)) < 1e-6:
        return np.empty(0), np.empty(0)
    # Blocks bound STFT memory even for long audio. Overlap keeps edge onsets.
    all_t, all_s = [], []
    block = 30 * sr
    margin = sr
    for start in range(0, len(samples), block):
        left, right = max(0, start - margin), min(len(samples), start + block + margin)
        audio = samples[left:right]
        if len(audio) < 1024:
            continue
        freq, times, z = signal.stft(audio, sr, nperseg=1024,
                                    noverlap=1024-HOP, boundary='zeros')
        mag = np.abs(z)
        low = np.sqrt(np.mean(mag[(freq >= 35) & (freq <= 180)]**2, axis=0))
        flux = np.mean(np.maximum(np.diff(mag, axis=1, prepend=mag[:, :1]), 0), axis=0)
        rise = np.maximum(np.diff(low, prepend=low[0]), 0)
        def normalize(x):
            scale = float(np.percentile(x, 95))
            if scale < 1e-10:
                scale = float(np.max(x))
            return x / max(scale, 1e-10)
        curve = 0.8 * normalize(rise) + 0.2 * normalize(flux)
        baseline = ndimage.median_filter(curve, size=51)
        novelty = np.maximum(curve-baseline, 0)
        top = float(np.max(novelty))
        if top < 1e-8:
            continue
        peaks, _ = signal.find_peaks(novelty, distance=max(1, int(.17*sr/HOP)),
                                    prominence=max(.04*top, .035), height=.06*top)
        # Analysis window is centered: positive energy rise precedes its center.
        pts = np.maximum(0, times[peaks] + left/sr)
        valid = (pts >= start/sr) & (pts < min(start+block, len(samples))/sr)
        all_t.extend(pts[valid].tolist())
        all_s.extend(novelty[peaks][valid].tolist())
    times, strengths = np.asarray(all_t), np.asarray(all_s)
    if not len(times):
        return times, strengths
    # Remove rare duplicates around analysis-block boundaries, prefer stronger peak.
    kept = []
    for idx in np.argsort(-strengths):
        if all(abs(times[idx]-times[j]) >= .15 for j in kept):
            kept.append(int(idx))
    kept.sort(key=lambda i: times[i])
    return times[kept], strengths[kept]


def choose_cuts(times, strengths, total_frames, fps, rng, density=.5,
                min_shot=.35, max_shot=5.):
    """Mix short runs with held shots; only force a timed cut across long gaps."""
    minimum = max(1, int(np.ceil(min_shot * fps)))
    maximum = max(minimum, int(np.floor(max_shot * fps)))
    candidates = {}
    scale = max(float(np.percentile(strengths, 85)), 1e-9) if len(strengths) else 1.
    for t, s in zip(times, strengths):
        frame = int(round(float(t)*fps))
        if 0 < frame < total_frames:
            candidates[frame] = max(candidates.get(frame, 0.), float(s)/scale)
    frames = np.array(sorted(candidates), dtype=int)
    weights = np.array([candidates[f] for f in frames])
    cuts, fallback, burst_left = [0], [], 0
    while total_frames-cuts[-1] > minimum:
        last = cuts[-1]
        remaining = total_frames-last
        if remaining <= maximum and rng.random() < .13:
            break
        if burst_left == 0 and rng.random() < .08 + .4*density:
            burst_left = int(rng.integers(2, 5))
        if burst_left:
            target = rng.uniform(.35, .85)
            burst_left -= 1
        else:
            target = rng.uniform(1.3, 3.9) * (1.25-.7*density)
        target = float(np.clip(target*fps, minimum, maximum))
        eligible = (frames >= last+minimum) & (frames <= last+maximum)
        eligible &= frames <= total_frames-minimum
        fs, ws = frames[eligible], weights[eligible]
        if len(fs):
            spread = max(.3*fps, .35*target)
            probability = np.exp(-.5*((fs-last-target)/spread)**2)
            probability *= .2 + np.minimum(ws, 5.)**1.2
            probability /= probability.sum()
            chosen = int(rng.choice(fs, p=probability))
        elif remaining > maximum:
            chosen = last+maximum
            # Avoid a tiny final shot, while preserving the maximum when possible.
            if total_frames-chosen < minimum:
                chosen = max(last+minimum, total_frames-minimum)
            fallback.append(chosen)
        else:
            break
        cuts.append(chosen)
    cuts.append(total_frames)
    return cuts, fallback
