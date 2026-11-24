# The stand: what it does and where it stops

`lab404/stand.py` runs real firmware code on Unicorn, an emulated Cortex-M core, starting from the memory the scatter table produces.
A pass means the code did this on the emulator. It never means it works on a unit.

## Modelled

| What | How | Test |
|---|---|---|
| Startup memory | Scatter rows applied in order, zeroed regions included | `test_stand`, `test_review_findings` |
| Function calls | AAPCS call, stack and callee-saved registers checked on return | `test_stand` |
| Unmodelled memory | The run stops with `Boundary` and names the address | `test_stand` |
| Budget | Bounded by instruction count, never by clock time | `test_stand` |
| Stubs | Replace a firmware function on purpose, each call is logged, and the report lists them | `test_stand` |
| Bit-exact comparison | Same inputs on base and candidate | `test_demo_mod` |

## Not modelled

| What | Consequence | Where it can be checked |
|---|---|---|
| Timing, cycles, caches, SDRAM | Instruction counts are not cycles. Arm publishes no cycle tables [DOC] | Unit only |
| Peripherals | Reads of unknown registers stop the run | Later stages, unit |
| Interrupts and the RTOS | Unicorn has no interrupt controller. Task switching and preemption do not happen | Whole firmware level below |
| Second processor (BMC/DSP) | Its code is encrypted, so effects cannot run | Unit only |
| FAT and SD | Not modelled yet | Later stages, unit |

## Whole firmware: `lab404/emulator.py`

Unicorn runs pieces of code exactly. For everything that needs a booted unit there is a second level: the separate DM-404 project, a QEMU machine with device
models, interrupts and the firmware's RTOS. `tools/setup_dm404.sh` builds it outside this repository. Each run uses a temporary flash and an overlay on a blank drive. The build script and the emulator link (unix sockets) are for Linux. On Windows use WSL: clone the repository inside WSL and run everything there. On macOS it has not been tried.

| Checked by a named test in `tests/test_emulator.py` [EMULATOR] | Test |
|---|---|
| Stock 5.52 boots to its main screen, and audio blocks flow | `test_stock_boots_and_keys_work` |
| Real keys change real screens, and EXIT returns | `test_stock_boots_and_keys_work` |
| A candidate matches its base screen for screen, on stock and DOOM OS 0.7.3 | `test_candidate_matches_its_base_screen_for_screen` |
| A hook fires in the running firmware, called by its own event code | `test_a_hook_fires_in_the_running_firmware` |
| DOOM OS opens with REMAIN + SUB PAD and differs from stock | `test_doom_opens_its_own_screen_and_stock_does_not` |
| With a project: pads sound, a hook in the voice renderer fires, and pad peaks match the base | `test_a_hook_in_the_voice_renderer_fires_and_pads_sound_the_same` |
| The mixer helper `0x15FEE` is not called when pads play ordinarily | `test_the_mixer_helper_is_not_on_the_ordinary_pad_path` |
| A boot is ready only on the main screen, also under load | `test_ready_means_the_main_screen_even_under_load` |
| Each route to a screen arrives on its page | `test_every_route_arrives` |
| Recorded key verdicts still hold, on a sample of each kind | `test_recorded_verdicts_still_hold` |
| A whole task from APP1 to package, on stock and DOOM OS | `test_a_whole_task_from_app1_to_package_on_two_bases` |
| The comparison catches a mod that changes an existing key | `test_replay_catches_a_mod_that_changes_something_existing` |
| The comparison catches a chord firing on screens it was not declared for | `test_replay_catches_a_chord_that_also_fires_on_screens_it_was_not_declared_for` |
| On DOOM OS, its own screen keeps those keys | `test_on_doom_os_its_own_screen_keeps_the_keys` |

Limits of this level:
- Audio tests need a drive image holding a project, `inputs/project-drive.img`, made by the user from their own project. Without it they skip. Peaks are a coarse comparison, not bit for bit.
- DM-404 stands in for the second processor, so effects are not Roland's sound.
- Its timing is not the unit's.
- Its device models are another project's work. A behaviour seen here and not on a unit stays unproven.

### A debugger on the whole firmware

`Emulator(..., extra_args=[...])` passes arguments to QEMU, so its gdb stub can be opened on a unix socket:
`extra_args=['-gdb', 'unix:PATH,server=on,wait=off']`, then `gdb` with `set architecture arm` and `target remote PATH`.
In the development sandbox a TCP stub (`-s`) could not be reached; the unix socket could. Hardware breakpoints and read and
write watchpoints work. `bt` stops early without symbols: read `$lr` and look on the stack for odd `0x80xxxxxx` words. A
gdb-python breakpoint whose `stop()` returns False counts calls without stopping. Found in use on 2026-11-14; no test here
covers it.

## Key bindings on the emulator

`python -m lab404 sweep` presses each recorded binding on a fresh boot, and `record-sweep` writes the outcome to `knowledge/observations/<firmware>.json`.
Import requires a log for a known image matching the selected profile and the current binding definitions. Changes to generated evidence citations leave the definition fingerprint unchanged.

| Verdict | Meaning |
|---|---|
| `confirmed` | A sign declared in advance appeared: the expected page, the key's own light, or sound. A page or light still shows only that the firmware responded as described, on this emulator. |
| `reacted` | Something changed and no control explains it. What it means is not proven. |
| `no-reaction` | Nothing attributable was seen. No evidence either way: the action may need a condition the run lacked, such as a sample playing or a loaded deck. |
| `unobserved` | The run or its control lacked a confirmed screen or stable starting state, or could not be compared. |
| `contradicted` | A different page appeared than the one declared. Needs a person or agent to look. |

Only `confirmed` and `reacted` become `[EMULATOR]` evidence. A verdict depends on the project on the drive. It never makes a key `free`: that takes a screen marked complete.

Stock 5.52 result, 2026-11-09: 784 bindings tried, 3 not tried (two skip-back keys need recorded audio, one needs power-on). Of 120 repeated at random, 119 verdicts matched and all 120 final pages matched. Only about a fifth of bindings have a declared sign at all, so most can reach `reacted` at best.

The published stock results now classify 47 more entries as `unobserved`. The original logs lacked a stable, confirmed starting state for the input or its control.

Limits: `RESAMPLE`'s page was declared wrongly, then corrected after the run and checked by eye. PAD5 and PAD8 of the project on this drive showed no sound though the screen shows samples there; the cause is unknown.

## Which level to use

| Question | Level |
|---|---|
| Does this code compute exactly the right samples? Registers, stack, memory | Unicorn, `lab404/stand.py` |
| Do screens, keys, tasks and boot behave? Does a mod disturb them? | DM-404, `lab404/emulator.py` |
| Timing, sound of effects, real SD cards, hardware faults | The unit, by the user |

## Earlier experiment: Unicorn from reset (2026-11-09)

Running the firmware from reset on Unicorn with peripherals as plain memory reached an error trap at `0x800022C8`, caused by the assumed register values. Unicorn has no
interrupt controller, which is why the whole-firmware level uses DM-404.
