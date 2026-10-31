import wave
import struct
import numpy as np

SAMPLE_RATE = 44100
DURATION = 24.0
TOTAL_SAMPLES = int(SAMPLE_RATE * DURATION)
BPM = 115.0
BEAT_DUR = 60.0 / BPM  # ~0.5217s

t = np.linspace(0, DURATION, TOTAL_SAMPLES, endpoint=False)
left = np.zeros(TOTAL_SAMPLES, dtype=np.float32)
right = np.zeros(TOTAL_SAMPLES, dtype=np.float32)

def add_tone(start_t, dur, freq, amp=0.2, decay=5.0, pan=0.0):
    start_idx = int(start_t * SAMPLE_RATE)
    num_s = int(dur * SAMPLE_RATE)
    if start_idx >= TOTAL_SAMPLES:
        return
    num_s = min(num_s, TOTAL_SAMPLES - start_idx)
    sub_t = np.linspace(0, dur, num_s, endpoint=False)
    env = np.exp(-decay * sub_t)
    wave = amp * np.sin(2 * np.pi * freq * sub_t) * env
    l_amp = 0.5 * (1.0 - pan)
    r_amp = 0.5 * (1.0 + pan)
    left[start_idx:start_idx+num_s] += wave * l_amp
    right[start_idx:start_idx+num_s] += wave * r_amp

def add_kick(start_t, amp=0.7):
    dur = 0.35
    start_idx = int(start_t * SAMPLE_RATE)
    num_s = min(int(dur * SAMPLE_RATE), TOTAL_SAMPLES - start_idx)
    if num_s <= 0 or start_idx >= TOTAL_SAMPLES:
        return
    sub_t = np.linspace(0, dur, num_s, endpoint=False)
    freq = 155.0 * np.exp(-18.0 * sub_t) + 42.0
    phase = 2 * np.pi * np.cumsum(freq) / SAMPLE_RATE
    env = np.exp(-8.0 * sub_t)
    wave = amp * np.sin(phase) * env
    left[start_idx:start_idx+num_s] += wave * 0.5
    right[start_idx:start_idx+num_s] += wave * 0.5

def add_hat(start_t, amp=0.18):
    dur = 0.08
    start_idx = int(start_t * SAMPLE_RATE)
    num_s = min(int(dur * SAMPLE_RATE), TOTAL_SAMPLES - start_idx)
    if num_s <= 0 or start_idx >= TOTAL_SAMPLES:
        return
    noise = np.random.uniform(-1, 1, num_s)
    sub_t = np.linspace(0, dur, num_s, endpoint=False)
    env = np.exp(-40.0 * sub_t)
    left[start_idx:start_idx+num_s] += noise * env * amp * 0.4
    right[start_idx:start_idx+num_s] += noise * env * amp * 0.6

def add_snare(start_t, amp=0.4):
    dur = 0.25
    start_idx = int(start_t * SAMPLE_RATE)
    num_s = min(int(dur * SAMPLE_RATE), TOTAL_SAMPLES - start_idx)
    if num_s <= 0 or start_idx >= TOTAL_SAMPLES:
        return
    sub_t = np.linspace(0, dur, num_s, endpoint=False)
    tone = np.sin(2 * np.pi * 180 * np.exp(-15 * sub_t) * sub_t)
    noise = np.random.uniform(-1, 1, num_s)
    env = np.exp(-12.0 * sub_t)
    wave = (tone * 0.4 + noise * 0.6) * env * amp
    left[start_idx:start_idx+num_s] += wave * 0.5
    right[start_idx:start_idx+num_s] += wave * 0.5

def add_glass_tick(start_t, freq=2800.0, amp=0.25):
    dur = 0.06
    start_idx = int(start_t * SAMPLE_RATE)
    num_s = min(int(dur * SAMPLE_RATE), TOTAL_SAMPLES - start_idx)
    if num_s <= 0 or start_idx >= TOTAL_SAMPLES:
        return
    sub_t = np.linspace(0, dur, num_s, endpoint=False)
    env = np.exp(-50.0 * sub_t)
    wave = amp * (np.sin(2 * np.pi * freq * sub_t) + 0.5 * np.sin(2 * np.pi * (freq * 1.5) * sub_t)) * env
    left[start_idx:start_idx+num_s] += wave * 0.4
    right[start_idx:start_idx+num_s] += wave * 0.6

