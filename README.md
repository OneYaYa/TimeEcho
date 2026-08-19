# TIME ECHO / 时间回响

[简体中文](README.zh-CN.md) | **English**

TIME ECHO is a pixel-art time-loop exploration game. Active development targets Godot 4.6; the older browser version is an unmaintained early draft. Please use the Godot project for testing.

## Launch

The legacy HTML draft can be served from PowerShell:

```powershell
python server.py
```

Then open <http://127.0.0.1:8000>. Do not open `index.html` directly because browsers will block its module and JSON requests.

## Godot 4.6 Version

The complete Godot project is in [`godot/`](godot/), with `godot/scenes/main/main.tscn` as the main scene. Open `godot/project.godot` in Godot 4.6 or run:

```powershell
& "C:\path\to\godot.exe" --path .\godot
```

The Godot version preserves the JSON data, 18 locations, seven NPCs, time loop, puzzles, deterministic local AI fallback, and save semantics, while migrating the `art/` assets.

- [Migration report](godot/MIGRATION_REPORT.md)
- [Migration analysis](godot/MIGRATION_ANALYSIS.md)
- [18-map render gallery](godot/MAP_RENDER_GALLERY.md)
- [Test checklist](godot/TEST_CHECKLIST.md)
- [AI NPC technical upgrade](godot/docs/AI_NPC_TECH_UPGRADE.md)

Automated checks:

```powershell
godot --headless --path godot --editor --quit
godot --headless --path godot res://tests/test_runner.tscn
python godot/tests/validate_project.py
```

## Controls

- `WASD` / arrow keys: move
- `Shift`: sprint
- `E`: interact with residents, objects, doors, and roads
- `J`: open the repair log that persists across loops
- During free-form dialogue, game time runs at one-quarter speed
- In the low-tide cave and hidden darkroom, game time pauses

Each loop runs from Saturday 06:00 to Sunday 06:00 and lasts about 12 real-world minutes. The white-light reset sequence begins at 05:55.

## Playable Content

- An English title screen and a standalone employer prologue
- Six scrolling public scenes: Lakeside Inn Yard, Clockshadow Square, Chapel Hill, Silver-Salt Lane, Archive Slope, and Returning-Tide Harbor
- More than ten interiors and hidden spaces, including the inn, Room Eight, clock service cabin and basement, chapel tower, photography studio, archives, harbor control room, and low-tide cave
- Three distinct repair puzzles: gear swapping/calibration, a six-hammer escapement, and a three-ring tidal dial
- A three-step cave-negative development puzzle and four-anchor identity fixing
- Seven residents with occupational locations, evening routines, movement, portraits, and six-frame walk/sprint animation
- Optimized transparent WebP scene art with procedural fallbacks for buildings, furniture, props, and boats
- Original procedural ambience, footsteps, bells, and light pentatonic music for individual scenes
- A cinematic lake-town panorama for loop resets and both endings
- A cross-loop journal and retained photographs, while physical objects reset each loop
- A surface ending and a true ending

## Dialogue and Evidence Boundaries

Free input supports open expression, while fixed actions define verifiable changes. Natural language can only enter the same locally validated state-change path when the relevant action is already available and the model explicitly selects it.

1. An NPC only receives public facts allowed by their current state.
2. Mentioning `Ada Rowan`, Room Seven, or the seventh witness early does not unlock that knowledge.
3. NPC actions require the physical items, records, identity evidence, and responsibility conditions for the current loop.
4. The cross-loop journal represents player memory and never pretends that an NPC investigated the same evidence this loop.
5. The model returns a strict JSON Schema result through the Responses API and can only choose allowlisted actions; local rules remain authoritative.
6. Ada must personally verify her name, residence, duty, and face in frozen time, one fixed evidence action at a time.

Without a configured model, all seven residents use handcrafted local dialogue rules and the full story remains playable.

### Godot AI NPC v2

The Godot version uses a dedicated context compiler rather than concatenating character cards with world state. Each turn projects only canonical facts the current NPC may know, shared evidence from the current loop, subjective memory, relationship state, scene mode, and director intent with TTL/cooldown fields. Character-writing rules are separated from secret knowledge.

