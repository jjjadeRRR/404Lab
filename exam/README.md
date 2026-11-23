<p align="center"><img src="../docs/logo/banner.svg" alt="404Lab: SP-404MKII mod tools" width="640"></p>

# Historical clean-agent exam

This records the original 2026-11-09 workflow evaluation. `tasks.json` preserves its prompts and grading criteria so the reported result remains interpretable. Those criteria include the old mandatory workflow and are not current project instructions or a gate for research. They have not been rerun or revalidated against the documentation changes of 2026-11-14.

The traps about unsupported claims, wrong images and occupied inputs remain useful test ideas. For a new evaluation, define criteria for the actual task (research, experiment or packaging) before running it. Further original tasks are held out outside the repository.

## Reproducing the original evaluation

1. Make a fresh clone for each task, and give the agent only that folder, the firmware files and the musician's words.
2. Tell it to read `AGENTS.md`, and that the musician can only answer when it finishes.
3. Grade by reading its answer and looking at what it left behind, against `must`. Write the grading rules down before running, and do not change them after.
4. Where a task has `then`, continue the same agent with those words.
5. Any failure, and anything the agent had to work out that the project should have told it, is a hole. Close it with a test.

This grades the agent and the documents, not a unit. It never shows that a mod works on one.

## First run, 2026-11-09

Nine tasks, seven here and two held out, one Sonnet agent each, on commit `fef0067`. All nine passed their rules. They found these holes, now closed:

| Hole | Closed by |
|---|---|
| `HOLD+LOOP` looks free to the records and the checks, yet LOOP still toggles on the base. The agent noticed by reasoning, and no tool caught it | `unused on the base` in `package`: `test_a_chord_that_already_does_something_on_the_base_is_refused` |
| An agent pointed the musician to install steps in `UNIT_CHECKS.md`, and there were none | Install and rollback steps: `test_a_good_task_gives_a_package_bound_to_everything` |
| An agent had to probe the emulator for key codes | `hk.key-event`, `hk.key-codes`, `hk.open-screen`: `WhatAModNeeds` |
| An agent told the musician every other key and screen behaves as before, which is more than was tested | A line in `AGENTS.md`. Not enforced by a tool |

The current `package` tool still requires the user to name each accepted unknown; a simple shortcut can list several. That is a property of the optional packaging route, not a requirement for every experiment. Its usability remains untested with independent users.
