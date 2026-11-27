# Audio Message and Queue Specification

This document is the source of truth for spoken messages in the interface.
It defines the message model and queue behavior independently of the speech
backend or the generated-audio implementation.

## Goals

- Speak complete, meaningful messages rather than assembling fragments at
  playback time.
- Keep messages reusable by giving them stable semantic IDs that do not depend
  on the call site.
- Prefer the newest information when transient state changes quickly.
- Ensure every distinct error is eventually spoken.
- Keep lens-specific queue policy out of individual lenses.

## Message model

Every request to the audio system represents one complete utterance.

| Field | Meaning |
| --- | --- |
| `id` | Stable semantic identifier for the message. It is not a location or event timestamp. |
| `text` | The complete text of the utterance. It is never assembled from separate title, label, or instruction fragments at playback time. |
| `type` | One of `LensEntry`, `MenuOption`, `Instruction`, or `Error`. |
| `lens_id` | The lens that owns the message, when applicable. Used to clear stale non-error messages on lens switches. |
| `error_key` | Required for `Error`; identifies the underlying error for deduplication. |
| `clip_id` | Optional generated-audio asset ID. For a generated clip, the clip must contain exactly the complete `text`. |

The four message types are intentionally small and are the only queue-policy
types for now.

### Examples

| Type | Stable message ID | Complete text |
| --- | --- | --- |
| `LensEntry` | `lens.main_menu.entry` | `Entering Main Menu` |
| `LensEntry` | `lens.quick_menu.entry` | `Entering Quick menu` |
| `LensEntry` | `lens.finger_rays.resume` | `Resuming Finger Rays` |
| `MenuOption` | `menu.option.finger_rays` | `Finger Rays` |
| `Instruction` | `menu.instructions.joystick` | `Move the joystick to slide through menu options. Press the button to select.` |
| `Error` | `compute.stereo.error` | `Stereo camera error: ...` |

Menu options do not include their containing menu. For example, the reusable
option is `Finger Rays`, not `Main Menu. Finger Rays`.

`LensEntry` is used whenever the active spoken context changes: starting a
lens, entering the quick menu, or returning to a lens after the quick menu
closes. Returning uses `Resuming <Lens name>` rather than `Entering <Lens
name>`, but has the same priority and cleanup behavior.

Short standalone words such as `Main` or `Menu` are not message assets. A
short phrase is acceptable when it is itself a complete spoken message, such
as a menu option or a setting value.

## Generated audio and TTS

Known fixed messages may have generated clips. Each generated clip corresponds
to one complete message and has a stable ID. The queue may play multiple clips
in sequence; it does not concatenate audio fragments.

For example, entering Main Menu can enqueue these three independent messages,
in this order:

1. `Entering Main Menu` (`LensEntry`)
2. `Move the joystick to slide through menu options. Press the button to select.` (`Instruction`)
3. `Finger Rays` (`MenuOption`)

Entering the quick menu follows the same pattern, beginning with
`Entering Quick menu`. Closing it without switching lenses begins with
`Resuming <Lens name>`.

Dynamic text, including current values and error details, continues to use
runtime TTS for now. Dynamic TTS requests still follow the same complete
message contract and queue policy.

Settings are the one deliberate exception to the complete-clip rule. A
settings `MenuOption` may contain an atomic sequence of reusable audio parts,
for example:

```text
settings.label.menu_instructions
settings.current_value
settings.value.on
```

The queue treats that sequence as one message for interruption and replacement
purposes. Fixed labels and common finite values use generated clips; dynamic
values such as numbers use TTS for only that part.

## Priority and interruption

| Type | Priority | Interrupts current playback? | Queued-message behavior |
| --- | --- | --- | --- |
| `LensEntry` | High | Yes, any currently playing non-error message, including another `LensEntry` | Removes queued non-error messages made stale by the lens switch, then is placed before queued errors. |
| `MenuOption` | Medium | Yes, any currently playing `MenuOption` or `Instruction` | Removes older queued `MenuOption` messages, then is placed ahead of queued `Instruction`. An interrupted `Instruction` is requeued immediately after the incoming option. |
| `Instruction` | Low | Never | Replaces older queued instructions. It may be removed by a lens switch or explicit queue cleanup. |
| `Error` | Low | Never | Is never removed by ordinary replacement or lens-switch cleanup. Repeated instances are deduplicated. |