Natural-language understanding may propose a story action whose hard prerequisites are already satisfied, but it cannot change state. `DialogueManager` validates the action allowlist again against the latest world snapshot before local rules commit it. A post-generation quality gate removes unsupported communication failures, restores high-confidence facts that the model evaded, and rejects dialogue that contradicts its own citations. Recent turns retain local trace data with fact IDs, memory IDs, token estimates, trimming reasons, and `quality_guard` results.

Ordinary conversations and subjective memories belong to the current loop and are cleared by the white-light reset. Player notes, learned knowledge, and intentionally persistent photographs survive.

## Terminal AI-NPC Lab

Test NPCs without launching the game:

```powershell
python tools/npc_terminal.py
```

Inspect the exact context for a story stage without calling OpenAI:

```powershell
python tools/npc_terminal.py --dry-run --npc dorothea --preset records
python tools/npc_terminal.py --dry-run --npc ada --preset darkroom --once "Do you remember your name?"
```

Use `/npc` to choose among seven NPCs, `/preset` for curated story stages, and `/item`, `/evidence`, `/repair`, `/flag`, `/knowledge`, `/photo`, or `/time` to edit test state. `/state`, `/facts`, and `/context` expose the world and next request. Enter `/help` for all commands.

Items, evidence, and mechanism flags remain in local state; context is projected separately for each NPC immediately before dialogue. Irreversible actions require both world prerequisites and a matching current-turn trigger. The model cannot rewrite action effects, inventory, evidence, or story flags.

## Model Configuration

Copy `.env.example` to `.env` and configure the server-side variables:

```env
OPENAI_API_KEY=your-key
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-5.6-luna
OPENAI_REASONING_EFFORT=low
```

The browser never reads the API key. `server.py` uses the OpenAI Responses API with `store: false` and strict structured output, exposing only non-sensitive status such as whether AI is configured and which model is active. Legacy `LLM_*` names remain compatible, but new deployments should prefer `OPENAI_*`.

## Story Routes

Surface ending:

```text
Repair all three clocks
  → read the three external protocols in the basement
  → confirm the lighthouse → chapel → square light path with Conrad
  → have Arthur stop the clock through the emergency interface
  → have Beatrice complete the seventh strike with the silver tuning fork
  → pull the red delete lever
  → Sunday arrives, and Ada's shared record disappears
```

Seven-person continuation:

```text
Tidal clock → 02:00 low-tide cave → old negative → three-step development
Main-clock A.R. record + belfry A.R. record + damaged portrait → restore name/duty
Room Seven key tag + gap in the inn ledger → restore residence
Stop main clock + illuminate west wall from two routes + unnumbered key → second darkroom
Verify Ada's name + residence + duty + face one by one → fix the portrait
Place it in the basement's seventh-witness position → press the white Continue knob
```

## Project Structure

```text
timeecho/
├─ data/world.json            # Characters, items, evidence, and loop configuration
├─ data/maps.json             # Locations, terrain, furniture, and interaction points
├─ js/simulation.js           # Loop rules, knowledge/items, NPC actions, endings
├─ js/game.js                 # Input, movement, travel, interaction, saves, main loop
├─ js/renderer.js             # Camera, collision, animation, pixel-scene rendering
├─ js/ui.js                   # Title, journal, dialogue, puzzles, reset/endings
├─ js/ai.js                   # Browser-side dialogue and local fallback
├─ art/runtime/               # Optimized WebP assets and cinematic panoramas
├─ tools/build_runtime_art.py # Rebuild runtime assets from art sources
├─ tools/npc_terminal.py      # Editable terminal dialogue lab
├─ server.py                  # Static server and optional same-origin model proxy
└─ my_script.doc              # Original story script
```

`my_script.doc` is the fixed story source and is not modified by the current implementation work. Replacing or adding source art under `art/` can be followed by `python tools/build_runtime_art.py` to regenerate runtime WebP assets.
