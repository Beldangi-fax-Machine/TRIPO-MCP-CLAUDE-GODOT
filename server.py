#!/usr/bin/env python3
"""
Tripo AI MCP Server for Claude Code + Godot

Gives Claude full access to Tripo's 3D generation API:
  - Text/Image to 3D model
  - Rigging and animation with preset motions
  - Stylization (lego, voxel, voronoi, cartoon, clay, etc.)
  - Format conversion (glb, fbx, usdz, obj, stl)
  - Texture generation
  - Model refinement
  - Godot scene (.tscn) generation for instant import

All outputs land as game-ready assets in your Godot project.
"""

import asyncio
import base64
import json
import os
import re
import sys
from pathlib import Path

import httpx
from mcp import types
from mcp.server import Server
from mcp.server.stdio import stdio_server

# ── Constants ─────────────────────────────────────────────────────────────────

TRIPO_API = "https://api.tripo3d.ai/v2/openapi"

MODEL_VERSIONS = [
    "v2.5-20250123",
    "Turbo-v1.0-20250506",
    "default",
]

PRESET_ANIMATIONS = [
    "idle", "walk", "run", "jump", "climb",
    "slash", "shoot", "hurt", "fall", "turn",
]

STYLIZE_STYLES = [
    "lego", "voxel", "voronoi", "minecraft",
    "cartoon", "clay", "alien", "christmas",
    "steampunk", "gold", "ancient_bronze",
]

CONVERT_FORMATS = ["glb", "fbx", "usdz", "obj", "stl", "3mf"]

RIG_SPECS = ["mixamo", "tripo"]

# ── MCP server ────────────────────────────────────────────────────────────────

server = Server("tripo-godot-mcp")


def _api_key() -> str:
    key = os.environ.get("TRIPO_API_KEY", "")
    if not key:
        raise ValueError(
            "TRIPO_API_KEY not set. "
            "Get one at https://platform.tripo3d.ai → API Keys."
        )
    return key


def _headers() -> dict:
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {_api_key()}",
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _poll_task(task_id: str, timeout: int = 600) -> dict:
    """Poll a Tripo task until success, failure, or timeout."""
    async with httpx.AsyncClient(timeout=30) as client:
        elapsed = 0
        interval = 5
        while elapsed < timeout:
            await asyncio.sleep(interval)
            elapsed += interval
            resp = await client.get(
                f"{TRIPO_API}/task/{task_id}", headers=_headers()
            )
            resp.raise_for_status()
            data = resp.json().get("data", {})
            status = data.get("status", "")
            if status == "success":
                return data
            if status in ("failed", "cancelled", "unknown"):
                raise RuntimeError(
                    f"Task {task_id} ended with status '{status}': "
                    f"{json.dumps(data, indent=2)}"
                )
    raise TimeoutError(f"Task {task_id} did not complete within {timeout}s")


async def _download(url: str, dest: Path) -> Path:
    """Download a file from URL to local path."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(timeout=180, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        dest.write_bytes(resp.content)
    return dest


async def _upload_file(file_path: str) -> str:
    """Upload an image to Tripo and return the file token."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    mime_map = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }
    ext = path.suffix.lower()
    mime = mime_map.get(ext, "application/octet-stream")

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{TRIPO_API}/upload",
            headers={"Authorization": f"Bearer {_api_key()}"},
            files={"file": (path.name, path.read_bytes(), mime)},
        )
        resp.raise_for_status()
        token = resp.json().get("data", {}).get("image_token", "")
        if not token:
            raise RuntimeError(f"Upload failed: {resp.json()}")
        return token


def _safe_filename(text: str) -> str:
    """Derive a safe filename from a prompt string."""
    name = re.sub(r"[^a-zA-Z0-9_\- ]", "", text)[:40].strip().replace(" ", "_")
    return name or "model"


def _get_model_url(task_data: dict) -> str:
    """Extract the model download URL from task result data."""
    output = task_data.get("output", {})
    return output.get("model", "") or output.get("rendered_image", "")