An error that is already playing is treated as non-interruptible under the
original error rule. A new `LensEntry` waits for that error to finish, but it
is placed ahead of other queued messages. A new `MenuOption` waits for a
currently playing `LensEntry` or `Error`, but interrupts a currently playing
`Instruction` or `MenuOption`.

Within the same priority, messages retain FIFO order unless a type-specific
replacement rule below says otherwise.

## Queue rules

The queue manager applies these rules atomically for each incoming message.

### LensEntry

1. If a non-error message is playing, stop it immediately.
2. Remove every queued non-error message. This includes older lens entries,
   menu options, and instructions.
3. Keep all queued errors.
4. Add the incoming `LensEntry` before the queued errors.

This is also the cleanup behavior for a lens switch: non-error audio owned by
the previous lens must not leak into the new lens.

### MenuOption

1. If a `MenuOption` or `Instruction` is playing, stop it immediately.
2. Remove all queued `MenuOption` messages.
3. Add the incoming option ahead of queued `Instruction` and ahead of any
   lower-priority non-error messages.
4. If an `Instruction` was stopped, requeue that complete instruction directly
   after the incoming option and before other queued instructions. It will be
   played again from the beginning.
5. Do not interrupt a currently playing `LensEntry` or `Error`.

### Instruction

1. Never interrupt current playback.
2. Replace any other queued instruction automatically.
3. Queue the instruction in FIFO order relative to the remaining instructions.
   An instruction requeued because it was interrupted is placed before newer
   queued instructions.
4. Remove it when a lens switch clears non-error messages, or when an explicit
   future cancellation operation targets it.

### Error

1. Never interrupt current playback.
2. Compute a stable deduplication key from `error_key`.
3. If that key is already pending, playing, or recorded as delivered during
   the current audio-service session, ignore the repeated request.
4. Otherwise, enqueue it and retain it until it is played. No ordinary queue
   replacement or lens-switch cleanup may remove it.

Errors are low priority, so they do not jump in front of already queued higher
priority messages. They remain protected from removal and will eventually be
spoken.

## Canonical scenarios

| Current playback | Queue before | Incoming | Result |
| --- | --- | --- | --- |
| `LensEntry` | `[]` | `MenuOption` | Entry continues; option is queued. |
| `LensEntry` | `[MenuOption(old)]` | `MenuOption(new)` | Entry continues; old option is removed; new option is queued. |
| None | `[MenuOption(old)]` | `MenuOption(new)` | Old option is removed; new option is queued/played. |
| `MenuOption(old)` | `[Instruction]` | `MenuOption(new)` | Old option stops; new option plays before the instructions. |
| `LensEntry(old)` | `[MenuOption, Error]` | `LensEntry(new)` | Old entry stops; menu option is removed; new entry is placed before the error. |
| `Error` | `[MenuOption]` | `LensEntry` | Error continues; menu option is removed; new entry waits immediately after the error. |
| `Instruction(old)` | `[]` | `MenuOption(new)` | Old instruction stops and is requeued; new option plays immediately; the instruction plays again afterward. |
| Any non-error from old lens | `[Instruction(old), Error]` | lens switch | Current non-error stops; queued instruction is removed; error remains. |

## Required invariants

The implementation is correct only if all of these remain true:

1. At most one message is actively playing.
2. A stale queued `MenuOption` is never played after a newer option for the
   same active context has arrived.
3. A new lens never speaks non-error audio owned by the previous lens.
4. A `LensEntry` is never queued behind an ordinary non-error message that it
   supersedes.
5. A new `MenuOption` interrupts a currently playing `Instruction`, but the
   interrupted instruction is requeued and is not lost.
6. A unique error is not lost, replaced, or removed before playback.
7. Repeated requests for the same error key do not create repeated playback.
8. Generated clips and TTS both receive the same complete message text and
   obey the same queue policy.

