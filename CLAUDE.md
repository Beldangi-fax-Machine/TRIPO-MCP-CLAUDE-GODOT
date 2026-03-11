# CLAUDE.md — Tripo MCP + Godot Integration Guide

This project is an MCP server that gives you (Claude) access to the Tripo AI 3D generation API. You can generate 3D models, rig them, animate them, stylize them, convert formats, and create Godot scene files — all through MCP tool calls.

## How to Map User Requests to Tools

Users will ask for 3D assets in casual language. Here's how to translate what they say into the right tool calls.

### "Generate me a ___" / "Make me a ___" / "Create a ___"

When someone asks you to **make, generate, or create** a 3D model from a description:

- **If they mention animations** (e.g., "make me a knight that can walk and fight"):
  → Use `generate_and_animate`. Set `animations` based on what they describe.
  - "walk and fight" → `["walk", "idle", "slash"]`
  - "moving around" → `["idle", "walk", "run"]`
  - "dancing" → `["dance_01", "dance_02", "dance_03"]`
  - "combat" → `["idle", "slash", "shoot", "hurt"]`

- **If they just want a static model** (e.g., "make me a treasure chest"):
  → Use `generate_3d_model`.

- **If they provide an image** (e.g., "turn this picture into a 3D model"):
  → Use `image_to_3d_model`. The `image_path` must be the absolute path to the file.

### "Animate ___" / "Rig ___" / "Make it move"

When someone wants to add animation to an **existing** model:

1. First call `rig_3d_model` with the model's `task_id` (ask if you don't have it).
2. Then call `animate_3d_model` with both the original `task_id` and the `rig_task_id`.

Common animation mappings from casual language:
| User says | Animations to use |
|-----------|-------------------|
| "make it walk" / "walking" | `["idle", "walk"]` |
| "running and jumping" | `["run", "jump"]` |
| "fighting" / "combat" / "attack" | `["idle", "slash", "hurt"]` |
| "shooting" / "ranged" | `["idle", "shoot"]` |
| "dancing" | `["dance_01", "dance_02", "dance_03"]` |
| "waving" / "greeting" | `["idle", "wave"]` |
| "all the basics" / "standard" | `["idle", "walk", "run", "jump"]` |
| "everything" / "full set" | `["idle", "walk", "run", "jump", "slash", "shoot", "hurt", "fall"]` |
| "NPC" / "townsperson" | `["idle", "walk", "wave", "agree", "bow"]` |
| "enemy" / "monster" | `["idle", "walk", "run", "slash", "hurt", "fall"]` |
| "player character" | `["idle", "walk", "run", "jump", "slash", "shoot", "hurt", "fall", "climb"]` |
| "sports" | `["idle", "run", "basketball_shot", "crossover_dribble"]` |
| "scared" / "emotional" | `["idle", "afraid", "cry", "angry_01"]` |
| "magic" / "wizard" / "casting" | `["idle", "cast_a_spell", "walk"]` |
| "sitting" / "resting" | `["idle", "sit"]` |

### "Make it look like ___" / "Style it as ___" / "Stylize"

When someone wants to change the visual style:
→ Use `stylize_3d_model`.

| User says | Style parameter |
|-----------|----------------|
| "lego" / "brick" / "block" | `lego` |
| "voxel" / "blocky" / "pixel art" | `voxel` |
| "minecraft" / "cube" | `minecraft` |
| "cartoon" / "cartoony" / "toon" | `cartoon` |
| "clay" / "claymation" / "plasticine" | `clay` |
| "alien" / "organic" / "otherworldly" | `alien` |
| "christmas" / "holiday" / "festive" | `christmas` |
| "steampunk" / "mechanical" / "victorian" | `steampunk` |
| "gold" / "golden" / "metallic gold" | `gold` |
| "bronze" / "statue" / "ancient" | `ancient_bronze` |
| "voronoi" / "cellular" / "organic pattern" | `voronoi` |

### "Convert to ___" / "Export as ___" / "Save as FBX"

When someone wants a format change:
→ Use `convert_3d_model`.

| User says | Format parameter |
|-----------|-----------------|
| "fbx" / "for unity" / "for unreal" / "for blender" | `fbx` |
| "obj" | `obj` |
| "for AR" / "usdz" / "for apple" / "for iphone" | `usdz` |
| "for 3d printing" / "stl" | `stl` |
| "3mf" | `3mf` |
| "glb" / "gltf" / "for web" / "for godot" | `glb` |

If they mention **poly count** or **low poly** or **mobile ready**, set `face_limit`:
- "low poly" → `face_limit: 3000`
- "mobile" / "mobile ready" → `face_limit: 5000`
- "medium poly" → `face_limit: 10000`
- "high poly" / "detailed" → leave unset (adaptive)

### "Better texture" / "Retexture" / "Change the skin"

→ Use `texture_3d_model`. Pass any description as `prompt`.

### "Improve it" / "Make it higher quality" / "Refine"

→ Use `refine_3d_model` with the model's `draft_task_id`.

### "Put it in my Godot scene" / "Add to scene" / "Place it at ___"

→ Use `create_godot_scene`. Parse position from what they say:
- "at the origin" → `[0, 0, 0]`
- "at position 5, 0, 3" → `[5, 0, 3]`
- "in the center" → `[0, 0, 0]`
- "to the right" → `[3, 0, 0]`

### "How many credits" / "Balance" / "How much do I have left"

→ Use `check_tripo_balance`.

### "What can you do" / "What animations are available" / "List options"

→ Use `list_tripo_options`.

### "Is it done" / "Check on it" / "What's the status"

→ Use `check_task_status` with the task ID.

## Output Directory Rules

- Default output goes to `./models/`
- If the user mentions a Godot project path like `res://assets/enemies/`, translate it to a real filesystem path. `res://` is the Godot project root — find the project root by looking for `project.godot` in parent directories.
- If they say "save to my project" or "put it in assets", use `./assets/models/` or look for an existing assets directory.
- Always create parent directories automatically (the server handles this).

## Chaining Tools

Many requests require **multiple tool calls in sequence**. Common chains:

1. **"Make an animated character"**
   → `generate_and_animate` (does it all in one call)

2. **"Make a character, stylize it as lego, and export as FBX"**
   → `generate_3d_model` → `stylize_3d_model` → `convert_3d_model`

3. **"Turn this image into an animated model for my Godot game"**
   → `image_to_3d_model` → `rig_3d_model` → `animate_3d_model` → `create_godot_scene`

4. **"Generate a prop and make it low poly for mobile"**
   → `generate_3d_model` → `convert_3d_model` with `face_limit`

5. **"Make a character with different style variants"**
   → `generate_3d_model` → `stylize_3d_model` (lego) → `stylize_3d_model` (cartoon) → etc.

Always save the `task_id` from each step — you need it for the next tool in the chain.

## Quality Tips to Share with Users

- For characters that will be animated, always include `idle` in the animation list
- `mixamo` rig spec has wider ecosystem compatibility; `tripo` is Tripo's native format
- Use `v3.0-20250812` with `geometry_quality: "detailed"` for hero characters
- Use `Turbo-v1.0-20250506` for quick iteration and prototyping
- For Godot specifically, GLB is the best format — it imports natively
- Suggest `generate_and_animate` over separate calls when the user wants a complete character

## Task IDs Are Important

Every Tripo operation returns a `task_id`. Always report these to the user and remember them for follow-up operations. If the user asks to modify a previously generated model, you need its `task_id`.
