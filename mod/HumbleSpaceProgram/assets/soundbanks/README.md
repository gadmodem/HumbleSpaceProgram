# Soundbanks

The plugin loads every `*.bnk` in this folder at post-initialization (`AkSoundEngine.LoadBankMemoryCopy`)
and registers it with the running Wwise engine, so the events a bank defines become postable by name
or id. SpaceWarp2 has its own "loading soundbanks" step for this folder, but in Redux 0.2.9 its backend
(`SpaceWarp2.Sound.Backend.ISoundApi.Instance`) is null at that point and the step throws a
NullReferenceException for every bank, so the plugin does not rely on it (a bank SpaceWarp2 did load
returns `AK_BankAlreadyLoaded`, which counts as success). The plugin also parses the HIRC section of
each bank and only remaps stock events whose replacement exists.

Requirements that the stock game imposes:

| Item | Value |
| --- | --- |
| Wwise SDK in the game | 2021.1.10 (bank format version 140) |
| Authoring | Wwise 2021.1.x (2021.1.13 is what the Redux docs recommend), or `tools/wwise_bank_write.py` for simple PCM banks |
| Platform | Windows |
| Media | embedded (DIDX/DATA); banks are loaded from memory, streamed files would not be found |

## Event naming: the Gerbal rule

Every stock kerbal event is remapped by name: an event whose name contains `Kerbal` plays through the
mod event with the same name and `Gerbal` instead, case preserved (`audioWordSwap` in
`assets/data/human_variety.json`). Author the SFX and voice bank with exactly these names:

| Stock event | Mod event to author |
| --- | --- |
| `Play_An_Kerbal_footsteps` (and `_soft`, `_run`, `_land`) | `Play_An_Gerbal_footsteps` (...) |
| `Play_An_Kerbal_ladder_step`, `_jump_start`, `_clap`, `_swim_stroke`, `_swim_stroke_idle` | `Play_An_Gerbal_...` |
| `Play_An_Kerbal_getUp_start`, `_getUp_push`, `_helmet_adjust`, `_helmet_adjust_low` | `Play_An_Gerbal_...` |
| `Play_An_Kerbal_jetpack_button`, `_jetpack_open`, `_jetpack_open_end`, `_jetpack_close`, `_jetpack_close_end` | `Play_An_Gerbal_...` |
| `Play_An_Kerbal_FlagPlant_02_pull` ... `_09_impact`, `Play_An_Kerbal_Gear_adjust_01` ... `_13` | `Play_An_Gerbal_...` |
| `Play_AnVo_kerbal_yawn` | `Play_AnVo_gerbal_yawn` |
| `Play_Kerbal_part_collision_hit_VO`, `Play_Kerbal_Part_collision_start_hit_VO` | `Play_Gerbal_part_collision_hit_VO`, `Play_Gerbal_Part_collision_start_hit_VO` |
| `Play_A_explosion_Kerbal` | `Play_A_explosion_Gerbal` |
| `Play_amb_vessel_emitter_Vessel_kerbal` (+ `_Stop`) | `Play_amb_vessel_emitter_Vessel_gerbal` (+ `_Stop`) |

Events the bank does not define keep their stock sound. `audioRemap` in the same JSON holds
explicit exceptions (stock name -> mod name) if a different name is ever needed.

## HumbleSpaceProgram_narration.bnk (generated, do not edit by hand)

The English narration lines that say "Kerbal", re-cut so the narrator says "Gerbal"
(`docs/audio-events.md`, "Narration pipeline"). One event per stock line, `Play_Gerbal_VO_<stock
event id>`, embedded PCM, routed to the stock voice bus 1459302360 at -6 dB with the stock initial
delay. `assets/data/narration_remap.json` maps the stock event ids to these. Regenerate with:

```powershell
tools\venv\Scripts\python tools\vo_gerbal.py all        # events, transcribe, edit, bank
tools\venv\Scripts\python tools\vo_gerbal.py edit --verify   # re-check what a transcriber hears
```

## Sound design checklist (for the future SFX/voice bank)

Derived from the stock kerbal bank (`kerbal_sfx_events.bnk`: 53 events, 767 sound objects, 348 media
files) and the voice bank (`u_Kerbal_voice_media.bnk`, 115 files):

- Footsteps: normal, soft, run, land, ladder step (surface variation is handled by Wwise switches in stock; start simple).
- Body: jump start, get up (start, push), clap, swim stroke, swim stroke idle.
- Suit: helmet adjust (normal, low), gear adjust 01 to 13, jetpack open/close (+ end), jetpack button.
- Flag plant: 02 pull, 03, 04, 05 unpack, 06, 07, 08 down, 09 impact.
- Voice: yawn, collision hit, collision start hit, explosion, plus the idle/emote chatter set that the
  stock game drives through the `kerbal_voice_selection` (int 0 to 10) and `kerbal_voice_type`
  (float 0 to 2) RTPCs. Model the human voice bank with the same two RTPCs so the per-astronaut
  voice attributes keep working.
