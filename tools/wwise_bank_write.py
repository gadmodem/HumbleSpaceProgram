"""Write a minimal Wwise soundbank (bank format 140, Wwise 2021.1) without the Wwise authoring tool.

Supports embedded 16-bit PCM media, one Sound per media file, and one Play action plus one Event per
Sound. The byte layouts mirror the stock KSP2 Redux banks (English/VO_events.bnk, VO_media.bnk) as
dumped by wwiser; see docs/audio-events.md ("Generated banks").

Library use:
    bank = Bank("HumanKerbals_narration")
    bank.add_line("Play_Gerbal_VO_123", samples_int16, 48000, bus_id=1459302360, volume_db=-6.0)
    open(path, "wb").write(bank.build())

CLI use (one line per JSON spec entry, see tools/vo_gerbal.py for the producer):
    python wwise_bank_write.py spec.json out.bnk
"""
import json
import struct
import sys

import numpy as np


# Wwise object ids and bank ids are FNV-1 32-bit hashes of the lower-cased name (AK::SoundEngine::GetIDFromString).
def fnv1(name: str) -> int:
    h = 2166136261
    for b in name.lower().encode():
        h = (h * 16777619) & 0xFFFFFFFF
        h ^= b
    return h


LANGUAGE_SFX = 393239870        # dwLanguageID of every non-localized stock bank ("sfx")
PROJECT_ID = 5643               # dwProjectID of the stock banks
PLUGIN_PCM = 0x00010001         # AkBankSourceData.ulPluginID for PCM (codec 1, Audiokinetic)
HIRC_SOUND, HIRC_ACTION, HIRC_EVENT = 2, 3, 4
ACTION_PLAY = 0x0403
PROP_VOLUME, PROP_INITIAL_DELAY = 0x00, 0x3B


def pcm_wem(samples: np.ndarray, rate: int) -> bytes:
    """RIFF/WAVE as Wwise writes PCM media: WAVE_FORMAT_EXTENSIBLE (0xFFFE) with the 24-byte Wwise
    AkWAVEFORMATEXTENSIBLE (no SubFormat GUID), mono or stereo, 16-bit."""
    if samples.ndim == 1:
        samples = samples[:, None]
    channels = samples.shape[1]
    data = np.ascontiguousarray(samples.astype("<i2")).tobytes()
    block_align = 2 * channels
    channel_mask = 0x4 if channels == 1 else 0x3      # FC / FL+FR, as in the stock files
    fmt = struct.pack("<HHIIHHHHI", 0xFFFE, channels, rate, rate * block_align, block_align, 16, 6, 16, channel_mask)
    body = b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt + b"data" + struct.pack("<I", len(data)) + data
    return b"RIFF" + struct.pack("<I", len(body)) + body


def _var(n: int) -> bytes:
    """Wwise 7-bit varint (high bit set = more bytes follow)."""
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def _hirc(kind: int, oid: int, body: bytes) -> bytes:
    payload = struct.pack("<I", oid) + body
    return struct.pack("<BI", kind, len(payload)) + payload