def add_whoosh(start_t, dur=0.6, amp=0.3):
    start_idx = int(start_t * SAMPLE_RATE)
    num_s = min(int(dur * SAMPLE_RATE), TOTAL_SAMPLES - start_idx)
    if num_s <= 0 or start_idx >= TOTAL_SAMPLES:
        return
    sub_t = np.linspace(0, dur, num_s, endpoint=False)
    noise = np.random.uniform(-1, 1, num_s)
    env = np.sin(np.pi * sub_t / dur) ** 2
    freq_mod = np.sin(2 * np.pi * (200 + 1200 * (sub_t / dur)) * sub_t)
    wave = (noise * 0.7 + freq_mod * 0.3) * env * amp
    left[start_idx:start_idx+num_s] += wave * 0.5
    right[start_idx:start_idx+num_s] += wave * 0.5

def add_takeoff_whoosh(start_t, dur=0.9, amp=0.45):
    start_idx = int(start_t * SAMPLE_RATE)
    num_s = min(int(dur * SAMPLE_RATE), TOTAL_SAMPLES - start_idx)
    if num_s <= 0 or start_idx >= TOTAL_SAMPLES:
        return
    sub_t = np.linspace(0, dur, num_s, endpoint=False)
    noise = np.random.uniform(-1, 1, num_s)
    env = (np.sin(np.pi * sub_t / dur)) ** 1.5
    # Ascending jet/glider tone
    pitch = 180.0 * np.exp(1.5 * (sub_t / dur))
    jet_tone = np.sin(2 * np.pi * pitch * sub_t)
    wave = (noise * 0.6 + jet_tone * 0.4) * env * amp
    left[start_idx:start_idx+num_s] += wave * 0.4
    right[start_idx:start_idx+num_s] += wave * 0.6

def add_stamp_thud(start_t):
    dur = 0.8
    start_idx = int(start_t * SAMPLE_RATE)
    num_s = min(int(dur * SAMPLE_RATE), TOTAL_SAMPLES - start_idx)
    if num_s <= 0 or start_idx >= TOTAL_SAMPLES:
        return
    sub_t = np.linspace(0, dur, num_s, endpoint=False)
    sub_freq = 110.0 * np.exp(-9.0 * sub_t) + 38.0
    sub_phase = 2 * np.pi * np.cumsum(sub_freq) / SAMPLE_RATE
    sub_wave = 0.75 * np.sin(sub_phase) * np.exp(-5.0 * sub_t)
    sparkle = 0.25 * np.sin(2 * np.pi * 3400 * sub_t) * np.exp(-12.0 * sub_t)
    wave = sub_wave + sparkle
    left[start_idx:start_idx+num_s] += wave * 0.5
    right[start_idx:start_idx+num_s] += wave * 0.5

def add_chime(start_t, chord=[523.25, 659.25, 783.99, 1046.50], amp=0.3):
    for i, freq in enumerate(chord):
        add_tone(start_t + i * 0.04, 1.4, freq, amp=amp, decay=3.0, pan=(i-1.5)*0.3)

# 1. 115 BPM Rhythmic Beats across 24s (46 beats)
beats = np.arange(0, DURATION, BEAT_DUR)

