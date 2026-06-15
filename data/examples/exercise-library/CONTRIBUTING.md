# Exercise Library Contributing Guide

Each exercise is a `.md` file in the appropriate category subdirectory.

## Directory layout

```
exercise-library/
├── strength-push/   # horizontal and vertical pushing movements
├── strength-pull/   # horizontal and vertical pulling movements
├── strength-lower/  # squat, hinge, and single-leg movements
├── cardio/          # steady-state aerobic work
├── hiit/            # high-intensity intervals and complexes
└── mobility/        # stretching, activation, and recovery flows
```

## File format

```markdown
---
name: Floor Press
equipment: [barbell, bumper_plates]
muscles: [chest, triceps, shoulders]
type: strength-push
difficulty: intermediate
---
## Sets / Reps
- Strength: 4x3-5 @ 80-90% 1RM
- Hypertrophy: 3x8-12 @ 65-75% 1RM

## Cues
Keep elbows at 45°. Full stop at the floor. Drive through the bar.

## Progressions
- Beginner: 3x8 @ empty bar
- Advanced: 5x3 @ 90% 1RM with 3-min rest

## Notes
No bench required. Safer shoulder path than bench press.
```

## Equipment tags

Tags must exactly match the normalized form of `available_equipment` in your `config.toml`
(lowercase, spaces and hyphens replaced with underscores). Common tags:

| Config value        | Tag to use in front matter |
|---------------------|---------------------------|
| `barbell`           | `barbell`                 |
| `bumper plates`     | `bumper_plates`           |
| `pull-up bar`       | `pull_up_bar`             |
| `dumbbells`         | `dumbbells`               |
| `rings`             | `rings`                   |
| `kettlebell`        | `kettlebell`              |
| `resistance band`   | `resistance_band`         |

**AND-semantics:** ALL tags listed in an exercise file's `equipment` field must be present
in the user's `available_equipment`. An exercise requiring `[barbell, bumper_plates]`
will not appear for a user who only has `[barbell]`.

For bodyweight exercises that need no equipment, use `equipment: []`.

## Sampler behavior

- One exercise per category is sampled each week.
- The seed is the ISO week number, so the same week always produces the same selection.
- Different weeks rotate to different exercises automatically.
- Adding new files distributes evenly across future weeks.