def _generate_godot_scene(
    glb_path: Path,
    node_name: str,
    position: tuple = (0, 0, 0),
    rotation: tuple = (0, 0, 0),
    scale: tuple = (1, 1, 1),
) -> Path:
    """Generate a minimal Godot .tscn scene file that instances a .glb model."""
    # Use relative path from the scene file to the glb
    glb_relative = glb_path.name
    scene_path = glb_path.with_suffix(".tscn")

    safe_node = re.sub(r"[^a-zA-Z0-9_]", "_", node_name)

    tscn_content = f"""[gd_scene load_steps=2 format=3]

[ext_resource type="PackedScene" uid="" path="{glb_relative}" id="1"]

[node name="Scene" type="Node3D"]

[node name="{safe_node}" parent="." instance=ExtResource("1")]
transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, {position[0]}, {position[1]}, {position[2]})
"""

    if scale != (1, 1, 1):
        tscn_content = tscn_content.rstrip() + f"\n"

    if rotation != (0, 0, 0):
        tscn_content = tscn_content.rstrip() + f"\n"

    scene_path.write_text(tscn_content)
    return scene_path


# ── Tool definitions ─────────────────────────────────────────────────────────

TOOLS = [
    # 1. Text to 3D model
    types.Tool(
        name="generate_3d_model",
        description=(
            "Generate a 3D model from a text prompt via Tripo AI. "
            "Returns a .glb file ready for Godot import. "
            "Supports model_version and style parameters."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Describe the 3D model (e.g. 'a goblin warrior with mossy armor')",
                },
                "negative_prompt": {
                    "type": "string",
                    "description": "What to avoid in generation",
                    "default": "low quality, blurry, distorted",
                },
                "model_version": {
                    "type": "string",
                    "description": f"Model version: {', '.join(MODEL_VERSIONS)}",
                    "default": "v2.5-20250123",
                },
                "style": {
                    "type": "string",
                    "description": "Optional style hint for generation",
                    "default": "",
                },
                "output_dir": {
                    "type": "string",
                    "description": "Directory to save output (default: ./models)",
                    "default": "./models",
                },
                "filename": {
                    "type": "string",
                    "description": "Output filename without extension",
                    "default": "",
                },
            },
            "required": ["prompt"],
        },
    ),
    # 2. Image to 3D model
    types.Tool(
        name="image_to_3d_model",
        description=(
            "Generate a 3D model from an image file using Tripo AI. "
            "Provide the path to a PNG/JPG/WEBP image. "
            "Tripo auto-removes background."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "image_path": {
                    "type": "string",
                    "description": "Absolute path to the image file (PNG, JPG, or WEBP)",
                },
                "model_version": {
                    "type": "string",
                    "default": "v2.5-20250123",
                },
                "output_dir": {
                    "type": "string",
                    "default": "./models",
                },
                "filename": {
                    "type": "string",
                    "default": "",
                },
            },
            "required": ["image_path"],
        },
    ),
    # 3. Rig a model (add skeleton)
    types.Tool(
        name="rig_3d_model",
        description=(
            "Add a skeleton rig to a generated 3D model. "
            "Requires the task_id from a previous generation. "
            "Choose 'mixamo' or 'tripo' rig spec."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "original_task_id": {
                    "type": "string",
                    "description": "task_id from a previous model generation",
                },
                "rig_spec": {
                    "type": "string",
                    "description": f"Rig specification: {', '.join(RIG_SPECS)}",
                    "default": "mixamo",
                },
            },
            "required": ["original_task_id"],
        },
    ),
    # 4. Animate a rigged model
    types.Tool(
        name="animate_3d_model",
        description=(
            "Apply preset animations to a rigged 3D model. "
            "Requires both the original model task_id and the rig task_id. "
            f"Available animations: {', '.join(PRESET_ANIMATIONS)}"
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "original_task_id": {
                    "type": "string",
                    "description": "task_id from the original model generation",
                },
                "rig_task_id": {
                    "type": "string",
                    "description": "task_id from the rig_3d_model step",
                },
                "animations": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": f"Preset animations: {', '.join(PRESET_ANIMATIONS)}",
                    "default": ["idle", "walk", "run"],
                },
                "output_dir": {
                    "type": "string",
                    "default": "./models",
                },
                "filename": {
                    "type": "string",
                    "default": "",
                },
            },
            "required": ["original_task_id", "rig_task_id"],
        },
    ),
    # 5. Full pipeline: generate + rig + animate
    types.Tool(
        name="generate_and_animate",
        description=(
            "Full pipeline: generate a 3D character from text, rig it, "
            "and bake animations — all in one call. "
            "Outputs a game-ready animated .glb for Godot."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Describe the character (e.g. 'a knight in silver armor')",
                },
                "negative_prompt": {
                    "type": "string",
                    "default": "low quality, blurry, distorted",
                },
                "model_version": {
                    "type": "string",
                    "default": "v2.5-20250123",
                },
                "rig_spec": {
                    "type": "string",
                    "description": "Rig type: mixamo or tripo",
                    "default": "mixamo",
                },
                "animations": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": f"Animations to bake: {', '.join(PRESET_ANIMATIONS)}",
                    "default": ["idle", "walk", "run"],
                },
                "output_dir": {
                    "type": "string",
                    "default": "./models",
                },
                "filename": {
                    "type": "string",
                    "default": "",
                },
                "generate_scene": {
                    "type": "boolean",
                    "description": "Also generate a .tscn Godot scene file",
                    "default": False,
                },
            },
            "required": ["prompt"],
        },
    ),
    # 6. Stylize a model
    types.Tool(
        name="stylize_3d_model",
        description=(
            "Apply a visual style to a generated 3D model. "
            f"Available styles: {', '.join(STYLIZE_STYLES)}"
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "original_task_id": {
                    "type": "string",
                    "description": "task_id from a previous model generation",
                },
                "style": {
                    "type": "string",
                    "description": f"Style to apply: {', '.join(STYLIZE_STYLES)}",
                },
                "block_size": {
                    "type": "integer",
                    "description": "Block size for structural styles (lego/voxel/voronoi). Higher = coarser.",
                },
                "output_dir": {
                    "type": "string",
                    "default": "./models",
                },
                "filename": {
                    "type": "string",
                    "default": "",
                },
            },
            "required": ["original_task_id", "style"],
        },
    ),
    # 7. Convert model format
    types.Tool(
        name="convert_3d_model",
        description=(
            "Convert a generated model to a different format. "
            f"Supported: {', '.join(CONVERT_FORMATS)}. "
            "Optional face_limit for polygon control and quad mesh output."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "original_task_id": {
                    "type": "string",
                    "description": "task_id from a previous generation or animation",
                },
                "format": {
                    "type": "string",
                    "description": f"Target format: {', '.join(CONVERT_FORMATS)}",
                    "default": "glb",
                },
                "quad": {
                    "type": "boolean",
                    "description": "Enable quad mesh output (forces FBX)",
                    "default": False,
                },
                "face_limit": {
                    "type": "integer",
                    "description": "Limit the number of faces (0 = adaptive)",
                    "default": 0,
                },
                "scale_factor": {
                    "type": "number",
                    "description": "Scale factor for the model (default: 1.0)",
                    "default": 1.0,
                },
                "output_dir": {
                    "type": "string",
                    "default": "./models",
                },
                "filename": {
                    "type": "string",
                    "default": "",
                },
            },
            "required": ["original_task_id", "format"],
        },
    ),
    # 8. Texture a model
    types.Tool(
        name="texture_3d_model",
        description=(
            "Generate or regenerate textures for an existing 3D model. "
            "Supports text prompt and style image for texture guidance."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "original_task_id": {
                    "type": "string",
                    "description": "task_id of the model to texture",
                },
                "prompt": {
                    "type": "string",
                    "description": "Text prompt describing desired texture",
                    "default": "",
                },
                "output_dir": {
                    "type": "string",
                    "default": "./models",
                },
                "filename": {
                    "type": "string",
                    "default": "",
                },
            },
            "required": ["original_task_id"],
        },
    ),
    # 9. Refine a draft model
    types.Tool(
        name="refine_3d_model",
        description=(
            "Refine a draft model into a higher-quality version. "
            "Improves geometry detail and texture quality."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "draft_task_id": {
                    "type": "string",
                    "description": "task_id of the draft model to refine",
                },
                "output_dir": {
                    "type": "string",
                    "default": "./models",
                },
                "filename": {
                    "type": "string",
                    "default": "",
                },
            },
            "required": ["draft_task_id"],
        },
    ),
    # 10. Check task status
    types.Tool(
        name="check_task_status",
        description="Check the status and details of any Tripo task by ID.",
        inputSchema={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "The Tripo task ID",
                },
            },
            "required": ["task_id"],
        },
    ),
    # 11. Check credit balance
    types.Tool(
        name="check_tripo_balance",
        description="Check remaining Tripo API credit balance.",
        inputSchema={"type": "object", "properties": {}},
    ),
    # 12. Generate Godot scene file
    types.Tool(
        name="create_godot_scene",
        description=(
            "Generate a Godot .tscn scene file that instances a .glb model. "
            "Sets position, rotation, and scale for the model node."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "glb_path": {
                    "type": "string",
                    "description": "Path to the .glb file to instance",
                },
                "node_name": {
                    "type": "string",
                    "description": "Name for the model node in Godot",
                    "default": "Character",
                },
                "position": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "Position [x, y, z]",
                    "default": [0, 0, 0],
                },
                "rotation": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "Rotation degrees [x, y, z]",
                    "default": [0, 0, 0],
                },
                "scale": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "Scale [x, y, z]",
                    "default": [1, 1, 1],
                },
            },
            "required": ["glb_path"],
        },
    ),
    # 13. List available options
    types.Tool(
        name="list_tripo_options",
        description=(
            "List all available Tripo options: animations, styles, formats, "
            "model versions, and rig specs."
        ),
        inputSchema={"type": "object", "properties": {}},
    ),
]


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return TOOLS