for i, bt in enumerate(beats):
    if bt < 8.0:
        if i % 2 == 0:
            add_kick(bt, amp=0.45)
        add_hat(bt + BEAT_DUR * 0.5, amp=0.15)
        chord_freqs = [261.63, 329.63, 392.00] if (i // 4) % 2 == 0 else [293.66, 369.99, 440.00]
        for f in chord_freqs:
            add_tone(bt, 0.4, f * 1.0, amp=0.08, decay=6.0)
    elif bt < 19.0:
        # THE DROP AT 0:08 (Driving electronic pulse)
        if i % 2 == 0:
            add_kick(bt, amp=0.68)
        else:
            add_snare(bt, amp=0.42)
            add_kick(bt, amp=0.32)
        add_hat(bt, amp=0.18)
        add_hat(bt + BEAT_DUR * 0.5, amp=0.22)
        scale = [220.0, 261.63, 293.66, 329.63, 392.00, 440.00, 523.25]
        note_freq = scale[i % len(scale)]
        add_tone(bt, 0.25, note_freq, amp=0.12, decay=8.0, pan=(i % 3 - 1)*0.5)
        add_tone(bt + BEAT_DUR * 0.5, 0.25, note_freq * 1.5, amp=0.09, decay=9.0, pan=-(i % 3 - 1)*0.5)
    elif bt < 22.0:
        if i % 2 == 0:
            add_kick(bt, amp=0.55)
        add_hat(bt + BEAT_DUR * 0.5, amp=0.2)
        chord_c = [261.63, 329.63, 392.00, 523.25]
        for f in chord_c:
            add_tone(bt, 0.5, f, amp=0.12, decay=4.0)
    else:
        add_hat(bt, amp=0.12)
        add_tone(bt, 0.8, 392.00, amp=0.1, decay=3.0)

# 2. Key Storyboard SFX
# 0:00 - 0:01: "12,000 jobs" count-up ticks
for t_tick in np.linspace(0.1, 1.0, 10):
    add_glass_tick(t_tick, freq=2400 + (t_tick * 1000), amp=0.2)

# 0:015: "real" blue pop
add_glass_tick(1.5, freq=3600, amp=0.35)
add_tone(1.5, 0.7, 880.0, amp=0.22, decay=4.0)

# 0:03, 0:04, 0:05: The Pain cuts
add_whoosh(2.8, dur=0.3, amp=0.25)
add_glass_tick(3.0, freq=1800, amp=0.3)  # Ghost shatter
add_glass_tick(4.0, freq=1600, amp=0.35) # Strike
add_glass_tick(5.0, freq=2200, amp=0.3)  # Flip

# 0:06: The Reveal Takeoff Swoosh + Job Pilot Logo bloom
add_takeoff_whoosh(5.8, dur=1.0, amp=0.5)
add_chime(6.4, chord=[440.0, 554.37, 659.25, 880.0], amp=0.3)

# 0:08: DROP KICK at 0:08 (Universal Demo begins)
add_kick(8.0, amp=0.95)

# Role 1: Registered Nurse (0:08 - 0:09.75)
for t_c in [8.2, 8.5, 8.8]:
    add_glass_tick(t_c, freq=2800, amp=0.2)
add_stamp_thud(9.4)

# Role 2: Graphic Designer (0:09.75 - 0:11.5)
add_whoosh(9.65, dur=0.3, amp=0.3)
for t_c in [9.9, 10.2, 10.5]:
    add_glass_tick(t_c, freq=3100, amp=0.2)
add_stamp_thud(11.1)

# Role 3: Accountant (0:11.5 - 0:13.25)
add_whoosh(11.4, dur=0.3, amp=0.3)
for t_c in [11.7, 12.0, 12.3]:
    add_glass_tick(t_c, freq=3300, amp=0.2)
add_stamp_thud(12.8)

# Role 4: Sales Manager (0:13.25 - 0:15.0)
add_whoosh(13.15, dur=0.3, amp=0.3)
for t_c in [13.4, 13.7, 14.0]:
    add_glass_tick(t_c, freq=3500, amp=0.2)
add_stamp_thud(14.6)

# 0:15 - 0:19: Control tiles pop on beats
add_whoosh(14.9, dur=0.4, amp=0.35)
add_glass_tick(15.4, freq=2400, amp=0.25)
add_glass_tick(16.2, freq=2700, amp=0.25)
add_glass_tick(17.0, freq=3000, amp=0.25)
add_glass_tick(17.8, freq=3300, amp=0.25)

# 0:19: Checkmark draw chime
add_whoosh(18.9, dur=0.4, amp=0.35)
add_chime(19.2, chord=[523.25, 659.25, 783.99, 1046.50, 1318.51], amp=0.35)

# 0:22: CTA soft outro chime
add_whoosh(21.9, dur=0.5, amp=0.3)
add_chime(22.2, chord=[440.0, 554.37, 659.25, 880.0], amp=0.28)

# Soft fade out at end for clean loop
fade_samples = int(0.35 * SAMPLE_RATE)
fade = np.linspace(1.0, 0.0, fade_samples)
left[-fade_samples:] *= fade
right[-fade_samples:] *= fade

max_val = max(np.max(np.abs(left)), np.max(np.abs(right)))
if max_val > 0.95:
    left = (left / max_val) * 0.95
    right = (right / max_val) * 0.95

left_pcm = (left * 32767).astype(np.int16)
right_pcm = (right * 32767).astype(np.int16)
interleaved = np.empty((TOTAL_SAMPLES * 2,), dtype=np.int16)
interleaved[0::2] = left_pcm
interleaved[1::2] = right_pcm

with wave.open("audio_track.wav", "w") as f:
    f.setnchannels(2)
    f.setsampwidth(2)
    f.setframerate(SAMPLE_RATE)
    f.writeframes(interleaved.tobytes())

print("Updated Job Pilot audio track generated: audio_track.wav")
