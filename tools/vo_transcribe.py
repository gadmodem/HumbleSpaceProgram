"""Decode the English narration .wem files and transcribe them with word timestamps.

    tools\venv\Scripts\python tools\vo_transcribe.py [workdir]   (default workdir: reference/audio)

Writes <workdir>/en_wav/<id>.wav (vgmstream decode of every StreamingAssets English .wem) and
<workdir>/transcripts.json: {wemId: {sr, duration, text, words: [{word, start, end, prob}]}}.
Uses faster-whisper "small.en" on the CPU (first run downloads the model, about 480 MB).
"""
import glob
import json
import os
import subprocess
import sys
import time
from math import gcd

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

sys.path.insert(0, os.path.dirname(__file__))
import ksp2paths  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
VGMSTREAM = os.path.join(HERE, "vgmstream", "vgmstream-cli.exe")
DEFAULT_WORKDIR = os.path.join(HERE, "..", "reference", "audio")
PROMPT = "Kerbal Space Program. Kerbals. Kerbin. Kerbal Space Center. Kerman. Kerbals are astronauts."

_model = None


def english_dir():
    return os.path.join(ksp2paths.audio_dir(), "English")


def decode_all(workdir):
    wavdir = os.path.join(workdir, "en_wav")
    os.makedirs(wavdir, exist_ok=True)
    wems = sorted(glob.glob(os.path.join(english_dir(), "*.wem")))
    for p in wems:
        out = os.path.join(wavdir, os.path.splitext(os.path.basename(p))[0] + ".wav")
        if not os.path.exists(out):
            subprocess.run([VGMSTREAM, "-o", out, p], check=True, capture_output=True)
    return wavdir, len(wems)


def model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        _model = WhisperModel("small.en", device="cpu", compute_type="int8",
                              cpu_threads=max(2, (os.cpu_count() or 4) - 1))
    return _model


def to16k(audio, sr):
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if sr == 16000:
        return audio.astype(np.float32)
    g = gcd(sr, 16000)
    return resample_poly(audio, 16000 // g, sr // g).astype(np.float32)


def transcribe_array(audio, sr, prompt=PROMPT, vad=False):
    """-> (text, [{word, start, end, prob}]) with times in seconds of the original audio."""
    segs, _ = model().transcribe(to16k(audio, sr), beam_size=5, word_timestamps=True, initial_prompt=prompt,
                                 vad_filter=vad, condition_on_previous_text=False)
    words, text = [], []
    for s in segs:
        text.append(s.text)
        for w in (s.words or []):
            words.append({"word": w.word, "start": round(w.start, 3), "end": round(w.end, 3), "prob": round(w.probability, 3)})
    return "".join(text).strip(), words


def main():
    workdir = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_WORKDIR)
    t0 = time.time()
    wavdir, n = decode_all(workdir)
    print(f"decoded {n} wems into {wavdir} ({time.time() - t0:.1f}s)", flush=True)
    outp = os.path.join(workdir, "transcripts.json")
    res = json.load(open(outp)) if os.path.exists(outp) else {}
    t0 = time.time()
    files = sorted(glob.glob(os.path.join(wavdir, "*.wav")))
    for i, p in enumerate(files):
        wid = os.path.splitext(os.path.basename(p))[0]
        if wid in res:
            continue
        audio, sr = sf.read(p, dtype="float32")
        text, words = transcribe_array(audio, sr)
        res[wid] = {"sr": sr, "duration": round(len(audio) / sr, 3), "text": text, "words": words}
        if i % 20 == 0:
            print(f"{i}/{len(files)} {wid}: {text[:90]}", flush=True)
            json.dump(res, open(outp, "w"), indent=1)
    json.dump(res, open(outp, "w"), indent=1)
    print(f"transcribed {len(res)} files ({time.time() - t0:.1f}s) -> {outp}")


if __name__ == "__main__":
    main()
