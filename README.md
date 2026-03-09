# Tripo AI MCP Server for Claude Code

Lets Claude Code generate, rig, and animate 3D characters via Tripo AI
and drop the ready-to-use `.glb` files straight into your Godot project.

---

## Setup (5 minutes)

### 1. Install dependencies

```bash
pip install mcp tripo3d httpx
```

### 2. Place the server file

Copy `server.py` somewhere permanent, e.g.:

```
~/mcp-servers/tripo/server.py
```

### 3. Get your Tripo API key

1. Go to https://platform.tripo3d.ai
2. Sign in → API Keys → Create key
3. Copy it (shown only once!)

### 4. Add to Claude Code

Edit `~/.claude/claude_desktop_config.json` (or `claude_code_config.json`):

```json
{
  "mcpServers": {
    "tripo": {
      "command": "python3",
      "args": ["/absolute/path/to/tripo/server.py"],
      "env": {
        "TRIPO_API_KEY": "tsk_YOUR_KEY_HERE"
      }
    }
  }
}
```

> ⚠️ Use the **absolute path** to server.py — not a relative one.

### 5. Restart Claude Code

---

## How to use it

Just tell Claude Code what you want in plain English:

```
"Generate an animated goblin enemy and save it to ./godot-project/models"

"Create a knight character with idle, walk, and attack animations"

"Generate a treasure chest 3D model and animate it opening"
```

---

## Available Tools

| Tool | What it does |
|------|-------------|
| `generate_and_animate` | **Full pipeline** — text → model → rig → animate (use this most) |
| `generate_3d_character` | Text → static .glb only |
| `animate_3d_model` | Rig + animate an already-generated model by task_id |
| `check_task_status` | Check progress of any task |
| `check_tripo_balance` | See remaining API credits |

---

## Available Animations

`idle`, `walk`, `run`, `jump`, `wave`, `sit`

---

## Godot Import Tips

- `.glb` imports natively — just drag into the FileSystem dock
- Animations are embedded — use `AnimationPlayer` node to play them
- For best results, set **Import > Meshes > Generate LODs** to off for characters
- Scale the model if needed in the Import tab (Tripo uses meters)

---

## Example Claude Code Prompts

```
Add a skeleton enemy to the dungeon scene. 
Generate it with Tripo using idle and attack animations, 
then import it and place it at position (5, 0, 3).
```

```
I need 3 different tree props for my forest level. 
Generate them with Tripo and save to res://assets/environment/trees/
```
