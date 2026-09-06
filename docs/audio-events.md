# Kerbal audio events

Source of truth: `KSP2_x64_Data/StreamingAssets/Audio/GeneratedSoundBanks/Windows/`.
Wwise SDK 2021.1.10, bank version 140. Event IDs are FNV-1 32-bit hashes of the lower-cased event
name (`tools/wwise_fnv.py` verifies a candidate name against a bank).

## Banks that matter

| Bank | Size | Content |
| --- | --- | --- |
| `kerbal_sfx_events.bnk` | 99 KB | 53 events, 54 actions, 767 sound objects, 139 random containers, 72 layer containers, 5 switch containers |
| `Kerbals_SFX_media.bnk` | 33 MB | 348 embedded media files (body and suit SFX) |
| `u_Kerbal_voice_media.bnk` | 5.2 MB | 115 embedded media files (voice lines) |
| `u_states_UI_music_utilities_events.bnk` | 926 KB | 816 events; 114 of its sound objects reference the voice media bank (idle/emote chatter lives here) |
| `Science_events.bnk` | 167 KB | 76 sound objects reference the voice media bank (science report chatter) |
| `AMB_emitters_events.bnk` | 41 KB | 59 sound objects reference the voice media bank (ambient vessel chatter, event `Play_amb_vessel_emitter_Vessel_kerbal`) |
| `part_collision_destruction_events.bnk` | 184 KB | collision and explosion VO events referenced from prefabs |

## Events resolved to names (animation-driven, `kerbal_sfx_events.bnk`)

These are posted by `AnimationSoundHandler.PostAnimWWEvent` from animation events on the clips in
`kerbal_shared_assets_all.bundle` (`reference/animation/kerbal_clips.json` has the exact times).

| Wwise ID | Event | Clips using it |
| --- | --- | --- |
| 2866725233 | Play_An_Kerbal_footsteps | 42 |
| 3173329341 | Play_An_Kerbal_ladder_step | 36 |
| 3758935388 | Play_An_Kerbal_footsteps_soft | 24 |
| 2012960661 | Play_An_Kerbal_jump_start | 18 |
| 4095238171 | Play_An_Kerbal_footsteps_land | 17 |
| 584824742 | Play_An_Kerbal_clap | 12 |
| 3163597128 | Play_An_Kerbal_swim_stroke_idle | 10 |
| 2554511463 | Play_An_Kerbal_swim_stroke | 10 |
| 1013572282 | Play_An_Kerbal_getUp_start | 6 |
| 3750898105 | Play_An_Kerbal_jetpack_button | 5 |
| 88226795 | Play_An_Kerbal_helmet_adjust | 5 |
| 4136739858 | Play_An_Kerbal_getUp_push | 4 |
| 1687885291 | Play_An_Kerbal_footsteps_run | 4 |
| 2598784679 | Play_An_Kerbal_jetpack_open_end | 2 |
| 3190787152 | Play_An_Kerbal_helmet_adjust_low | 2 |
| 3443222259 | Play_An_Kerbal_jetpack_close | 2 |
| 2945363349 | Play_An_Kerbal_jetpack_close_end | 2 |
| 2630360581 | Play_An_Kerbal_jetpack_open | 1 |
| 595602680 | Play_An_Kerbal_FlagPlant_02_pull | 1 |
| 1448915143 | Play_An_Kerbal_FlagPlant_03 | 1 |
| 1448915136 | Play_An_Kerbal_FlagPlant_04 | 1 |
| 3379037590 | Play_An_Kerbal_FlagPlant_05_unpack | 1 |
| 1448915138 | Play_An_Kerbal_FlagPlant_06 | 1 |
| 1448915139 | Play_An_Kerbal_FlagPlant_07 | 1 |
| 2415550219 | Play_An_Kerbal_FlagPlant_08_down | 1 |
| 2623016686 | Play_An_Kerbal_FlagPlant_09_impact | 1 |
| 2057301201 .. 2057301209 | Play_An_Kerbal_Gear_adjust_01 .. _09 | 1 each |
| 2074078784 .. 2074078787 | Play_An_Kerbal_Gear_adjust_13, _10, _11, _12 | 1 each |

`Play_AnVo_kerbal_yawn` (2988376420) is also fired from a clip but is defined in another bank.

## Events resolved to names (prefab components)

Found as `WwiseObjectReference` assets on the EVA kerbal prefab chain
(`reference/wwise_refs_from_prefabs.json` has all 195 references found in small bundles):

| Wwise ID | Event |
| --- | --- |
| 4265446274 | Play_Kerbal_part_collision_hit_VO |
| 3260672473 | Play_Kerbal_Part_collision_start_hit_VO |
| 2592821561 | Play_A_explosion_Kerbal |
| 1313592199 | Play_amb_vessel_emitter_Vessel_kerbal |
| 3786974594 | Play_amb_vessel_emitter_Vessel_kerbal_Stop |

## Unresolved event IDs in `kerbal_sfx_events.bnk`

243597081, 366092518, 1344040012, 1388483118, 1713048338, 1923028913, 2130945466 to 2130945470,
2470913776, 3019585202, 3446895873. These are probably jetpack loops, water entry and gear/flag
variants that no clip references directly. Resolve by guessing names with `tools/wwise_fnv.py`, or
by dumping the bank with wwiser (`python tools\wwiser\wwiser.pyz -d xml <bank.bnk>`; `-g` also writes
one `.txtp` play list per event that shows the full event -> action -> container -> source path).
Add resolved names to `stockAudioEvents` in `human_variety.json` so the word rule can pre-compute them.

## Voice lines

The per-kerbal voice is not chosen by event name. `VarietyUtils.ApplyVoiceSelection` and
`ApplyVoiceType` set two RTPCs on the kerbal's `KSPPartAudio` game object:

