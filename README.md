# Tripo AI MCP Server for Claude Code + Godot

An MCP (Model Context Protocol) server that gives Claude full access to the [Tripo AI](https://www.tripo3d.ai/) 3D generation API. Generate 3D models, rig them, animate them, stylize them, and drop game-ready `.glb` files straight into your Godot project — all through natural language.

## What It Does

Tell Claude what you need in plain English and it handles the entire pipeline:

```
"Generate an animated goblin with idle, walk, and slash animations for my RPG"

"Turn this concept art into a 3D model and save it to my Godot project"

"Make a lego-style version of my character model"

"Convert my model to FBX with 5000 faces for mobile optimization"
```

## Features

| Capability | Tool | Description |
|-----------|------|-------------|
| **Text to 3D** | `generate_3d_model` | Generate a 3D model from a text description |
| **Image to 3D** | `image_to_3d_model` | Generate a 3D model from a reference image (PNG/JPG/WEBP) |
| **Rigging** | `rig_3d_model` | Add a skeleton to any generated model (Mixamo or Tripo spec) |
| **Animation** | `animate_3d_model` | Apply preset animations to a rigged model |
| **Full Pipeline** | `generate_and_animate` | Text to animated character in one call |
| **Stylization** | `stylize_3d_model` | Apply visual styles (lego, voxel, cartoon, clay, etc.) |
| **Conversion** | `convert_3d_model` | Convert format (GLB, FBX, USDZ, OBJ, STL, 3MF) with poly control |
| **Texturing** | `texture_3d_model` | Generate or regenerate textures with text prompts |
| **Refinement** | `refine_3d_model` | Upgrade a draft model to higher quality |
| **Godot Scene** | `create_godot_scene` | Generate a `.tscn` file that instances your model |
| **Task Status** | `check_task_status` | Check progress of any Tripo task |
| **Balance** | `check_tripo_balance` | Check remaining API credits |
| **Options** | `list_tripo_options` | List all available animations, styles, formats |

## Setup

### 1. Install dependencies

```bash
pip install mcp httpx
```

Or use the requirements file:

```bash
pip install -r requirements.txt
```

### 2. Get your Tripo API key

1. Go to [platform.tripo3d.ai](https://platform.tripo3d.ai)
2. Sign in and navigate to **API Keys**
3. Create a new key and copy it (shown only once)

### 3. Add to Claude Code

Add to your Claude Code MCP configuration (`~/.claude.json` or project-level `.mcp.json`):

```json
{
  "mcpServers": {
    "tripo": {
      "command": "python3",
      "args": ["/absolute/path/to/TRIPO-MCP-CLAUDE-GODOT/server.py"],
      "env": {
        "TRIPO_API_KEY": "tsk_your_key_here"
      }
    }
  }
}
```

> **Important:** Use the absolute path to `server.py`.

### 4. Restart Claude Code

The `tripo-godot-mcp` server will appear in your available MCP tools.

## Available Preset Animations

### Locomotion
| Animation | Description |
|-----------|-------------|
| `idle` | Standing idle loop |
| `walk` | Walk cycle |
| `run` | Run cycle |
| `jump` | Jump motion |
| `climb` | Climbing motion |
| `fall` | Falling motion |
| `turn` | Turning in place |

### Combat
| Animation | Description |
|-----------|-------------|
| `slash` | Melee attack swing |
| `shoot` | Ranged attack |
| `chop` | Chopping motion |
| `cast_a_spell` | Magic casting |
| `box_01` / `box_02` / `box_03` | Boxing combos |

### Reactions & Emotions
| Animation | Description |
|-----------|-------------|
| `hurt` | Hit reaction |
| `afraid` | Fear reaction |
| `angry_01` / `angry_02` / `angry_03` | Anger variations |
| `cry` | Crying |
| `complain_01` / `complain_02` | Complaining |

### Social & Gestures
| Animation | Description |
|-----------|-------------|
| `agree` | Nodding agreement |
| `bow` | Bowing |
| `clap` | Clapping |
| `cheer` | Cheering |
| `wave` | Waving |

### Dance
| Animation | Description |
|-----------|-------------|
| `dance_01` through `dance_06` | Six dance styles |

### Sports
| Animation | Description |
|-----------|-------------|
| `basketball_shot` | Basketball shot |
| `crossover_dribble` | Crossover dribble |

## Available Styles

| Style | Description |
|-------|-------------|
| `lego` | Brick-built appearance |
| `voxel` | Blocky voxel aesthetic |
| `voronoi` | Organic cellular pattern |
| `minecraft` | Minecraft-style blocks |
| `cartoon` | Bright colors, exaggerated proportions |
| `clay` | Handmade clay/dough look |
| `alien` | Organic otherworldly aesthetic |
| `christmas` | Festive holiday theme |
| `steampunk` | Victorian mechanical style |
| `gold` | Metallic gold finish |
| `ancient_bronze` | Aged bronze statue look |

## Output Formats

| Format | Best For |
|--------|----------|
| `glb` | Godot, web viewers (default) |
| `fbx` | Unity, Unreal, Blender |
| `usdz` | Apple AR, USD pipelines |
| `obj` | Broad compatibility |
| `stl` | 3D printing |
| `3mf` | Advanced 3D printing |

## Rig Specifications

- **`mixamo`** — Adobe Mixamo-compatible skeleton (wider animation ecosystem)
- **`tripo`** — Tripo native skeleton

## Godot Integration Guide

### Importing Models

1. Generated `.glb` files import natively — drag them into Godot's FileSystem dock
2. Godot auto-detects embedded animations in the `.glb`
3. Use **AnimationPlayer** to play individual animations
4. Use **AnimationTree** for blending and state machines

### Using Generated Scenes

The `create_godot_scene` tool generates `.tscn` files you can open directly in Godot. The scene instances your `.glb` model at the specified position.

### Recommended Import Settings

- Set **Import > Meshes > Generate LODs** to `off` for character models
- Tripo outputs use meters — scale in the Import tab if your project uses different units
- For animated models, check that **Import > Animation > Import** is enabled

### Typical Workflow

```
1. "Generate an animated knight with idle, walk, run, and slash animations"
   → Claude generates, rigs, and animates the model via Tripo
   → Downloads the .glb to your project's models/ directory

2. "Create a Godot scene with the knight at position (5, 0, 3)"
   → Claude generates a .tscn file referencing the .glb

3. "Convert the knight to FBX with 8000 faces for mobile"
   → Claude converts with poly reduction

4. "Make a lego version of the knight"
   → Claude stylizes the model
```

## Example Prompts

### Characters
```
Generate an animated skeleton warrior with idle, walk, and slash animations.
Save it to ./game/assets/enemies/

Create a friendly NPC shopkeeper with idle and wave animations.

Turn this image into a 3D character and rig it with Mixamo skeleton.
```

### Props and Environment
```
Generate a treasure chest 3D model and save to ./game/assets/props/

Create 3 different rock formations for my cave level.

Generate a medieval sword prop and convert it to FBX with 2000 faces.
```

### Stylization
```
Take the goblin model and make a cartoon version of it.

Stylize my character as voxel art for the retro game mode.

Create a gold trophy version of the player character.
```

### Pipeline
```
Generate a dragon enemy. Rig it, animate with idle and slash,
then convert to FBX. Make a lego version too.
Save everything to ./game/assets/enemies/dragon/
```

## Model Versions

| Version | Notes |
|---------|-------|
| `v2.5-20250123` | Balanced quality and speed, enhanced geometry (default) |
| `v3.0-20250812` | Latest. Crisper edges, sharper surfaces. Supports `geometry_quality: "detailed"` for up to 2M polys |
| `Turbo-v1.0-20250506` | Fastest generation, good for rapid iteration |
| `v2.0-20240919` | Industry-leading geometry with PBR |
| `default` | Latest stable version |

## Project Structure

```
TRIPO-MCP-CLAUDE-GODOT/
├── server.py               # MCP server (all Tripo tools)
├── requirements.txt        # Python dependencies
├── claude_code_config.json # Example MCP config
├── .gitignore
└── README.md
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `TRIPO_API_KEY not set` | Set the env var in your MCP config or shell |
| Task timeout | Increase timeout; complex models take longer |
| No model URL in result | Check `check_task_status` — the task may have failed |
| Godot can't import `.glb` | Ensure Godot 4.x; check the file downloaded correctly |
| Animation not playing | Check AnimationPlayer node; animations are embedded in the `.glb` |
| Model too large/small | Use `convert_3d_model` with `scale_factor` or adjust in Godot Import tab |

## Credits & Links

- [Tripo AI Platform](https://platform.tripo3d.ai)
- [Tripo API Docs](https://platform.tripo3d.ai/docs)
- [Godot Engine](https://godotengine.org)
- [MCP Specification](https://modelcontextprotocol.io)