class Bank:
    def __init__(self, name: str, language_id: int = LANGUAGE_SFX, project_id: int = PROJECT_ID):
        self.name = name
        self.id = fnv1(name)
        self.language_id = language_id
        self.project_id = project_id
        self.media = []      # (source_id, wem bytes)
        self.sounds = []     # serialized HIRC objects
        self.actions = []
        self.events = []
        self.manifest = []   # dicts describing what was written, used for the remap table of the plugin

    def add_line(self, event_name: str, samples: np.ndarray, rate: int, bus_id: int, volume_db: float = 0.0,
                 initial_delay: float = None, max_instances: int = 1, source_name: str = None, extra: dict = None):
        """One embedded PCM clip playable through event `event_name` (id = fnv1(name))."""
        source_name = source_name or event_name + "_media"
        source_id = fnv1(source_name)
        sound_id = fnv1(event_name + "_sound")
        action_id = fnv1(event_name + "_play")
        event_id = fnv1(event_name)
        wem = pcm_wem(samples, rate)
        self.media.append((source_id, wem))

        props = [(PROP_VOLUME, float(volume_db))]
        if initial_delay:
            props.append((PROP_INITIAL_DELAY, float(initial_delay)))
        body = struct.pack("<IBIIB", PLUGIN_PCM, 0, source_id, len(wem), 0)   # AkBankSourceData, in-bank media
        body += struct.pack("<BB", 0, 0)                                      # NodeInitialFxParams
        body += struct.pack("<BB", 0, 0)                                      # metadata override, uNumFx
        body += struct.pack("<B", 0)                                          # bOverrideAttachmentParams
        body += struct.pack("<II", bus_id, 0)                                 # OverrideBusId, DirectParentID (none)
        body += struct.pack("<B", 0)                                          # byBitVector (priority etc.)
        body += struct.pack("<B", len(props)) + bytes(p for p, _ in props) + b"".join(struct.pack("<f", v) for _, v in props)
        body += struct.pack("<B", 0)                                          # ranged props
        body += struct.pack("<B", 0)                                          # PositioningParams: inherit (2D)
        body += struct.pack("<BI", 0, 0)                                      # AuxParams
        # AdvSettingsParams: override max instances (bits 2 and 4, as the stock VO actor-mixer), queue from
        # elapsed time, kill voice below threshold, no loudness normalization / envelope.
        body += struct.pack("<BBHBB", 0x14, 1, max_instances, 1, 0)
        body += _var(0) + _var(0)                                             # StateChunk: no state props / groups
        body += struct.pack("<H", 0)                                          # InitialRTPC
        self.sounds.append(_hirc(HIRC_SOUND, sound_id, body))

        action = struct.pack("<HIB", ACTION_PLAY, sound_id, 0)                # type, idExt (target), bIsBus
        action += struct.pack("<BB", 0, 0)                                    # props, ranged props
        action += struct.pack("<BI", 0x04, self.id)                           # PlayActionParams: linear fade, bank
        self.actions.append(_hirc(HIRC_ACTION, action_id, action))

        self.events.append(_hirc(HIRC_EVENT, event_id, _var(1) + struct.pack("<I", action_id)))
        entry = {"event": event_name, "eventId": event_id, "sourceId": source_id, "soundId": sound_id,
                 "samples": int(samples.shape[0]), "rate": rate}
        if extra:
            entry.update(extra)
        self.manifest.append(entry)
        return event_id

    def build(self) -> bytes:
        header = struct.pack("<IIIII", 140, self.id, self.language_id, 16, self.project_id) + b"\0" * 4
        out = b"BKHD" + struct.pack("<I", len(header)) + header
        if self.media:
            index = b""
            data = bytearray()
            for source_id, wem in self.media:
                if len(data) % 16:
                    data += b"\0" * (16 - len(data) % 16)
                index += struct.pack("<III", source_id, len(data), len(wem))
                data += wem
            out += b"DIDX" + struct.pack("<I", len(index)) + index
            out += b"DATA" + struct.pack("<I", len(data)) + bytes(data)
        objects = self.sounds + self.actions + self.events
        hirc = struct.pack("<I", len(objects)) + b"".join(objects)
        out += b"HIRC" + struct.pack("<I", len(hirc)) + hirc
        return out


def main():
    spec_path, out_path = sys.argv[1], sys.argv[2]
    import soundfile as sf
    spec = json.load(open(spec_path))
    bank = Bank(spec["bank"], spec.get("languageId", LANGUAGE_SFX), spec.get("projectId", PROJECT_ID))
    for line in spec["lines"]:
        samples, rate = sf.read(line["wav"], dtype="int16")
        bank.add_line(line["event"], samples, rate, line["bus"], line.get("volumeDb", 0.0), line.get("initialDelay"),
                      line.get("maxInstances", 1), extra=line.get("extra"))
    open(out_path, "wb").write(bank.build())
    manifest_path = spec.get("manifest")
    if manifest_path:
        json.dump({"bank": spec["bank"], "bankId": bank.id, "lines": bank.manifest}, open(manifest_path, "w"), indent=1)
    print(f"wrote {out_path}: {len(bank.media)} clips, bank id {bank.id}")


if __name__ == "__main__":
    main()
