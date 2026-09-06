"""Narration pipeline: make the English voice-over say "Gerbal" wherever the narrator says "Kerbal".

    tools\venv\Scripts\python tools\vo_gerbal.py <step> [--workdir reference/audio] [--verify] [--limit N]

Steps (outputs go to the work dir, git-ignored because they hold decoded stock audio):
  events      dump English/VO_*.bnk with wwiser and write vo_events.json (stock event id -> wem source ids)
  transcribe  decode every English .wem and transcribe it with word timestamps (tools/vo_transcribe.py)
  edit        for every "Kerbal" word: shorten the /k/ aspiration so the ear hears /g/ ("Gerbal");
              writes edited/<wem>.wav and edit_report.json (--verify re-transcribes each edited line)
  bank        write mod/HumbleSpaceProgram/assets/soundbanks/HumbleSpaceProgram_narration.bnk (embedded PCM, one
              event per edited stock line) and assets/data/narration_remap.json for the plugin
  all         events, transcribe, edit, bank

Why it works: English initial /k/ and /g/ differ mainly in voice-onset time (the aspiration between the
release burst and the vowel: about 60 to 90 ms for /k/, under 25 ms for /g/). Cutting most of that
aspiration and softening the burst flips the percept from "Kerbal" to "Gerbal" while keeping the
narrator's own voice and timing. The stock Vorbis files cannot be re-encoded without the Wwise tool,
so the edited lines ship as PCM in a generated bank and the plugin remaps the stock events to it.
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys

import numpy as np
import soundfile as sf
from scipy.signal import butter, sosfiltfilt

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ksp2paths  # noqa: E402
from wwise_bank_write import Bank, fnv1  # noqa: E402

DEFAULT_WORKDIR = os.path.join(HERE, "..", "reference", "audio")
MOD_DIR = os.path.join(HERE, "..", "mod", "HumbleSpaceProgram")
WWISER = os.path.join(HERE, "wwiser", "wwiser.pyz")
BANK_NAME = "HumbleSpaceProgram_narration"
VO_BUS = 1459302360       # bus the stock narration actor-mixer routes to (voice sliders live above it)
VO_VOLUME_DB = -6.0       # stock chain: actor-mixer -4 dB + parent actor-mixer -2 dB
WORD_RE = re.compile(r"(?i)^kerbal")

# --- consonant edit parameters (seconds) --------------------------------------------------------
SEARCH_BEFORE, SEARCH_AFTER = 0.25, 0.35   # window around the whisper word start to look for the /k/
KEEP_BURST = 0.016                          # release burst kept (softened); 12 ms reads labial, 18 ms keeps more /k/
KEEP_TAIL = 0.008                           # aspiration kept right before the vowel (formant transitions)
MIN_VOT, MAX_VOT = 0.030, 0.140             # plausible /k/ aspiration length; outside = detection failure
MIN_CUT = 0.010
XFADE = 0.004
BURST_GAIN = 0.8                            # -2 dB on the burst (a strong burst keeps the velar identity)
PREVOICE = 0.050                            # voicing added during the closure before the burst (0 = off)
PREVOICE_LEVEL = 0.12                       # relative to the RMS of the following vowel (about -18 dB)
# Tuning (2026-09-04, 15 words, re-transcribed without context): prevoicing lowers the "Kerbal" readings
# from 4-6 to 3-4 of 15; burst 12 ms gives "verbal/purple" confusions, 18 ms "gerbil/Gribble/Goebbels"
# but one more "Kerbal". The remaining "Kerbal" readings sit in "Kerbal Space Program" style phrases,
# where the language model overrides the acoustics (the Ganong effect works on listeners too).
MIN_WORD_PROB, MIN_WORD_LEN = 0.4, 0.08     # whisper words below this are hallucinations, not narration


def envelope(x, sr, lo, hi, smooth_ms):
    sos = butter(4, [lo, hi], btype="band", fs=sr, output="sos")
    y = sosfiltfilt(sos, x)
    n = max(1, int(sr * smooth_ms / 1000))
    e = np.convolve(y * y, np.ones(n) / n, mode="same")
    return np.sqrt(np.maximum(e, 0))


def find_k(x, sr, t_word):
    """Locate the /k/ of a word starting near t_word. Returns (burst, vowel_onset) in samples or None."""
    hf = envelope(x, sr, 1500, min(7000, sr / 2 - 100), 6)
    lf = envelope(x, sr, 80, 700, 10)
    s = lambda t: int(max(0, min(len(x) - 1, round(t * sr))))
    w0, w1 = s(t_word - SEARCH_BEFORE), s(t_word + SEARCH_AFTER)
    if w1 - w0 < sr * 0.1:
        return None
    lf_peak = lf[w0:w1].max()
    if lf_peak <= 0:
        return None
    candidates = []
    hold = int(0.015 * sr)
    i = w0
    while i < w1 - hold:
        if lf[i] > 0.4 * lf_peak and lf[i:i + hold].mean() > 0.35 * lf_peak:
            # i is a vowel onset; look for aspiration + closure right before it
            v = i
            a0, a1 = max(0, v - int(0.16 * sr)), v
            seg = hf[a0:a1]
            if len(seg) == 0:
                break
            thr = 0.12 * seg.max()
            # walk back from the vowel while the high band stays "on" (aspiration/burst)
            j = a1 - 1
            while j > a0 and hf[j] > thr:
                j -= 1
            burst = j + 1
            vot = (v - burst) / sr
            closure = 0
            k = burst - 1
            while k > 0 and hf[k] <= thr and closure < int(0.05 * sr):
                closure += 1
                k -= 1
            if MIN_VOT <= vot <= MAX_VOT and closure >= int(0.012 * sr):
                candidates.append((abs(burst / sr - t_word), burst, v, vot))
            # skip past this voiced stretch
            while i < w1 and lf[i] > 0.25 * lf_peak:
                i += 1
        i += 1
    if not candidates:
        return None
    candidates.sort()
    _, burst, v, vot = candidates[0]
    return burst, v


def prevoice(x, sr, burst, vowel):
    """Add faint low-frequency voicing (glottal buzz) during the closure before the burst, the second
    cue that separates /g/ from /k/. The pitch is estimated from the vowel that follows."""
    seg = x[vowel:vowel + int(0.06 * sr)]
    if len(seg) < int(0.03 * sr):
        return x
    seg = seg - seg.mean()
    ac = np.correlate(seg, seg, "full")[len(seg) - 1:]
    lo, hi = int(sr / 300), int(sr / 60)
    if hi >= len(ac) or ac[0] <= 0:
        return x
    f0 = sr / (lo + int(np.argmax(ac[lo:hi])))
    n = min(int(PREVOICE * sr), burst)
    if n < int(0.02 * sr):
        return x
    t = np.arange(n) / sr
    buzz = sum(np.sin(2 * np.pi * f0 * k * t) / k for k in (1, 2, 3))
    buzz *= np.linspace(0, 1, n) ** 0.5
    vowel_rms = np.sqrt(np.mean(seg ** 2)) + 1e-9
    buzz *= PREVOICE_LEVEL * vowel_rms / (np.sqrt(np.mean(buzz ** 2)) + 1e-9)
    y = x.copy()
    y[burst - n:burst] += buzz.astype(y.dtype)
    return y


def k_to_g(x, sr, burst, vowel):
    """Shorten the aspiration between burst and vowel onset, soften the burst and add prevoicing.
    Returns (new array, samples removed) or None when the aspiration is already short."""
    cut0 = burst + int(KEEP_BURST * sr)
    cut1 = vowel - int(KEEP_TAIL * sr)
    if cut1 - cut0 < int(MIN_CUT * sr):
        return None
    y = prevoice(x, sr, burst, vowel) if PREVOICE > 0 else x.copy()
    nb = cut0 - burst
    ramp = np.linspace(1.0, BURST_GAIN, max(1, nb // 3))
    gain = np.concatenate([ramp, np.full(nb - len(ramp), BURST_GAIN)])[:nb]
    y[burst:cut0] *= gain
    nx = int(XFADE * sr)
    fade_out = 0.5 * (1 + np.cos(np.linspace(0, np.pi, nx)))
    fade_in = 1 - fade_out
    head = y[:cut0].copy()
    tail = y[cut1:].copy()
    # overlap the last nx samples of head with the first nx samples of tail
    if len(head) >= nx and len(tail) >= nx:
        mix = head[-nx:] * fade_out + tail[:nx] * fade_in
        out = np.concatenate([head[:-nx], mix, tail[nx:]])
    else:
        out = np.concatenate([head, tail])
    return out, len(x) - len(out)


def step_events(workdir):
    au = ksp2paths.audio_dir()
    txtp = os.path.join(workdir, "wwiser_vo", "txtp")
    os.makedirs(txtp, exist_ok=True)
    banks = glob.glob(os.path.join(au, "English", "*.bnk"))
    cmd = [sys.executable, WWISER, "-d", "none", "-g", "-go", txtp, "-gw", au, os.path.join(au, "Init.bnk")] + banks
    subprocess.run(cmd, check=True, cwd=os.path.join(workdir, "wwiser_vo"), capture_output=True)
    rows = {}
    for p in glob.glob(os.path.join(txtp, "*.txtp")):
        t = open(p, encoding="utf-8", errors="replace").read()
        ev = re.findall(r"CAkEvent\[\d+\] (\d+)", t)
        if not ev:
            continue
        bank = re.search(r"# - .*/([^/]+\.bnk)", t).group(1)
        rows[ev[0]] = {
            "bank": bank,
            "sounds": re.findall(r"CAkSound\[\d+\] (\d+)", t),
            "sources": re.findall(r"Source (\d+)", t),
            "initialDelay": [float(d) for d in re.findall(r"\[InitialDelay\]: ([\d.]+)", t)],
            "classes": sorted(set(re.findall(r"(CAk[A-Za-z]+)\[", t))),
        }
    out = os.path.join(workdir, "vo_events.json")
    json.dump(rows, open(out, "w"), indent=1)
    single = sum(1 for r in rows.values() if len(r["sources"]) == 1)
    print(f"events: {len(rows)} stock narration events ({single} single-clip) -> {out}")
    return rows


def step_transcribe(workdir):
    import vo_transcribe
    sys.argv = [sys.argv[0], workdir]
    vo_transcribe.main()


def kerbal_words(entry):
    """Kerbal words with trustworthy timestamps. Whisper occasionally hallucinates repeated phrases
    ("Kerbal Space Center. Kerbal Space Center. ...") with zero-length words and near-zero
    probabilities; those are dropped here and the /k/ detector guards the rest."""
    out, seen = [], set()
    for w in entry["words"]:
        if not WORD_RE.match(w["word"].strip(" ,.;:!?\"'")):
            continue
        if w["prob"] < MIN_WORD_PROB or w["end"] - w["start"] < MIN_WORD_LEN or w["start"] in seen:
            continue
        seen.add(w["start"])
        out.append(w)
    return out


def hallucinated(entry, repeats=4):
    """True when the transcript loops: the same 1- to 3-word phrase repeated `repeats` times in a row.
    Such lines get a second, prompt-free transcription before any edit (the Kerbal-biased prompt is
    what makes the loop say Kerbal, and the words it invents land on unrelated consonants)."""
    words = [w["word"].strip(" ,.;:!?\"'").lower() for w in entry["words"]]
    for n in (1, 2, 3):
        for offset in range(n):
            run = 1
            for i in range(offset + n, len(words) - n + 1, n):
                if words[i:i + n] == words[i - n:i]:
                    run += 1
                    if run >= repeats:
                        return True
                else:
                    run = 1
    return False


def step_edit(workdir, verify=False, limit=0):
    transcripts = json.load(open(os.path.join(workdir, "transcripts.json")))
    outdir = os.path.join(workdir, "edited")
    os.makedirs(outdir, exist_ok=True)
    report = {}
    lines = [(wid, e) for wid, e in sorted(transcripts.items()) if kerbal_words(e)]
    if limit:
        lines = lines[:limit]
    print(f"edit: {len(lines)} of {len(transcripts)} lines contain a Kerbal word")
    import vo_transcribe
    for wid, entry in lines:
        x, sr = sf.read(os.path.join(workdir, "en_wav", wid + ".wav"), dtype="float32")
        if x.ndim > 1:
            x = x.mean(axis=1)
        if hallucinated(entry):
            text, words = vo_transcribe.transcribe_array(x, sr, prompt=None, vad=True)
            entry = {"text": text, "words": words}
            n = len(kerbal_words(entry))
            print(f"  {wid}: transcript loops, re-transcribed without prompt: {n} Kerbal word(s) | {text[:90]}")
            if n == 0:
                report[wid] = {"text": text, "sr": sr, "edits": [], "skipped": [], "hallucinated": True}
                continue
        edits, skipped = [], []
        # edit from the end so earlier sample positions stay valid
        for w in sorted(kerbal_words(entry), key=lambda w: -w["start"]):
            found = find_k(x, sr, w["start"])
            if not found:
                skipped.append({"word": w["word"], "start": w["start"], "reason": "no /k/ found"})
                continue
            burst, vowel = found
            res = k_to_g(x, sr, burst, vowel)
            if res is None:
                skipped.append({"word": w["word"], "start": w["start"], "reason": "aspiration already short"})
                continue
            x, removed = res
            edits.append({"word": w["word"], "start": w["start"], "burst": round(burst / sr, 3),
                          "vowel": round(vowel / sr, 3), "votBefore": round((vowel - burst) / sr, 3),
                          "votAfter": round(KEEP_BURST + KEEP_TAIL, 3), "_burst": burst, "_removed": removed})
        edits.reverse()
        # where each edited burst ended up after the cuts made before it
        for i, e in enumerate(edits):
            e["editedAt"] = round((e["_burst"] - sum(p["_removed"] for p in edits[:i])) / sr, 3)
        rec = {"text": entry["text"], "sr": sr, "edits": [{k: v for k, v in e.items() if not k.startswith("_")} for e in edits],
               "skipped": skipped}
        if edits:
            out = os.path.join(outdir, wid + ".wav")
            sf.write(out, np.clip(x, -1, 1), sr, subtype="PCM_16")
            rec["wav"] = out
            if verify:
                # Transcribe a short snippet around each edit without the Kerbal-biased prompt, so the
                # language model has as little context as possible to "correct" what it hears.
                heard = []
                for e in rec["edits"]:
                    a = max(0, int((e["editedAt"] - 0.25) * sr))
                    b = min(len(x), int((e["editedAt"] + 0.9) * sr))
                    text, words = vo_transcribe.transcribe_array(x[a:b], sr, prompt=None)
                    heard.append(text.strip())
                rec["verifyHeard"] = heard
        report[wid] = rec
        flag = "" if not skipped else f"  (skipped {len(skipped)})"
        heard = f"  heard: {rec.get('verifyHeard')}" if verify and edits else ""
        print(f"  {wid}: {len(edits)} edit(s){flag}{heard}")
    json.dump(report, open(os.path.join(workdir, "edit_report.json"), "w"), indent=1)
    n_ed = sum(1 for r in report.values() if r["edits"])
    n_sk = sum(len(r["skipped"]) for r in report.values())
    print(f"edit: {n_ed} lines edited, {sum(len(r['edits']) for r in report.values())} words changed, {n_sk} words skipped")
    return report


def step_bank(workdir):
    events = json.load(open(os.path.join(workdir, "vo_events.json")))
    report = json.load(open(os.path.join(workdir, "edit_report.json")))
    edited = {wid: r for wid, r in report.items() if r.get("wav")}
    bank = Bank(BANK_NAME)
    lines, unsupported = [], []
    for ev, info in sorted(events.items()):
        srcs = info["sources"]
        hit = [s for s in srcs if s in edited]
        if not hit:
            continue
        if len(srcs) != 1:
            unsupported.append({"stockEventId": int(ev), "sources": srcs, "reason": "multi-clip container"})
            continue
        wid = srcs[0]
        samples, rate = sf.read(edited[wid]["wav"], dtype="int16")
        delay = info["initialDelay"][0] if info["initialDelay"] else None
        name = f"Play_Gerbal_VO_{ev}"
        event_id = bank.add_line(name, samples, rate, VO_BUS, VO_VOLUME_DB, delay, source_name=f"{name}_media",
                                 extra={"stockEventId": int(ev), "stockSourceId": int(wid), "stockBank": info["bank"],
                                        "text": edited[wid]["text"], "words": len(edited[wid]["edits"])})
        lines.append(bank.manifest[-1])
    bank_dir = os.path.join(MOD_DIR, "assets", "soundbanks")
    os.makedirs(bank_dir, exist_ok=True)
    bank_path = os.path.join(bank_dir, BANK_NAME + ".bnk")
    data = bank.build()
    open(bank_path, "wb").write(data)
    remap = {"_comment": "Generated by tools/vo_gerbal.py: stock narration events whose line says Kerbal, "
                         "remapped to the Gerbal versions embedded in assets/soundbanks/" + BANK_NAME + ".bnk.",
             "bank": BANK_NAME, "bankId": bank.id, "lines": lines, "unsupported": unsupported}
    remap_path = os.path.join(MOD_DIR, "assets", "data", "narration_remap.json")
    json.dump(remap, open(remap_path, "w"), indent=1)
    secs = sum(l["samples"] / l["rate"] for l in lines)
    print(f"bank: {len(lines)} lines, {secs / 60:.1f} min of audio, {len(data) / 1e6:.1f} MB -> {bank_path}")
    print(f"bank: remap table -> {remap_path}; unsupported events: {len(unsupported)}")
    return remap


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=["events", "transcribe", "edit", "bank", "all"])
    ap.add_argument("--workdir", default=DEFAULT_WORKDIR)
    ap.add_argument("--verify", action="store_true", help="re-transcribe edited lines and report what is heard")
    ap.add_argument("--limit", type=int, default=0, help="edit only the first N lines (testing)")
    a = ap.parse_args()
    workdir = os.path.abspath(a.workdir)
    os.makedirs(workdir, exist_ok=True)
    if a.step in ("events", "all"):
        step_events(workdir)
    if a.step in ("transcribe", "all"):
        step_transcribe(workdir)
    if a.step in ("edit", "all"):
        step_edit(workdir, a.verify, a.limit)
    if a.step in ("bank", "all"):
        step_bank(workdir)


if __name__ == "__main__":
    main()