| RTPC | Range | Source attribute |
| --- | --- | --- |
| `kerbal_voice_selection` | int 0 to 10 | `VOICESELECTION` (VOICE_RANGE_RULE) |
| `kerbal_voice_type` | float 0 to 2 | `VOICETYPE` (VOICE_TYPE_RULE) |

Inside Wwise those RTPCs drive switch/blend containers that pick one of the 115 voice media files.
The human voice bank should expose the same two RTPC names so hero kerbals keep a stable voice
(Jebediah: selection 1, type 0.5; Valentina: selection 2, type 1.0).

## Spoken narration (English voice-over)

The tutorials, briefings and announcements are real English speech, separate from the kerbal
gibberish: `English/VO_events.bnk` (225 events) and `English/VO_videos_events.bnk` (5 events) in the
soundbank folder. Each event is one Play action on one Sound that streams a Wwise-Vorbis file from
`English/<sourceId>.wem` (316 files, 62 minutes; two events are random/layer containers with 7 and 8
clips). Routing: Sound -> actor-mixer 831633582 (-4 dB, one instance at a time, state chunks that mute
VO in some game states) -> actor-mixer 621162271 (-2 dB) -> bus 1459302360 (ducks 4 buses) -> bus
1534528548 (the voice volume slider RTPC 1087520875) -> bus 175183278 -> master 3803692087 (the
master slider RTPC 3720713001). None of these events has a resolvable name; `tools/vo_gerbal.py
events` writes the event -> wem table to `reference/audio/vo_events.json`.

Ten of the lines say "Kerbal" (the word, not Kerbin or Kerman): 15 words in total, found by
transcribing every line with faster-whisper (`tools/vo_transcribe.py`, word timestamps).

## Replacement strategy

The mod never edits stock banks. `Code/AudioRemapPatches.cs` prefixes all sixteen
`AkSoundEngine.PostEvent` overloads (the GameObject overloads call the native layer directly, so the
ulong ones alone would miss them) and rewrites the event name or id before Wwise sees it. Every
remap is filtered by the set of event ids the mod's own banks define (the plugin parses the HIRC
section of each `assets/soundbanks/*.bnk`), so a missing mod event leaves the stock sound in place.
Three sources, all in `assets/data`:

1. **Word rule** (`audioWordSwap` in `human_variety.json`, default Kerbal -> Gerbal): a stock event
   whose name contains the word maps to the same name with the replacement, case preserved
   (`Play_An_Kerbal_footsteps` -> `Play_An_Gerbal_footsteps`, `Play_AnVo_kerbal_yawn` ->
   `Play_AnVo_gerbal_yawn`). `stockAudioEvents` lists the known stock names so the id-only overloads
   can be pre-computed; names arriving as strings are swapped live. Author the mod SFX bank with the
   Gerbal names and the rule covers every kerbal event.
2. **Explicit pairs** (`audioRemap`), exceptions to the rule; empty by default.
3. **Narration table** (`narration_remap.json`, generated): stock VO event id -> mod event
   `Play_Gerbal_VO_<stockEventId>` in `assets/soundbanks/HumanKerbals_narration.bnk`.

### Generated banks (no Wwise authoring tool needed)

`tools/wwise_bank_write.py` writes a bank-version-140 soundbank from WAV files: BKHD (language "sfx"
393239870, project 5643 like the stock banks), DIDX/DATA with embedded 16-bit PCM media (Wwise's
24-byte extensible `fmt`), and a HIRC with one Sound (in-bank source, routed to a bus id, volume
prop, one instance) + Play action + Event per clip, byte layouts copied from the wwiser dump of the
stock VO bank. Banks are loaded from memory (the plugin calls `AkSoundEngine.LoadBankMemoryCopy`;
SpaceWarp2's own soundbank step throws in Redux 0.2.9 because its `ISoundApi.Instance` backend is
null), which is why the media is embedded rather than streamed. Validation: `wwiser` parses the
result with the expected objects, `vgmstream-cli` decodes the embedded media bit-exactly, and
`verify_in_game.ps1 -AudioTest` shows Wwise accepting the events with the expected durations.

### Narration pipeline (`tools/vo_gerbal.py`)

`events` (wwiser dump of the English banks) -> `transcribe` (vgmstream decode + faster-whisper) ->
`edit` -> `bank`. The edit turns the /k/ of every "Kerbal" into a /g/ acoustically: English initial
/k/ and /g/ differ mainly in voice-onset time (aspiration after the release burst, 60-110 ms in these
lines for /k/, about 20 ms for /g/), so the script finds the burst (high-band energy after a closure
gap) and the vowel onset (low-band energy), removes most of the aspiration with a crossfade, softens
the burst by 2 dB and adds 50 ms of faint voicing before the burst. `--verify` re-transcribes a short
context-free snippet around each edit: 11 of 15 words come back as gerbil/girl/Gribble/Goebbels-type
words, the rest stay "Kerbal" only inside "Kerbal Space Program" style phrases where the language
model wins over the acoustics. The edited lines ship as PCM at their original rate (48 kHz mostly),
about 1.6 minutes of audio, and keep the stock InitialDelay and the -6 dB of the stock mixer chain.
State-chunk muting is not reproduced (the lines are short and only play in tutorials).

Work files live in `reference/audio/` (git-ignored: decoded stock audio). Regenerate everything with
`tools\venv\Scripts\python tools\vo_gerbal.py all`, then rebuild the mod.

Listening to the originals: `tools/vgmstream/vgmstream-cli.exe -o out.wav <file.wem>` (also reads
`.bnk` files, `-m` lists embedded media).