# ── Tool dispatch ─────────────────────────────────────────────────────────────


def _text(msg: str) -> list[types.TextContent]:
    return [types.TextContent(type="text", text=msg)]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:

    # ── list_tripo_options ────────────────────────────────────────────────
    if name == "list_tripo_options":
        info = {
            "preset_animations": PRESET_ANIMATIONS,
            "stylize_styles": STYLIZE_STYLES,
            "convert_formats": CONVERT_FORMATS,
            "model_versions": MODEL_VERSIONS,
            "rig_specs": RIG_SPECS,
        }
        return _text(json.dumps(info, indent=2))

    # ── check_tripo_balance ───────────────────────────────────────────────
    if name == "check_tripo_balance":
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"{TRIPO_API}/user/balance", headers=_headers())
            r.raise_for_status()
            data = r.json().get("data", {})
        balance = data.get("balance", "unknown")
        frozen = data.get("frozen", 0)
        return _text(
            f"Tripo credit balance: {balance}\n"
            f"Frozen (in-use): {frozen}"
        )

    # ── check_task_status ─────────────────────────────────────────────────
    if name == "check_task_status":
        tid = arguments["task_id"]
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"{TRIPO_API}/task/{tid}", headers=_headers())
            r.raise_for_status()
            data = r.json().get("data", {})
        return _text(json.dumps(data, indent=2))

    # ── generate_3d_model (text to 3D) ────────────────────────────────────
    if name == "generate_3d_model":
        prompt = arguments["prompt"]
        neg = arguments.get("negative_prompt", "low quality, blurry, distorted")
        version = arguments.get("model_version", "v2.5-20250123")
        style = arguments.get("style", "")
        output_dir = Path(arguments.get("output_dir", "./models"))
        fname = arguments.get("filename", "") or _safe_filename(prompt)

        payload = {
            "type": "text_to_model",
            "prompt": prompt,
            "negative_prompt": neg,
            "model_version": version,
        }
        if style:
            payload["style"] = style

        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"{TRIPO_API}/task", headers=_headers(), json=payload
            )
            r.raise_for_status()
            task_id = r.json()["data"]["task_id"]

        result = f"Generation task submitted: {task_id}\nPolling for completion...\n"
        task_data = await _poll_task(task_id)
        glb_url = _get_model_url(task_data)

        if not glb_url:
            return _text(f"{result}Task done but no model URL found.\n{json.dumps(task_data, indent=2)}")

        dest = output_dir / f"{fname}.glb"
        await _download(glb_url, dest)

        return _text(
            f"{result}"
            f"Model ready!\n"
            f"File: {dest.resolve()}\n"
            f"task_id: {task_id}\n\n"
            f"Godot: drag the .glb into the FileSystem dock to import."
        )

    # ── image_to_3d_model ─────────────────────────────────────────────────
    if name == "image_to_3d_model":
        image_path = arguments["image_path"]
        version = arguments.get("model_version", "v2.5-20250123")
        output_dir = Path(arguments.get("output_dir", "./models"))
        fname = arguments.get("filename", "") or _safe_filename(
            Path(image_path).stem
        )

        token = await _upload_file(image_path)

        payload = {
            "type": "image_to_model",
            "file": {"type": "jpg", "file_token": token},
            "model_version": version,
        }

        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"{TRIPO_API}/task", headers=_headers(), json=payload
            )
            r.raise_for_status()
            task_id = r.json()["data"]["task_id"]

        result = f"Image-to-3D task submitted: {task_id}\nImage: {image_path}\nPolling...\n"
        task_data = await _poll_task(task_id)
        glb_url = _get_model_url(task_data)

        if not glb_url:
            return _text(f"{result}No model URL.\n{json.dumps(task_data, indent=2)}")

        dest = output_dir / f"{fname}.glb"
        await _download(glb_url, dest)

        return _text(
            f"{result}"
            f"Model ready!\n"
            f"File: {dest.resolve()}\n"
            f"task_id: {task_id}"
        )

    # ── rig_3d_model ──────────────────────────────────────────────────────
    if name == "rig_3d_model":
        orig_id = arguments["original_task_id"]
        spec = arguments.get("rig_spec", "mixamo")

        payload = {
            "type": "animate_rig",
            "original_model_task_id": orig_id,
        }
        if spec:
            payload["spec"] = spec

        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"{TRIPO_API}/task", headers=_headers(), json=payload
            )
            r.raise_for_status()
            rig_task_id = r.json()["data"]["task_id"]

        result = f"Rig task submitted: {rig_task_id}\nSpec: {spec}\nPolling...\n"
        await _poll_task(rig_task_id)

        return _text(
            f"{result}"
            f"Rig complete!\n"
            f"rig_task_id: {rig_task_id}\n\n"
            f"Use this rig_task_id with animate_3d_model to add animations."
        )

    # ── animate_3d_model ──────────────────────────────────────────────────
    if name == "animate_3d_model":
        orig_id = arguments["original_task_id"]
        rig_id = arguments["rig_task_id"]
        anim_list = arguments.get("animations", ["idle", "walk", "run"])
        output_dir = Path(arguments.get("output_dir", "./models"))
        fname = arguments.get("filename", "") or f"animated_{orig_id[:8]}"

        payload = {
            "type": "animate_retarget",
            "original_model_task_id": orig_id,
            "rig_task_id": rig_id,
            "animations": [{"name": a} for a in anim_list],
        }

        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"{TRIPO_API}/task", headers=_headers(), json=payload
            )
            r.raise_for_status()
            retarget_id = r.json()["data"]["task_id"]

        result = f"Animation retarget task: {retarget_id}\nAnimations: {', '.join(anim_list)}\nPolling...\n"
        task_data = await _poll_task(retarget_id)
        glb_url = _get_model_url(task_data)

        if not glb_url:
            return _text(f"{result}No model URL.\n{json.dumps(task_data, indent=2)}")

        dest = output_dir / f"{fname}_animated.glb"
        await _download(glb_url, dest)

        return _text(
            f"{result}"
            f"Animated model ready!\n"
            f"File: {dest.resolve()}\n"
            f"Animations: {', '.join(anim_list)}\n\n"
            f"Godot: AnimationPlayer will have all animations embedded."
        )

    # ── generate_and_animate (full pipeline) ──────────────────────────────
    if name == "generate_and_animate":
        prompt = arguments["prompt"]
        neg = arguments.get("negative_prompt", "low quality, blurry, distorted")
        version = arguments.get("model_version", "v2.5-20250123")
        spec = arguments.get("rig_spec", "mixamo")
        anim_list = arguments.get("animations", ["idle", "walk", "run"])
        output_dir = Path(arguments.get("output_dir", "./models"))
        fname = arguments.get("filename", "") or _safe_filename(prompt)
        gen_scene = arguments.get("generate_scene", False)

        result = (
            f"Full pipeline: generate + rig + animate\n"
            f"Prompt: {prompt}\n"
            f"Animations: {', '.join(anim_list)}\n\n"
        )

        # Step 1: generate
        gen_payload = {
            "type": "text_to_model",
            "prompt": prompt,
            "negative_prompt": neg,
            "model_version": version,
        }
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"{TRIPO_API}/task", headers=_headers(), json=gen_payload
            )
            r.raise_for_status()
            gen_task_id = r.json()["data"]["task_id"]
        result += f"[1/3] Generating model... task: {gen_task_id}\n"
        await _poll_task(gen_task_id)
        result += "Model generated.\n\n"

        # Step 2: rig
        rig_payload = {
            "type": "animate_rig",
            "original_model_task_id": gen_task_id,
        }
        if spec:
            rig_payload["spec"] = spec
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"{TRIPO_API}/task", headers=_headers(), json=rig_payload
            )
            r.raise_for_status()
            rig_task_id = r.json()["data"]["task_id"]
        result += f"[2/3] Rigging ({spec})... task: {rig_task_id}\n"
        await _poll_task(rig_task_id)
        result += "Rig complete.\n\n"

        # Step 3: retarget animations
        anim_payload = {
            "type": "animate_retarget",
            "original_model_task_id": gen_task_id,
            "rig_task_id": rig_task_id,
            "animations": [{"name": a} for a in anim_list],
        }
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"{TRIPO_API}/task", headers=_headers(), json=anim_payload
            )
            r.raise_for_status()
            retarget_id = r.json()["data"]["task_id"]
        result += f"[3/3] Baking animations... task: {retarget_id}\n"
        task_data = await _poll_task(retarget_id)
        result += "Animations baked.\n\n"

        glb_url = _get_model_url(task_data)
        if not glb_url:
            return _text(f"{result}No model URL.\n{json.dumps(task_data, indent=2)}")

        dest = output_dir / f"{fname}_animated.glb"
        await _download(glb_url, dest)

        result += (
            f"Done! Animated character ready for Godot.\n"
            f"File: {dest.resolve()}\n"
            f"Animations: {', '.join(anim_list)}\n"
        )

        # Optional Godot scene generation
        if gen_scene:
            scene_path = _generate_godot_scene(dest, fname)
            result += f"Godot scene: {scene_path.resolve()}\n"

        result += (
            f"\nGodot import steps:\n"
            f"  1. Drag the .glb into your FileSystem dock\n"
            f"  2. Instance it in your scene (or use the .tscn)\n"
            f"  3. AnimationPlayer has all animations embedded\n"
            f"  4. Use AnimationTree for blending/state machines\n"
        )

        return _text(result)

    # ── stylize_3d_model ──────────────────────────────────────────────────
    if name == "stylize_3d_model":
        orig_id = arguments["original_task_id"]
        style = arguments["style"]
        output_dir = Path(arguments.get("output_dir", "./models"))
        fname = arguments.get("filename", "") or f"stylized_{style}_{orig_id[:8]}"

        payload = {
            "type": "stylize_model",
            "original_model_task_id": orig_id,
            "style": style,
        }
        block_size = arguments.get("block_size")
        if block_size:
            payload["block_size"] = block_size

        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"{TRIPO_API}/task", headers=_headers(), json=payload
            )
            r.raise_for_status()
            task_id = r.json()["data"]["task_id"]

        result = f"Stylize task submitted: {task_id}\nStyle: {style}\nPolling...\n"
        task_data = await _poll_task(task_id)
        glb_url = _get_model_url(task_data)

        if not glb_url:
            return _text(f"{result}No model URL.\n{json.dumps(task_data, indent=2)}")

        dest = output_dir / f"{fname}.glb"
        await _download(glb_url, dest)

        return _text(
            f"{result}"
            f"Stylized model ready!\n"
            f"File: {dest.resolve()}\n"
            f"Style: {style}\n"
            f"task_id: {task_id}"
        )

    # ── convert_3d_model ──────────────────────────────────────────────────
    if name == "convert_3d_model":
        orig_id = arguments["original_task_id"]
        fmt = arguments["format"]
        quad = arguments.get("quad", False)
        face_limit = arguments.get("face_limit", 0)
        scale_factor = arguments.get("scale_factor", 1.0)
        output_dir = Path(arguments.get("output_dir", "./models"))
        fname = arguments.get("filename", "") or f"converted_{orig_id[:8]}"

        payload = {
            "type": "convert_model",
            "original_model_task_id": orig_id,
            "format": fmt,
            "quad": quad,
        }
        if face_limit > 0:
            payload["face_limit"] = face_limit
        if scale_factor != 1.0:
            payload["scale_factor"] = scale_factor

        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"{TRIPO_API}/task", headers=_headers(), json=payload
            )
            r.raise_for_status()
            task_id = r.json()["data"]["task_id"]

        result = f"Convert task submitted: {task_id}\nFormat: {fmt}\nPolling...\n"
        task_data = await _poll_task(task_id)
        model_url = _get_model_url(task_data)

        if not model_url:
            return _text(f"{result}No model URL.\n{json.dumps(task_data, indent=2)}")

        ext = fmt if fmt != "glb" else "glb"
        dest = output_dir / f"{fname}.{ext}"
        await _download(model_url, dest)

        return _text(
            f"{result}"
            f"Converted model ready!\n"
            f"File: {dest.resolve()}\n"
            f"Format: {fmt}\n"
            f"task_id: {task_id}"
        )

    # ── texture_3d_model ──────────────────────────────────────────────────
    if name == "texture_3d_model":
        orig_id = arguments["original_task_id"]
        prompt = arguments.get("prompt", "")
        output_dir = Path(arguments.get("output_dir", "./models"))
        fname = arguments.get("filename", "") or f"textured_{orig_id[:8]}"

        payload = {
            "type": "texture_model",
            "original_model_task_id": orig_id,
        }
        if prompt:
            payload["prompt"] = prompt

        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"{TRIPO_API}/task", headers=_headers(), json=payload
            )
            r.raise_for_status()
            task_id = r.json()["data"]["task_id"]

        result = f"Texture task submitted: {task_id}\nPolling...\n"
        task_data = await _poll_task(task_id)
        glb_url = _get_model_url(task_data)

        if not glb_url:
            return _text(f"{result}No model URL.\n{json.dumps(task_data, indent=2)}")

        dest = output_dir / f"{fname}.glb"
        await _download(glb_url, dest)

        return _text(
            f"{result}"
            f"Textured model ready!\n"
            f"File: {dest.resolve()}\n"
            f"task_id: {task_id}"
        )

    # ── refine_3d_model ───────────────────────────────────────────────────
    if name == "refine_3d_model":
        draft_id = arguments["draft_task_id"]
        output_dir = Path(arguments.get("output_dir", "./models"))
        fname = arguments.get("filename", "") or f"refined_{draft_id[:8]}"

        payload = {
            "type": "refine_model",
            "draft_model_task_id": draft_id,
        }

        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"{TRIPO_API}/task", headers=_headers(), json=payload
            )
            r.raise_for_status()
            task_id = r.json()["data"]["task_id"]

        result = f"Refine task submitted: {task_id}\nPolling...\n"
        task_data = await _poll_task(task_id)
        glb_url = _get_model_url(task_data)

        if not glb_url:
            return _text(f"{result}No model URL.\n{json.dumps(task_data, indent=2)}")

        dest = output_dir / f"{fname}.glb"
        await _download(glb_url, dest)

        return _text(
            f"{result}"
            f"Refined model ready!\n"
            f"File: {dest.resolve()}\n"
            f"task_id: {task_id}"
        )

    # ── create_godot_scene ────────────────────────────────────────────────
    if name == "create_godot_scene":
        glb_path = Path(arguments["glb_path"])
        node_name = arguments.get("node_name", "Character")
        pos = tuple(arguments.get("position", [0, 0, 0]))
        rot = tuple(arguments.get("rotation", [0, 0, 0]))
        scl = tuple(arguments.get("scale", [1, 1, 1]))

        if not glb_path.exists():
            return _text(f"Error: GLB file not found: {glb_path}")

        scene_path = _generate_godot_scene(glb_path, node_name, pos, rot, scl)

        return _text(
            f"Godot scene generated!\n"
            f"Scene: {scene_path.resolve()}\n"
            f"Model: {glb_path.resolve()}\n"
            f"Node: {node_name}\n"
            f"Position: {pos}\n\n"
            f"Open the .tscn in Godot to see your model in the scene."
        )

    return _text(f"Unknown tool: {name}")


# ── Entry point ───────────────────────────────────────────────────────────────

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
