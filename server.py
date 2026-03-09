#!/usr/bin/env python3
"""
Tripo AI MCP Server for Claude Code
Lets Claude Code generate 3D characters + animations and drop them into your Godot project.
"""

import asyncio
import os
import sys
import json
import httpx
from pathlib import Path
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

# ── MCP server setup ────────────────────────────────────────────────────────
server = Server("tripo-mcp")

TRIPO_API = "https://api.tripo3d.ai/v2/openapi"


def get_api_key() -> str:
    key = os.environ.get("TRIPO_API_KEY", "")
    if not key:
        raise ValueError("TRIPO_API_KEY environment variable not set.")
    return key


def headers() -> dict:
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {get_api_key()}",
    }


# ── Helpers ──────────────────────────────────────────────────────────────────

async def poll_task(task_id: str, timeout: int = 300) -> dict:
    """Poll until task is done or timeout (seconds)."""
    async with httpx.AsyncClient(timeout=30) as client:
        for _ in range(timeout // 5):
            await asyncio.sleep(5)
            r = await client.get(f"{TRIPO_API}/task/{task_id}", headers=headers())
            r.raise_for_status()
            data = r.json()["data"]
            status = data.get("status")
            if status == "success":
                return data
            if status in ("failed", "cancelled", "unknown"):
                raise RuntimeError(f"Task {task_id} ended with status: {status}")
    raise TimeoutError(f"Task {task_id} did not complete within {timeout}s")


async def download_file(url: str, dest: Path) -> Path:
    """Download a file to dest path."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
        r = await client.get(url)
        r.raise_for_status()
        dest.write_bytes(r.content)
    return dest


# ── Tools ────────────────────────────────────────────────────────────────────

@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="generate_3d_character",
            description=(
                "Generate a 3D character or object from a text prompt using Tripo AI. "
                "Returns a task_id and the downloaded .glb file path ready for Godot."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "Describe the character or object (e.g. 'a goblin warrior with mossy armor')",
                    },
                    "negative_prompt": {
                        "type": "string",
                        "description": "What to avoid (default: 'low quality, blurry')",
                        "default": "low quality, blurry, distorted",
                    },
                    "output_dir": {
                        "type": "string",
                        "description": "Directory to save the .glb file (default: ./models)",
                        "default": "./models",
                    },
                    "filename": {
                        "type": "string",
                        "description": "Output filename without extension (default: derived from prompt)",
                        "default": "",
                    },
                },
                "required": ["prompt"],
            },
        ),
        types.Tool(
            name="animate_3d_model",
            description=(
                "Rig and animate an existing Tripo model using its task_id. "
                "Runs: animate_rig → animate_retarget with preset animations. "
                "Downloads the animated .glb ready for Godot's AnimationPlayer."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "original_task_id": {
                        "type": "string",
                        "description": "The task_id from generate_3d_character",
                    },
                    "animations": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of preset animations to apply. Options: walk, run, idle, jump, wave, sit",
                        "default": ["idle", "walk", "run"],
                    },
                    "output_dir": {
                        "type": "string",
                        "description": "Directory to save the animated .glb",
                        "default": "./models",
                    },
                    "filename": {
                        "type": "string",
                        "description": "Output filename without extension",
                        "default": "",
                    },
                },
                "required": ["original_task_id"],
            },
        ),
        types.Tool(
            name="generate_and_animate",
            description=(
                "Full pipeline: generate a 3D character from text AND rig + animate it "
                "in one call. Saves a ready-to-use animated .glb for Godot."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "Describe the character (e.g. 'a warrior elf with silver armor')",
                    },
                    "negative_prompt": {
                        "type": "string",
                        "default": "low quality, blurry, distorted",
                    },
                    "animations": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Preset animations: idle, walk, run, jump, wave, sit",
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
                "required": ["prompt"],
            },
        ),
        types.Tool(
            name="check_task_status",
            description="Check the status of any Tripo task by its task_id.",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "The Tripo task ID to check"},
                },
                "required": ["task_id"],
            },
        ),
        types.Tool(
            name="check_tripo_balance",
            description="Check how many Tripo API credits you have remaining.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:

    # ── check_tripo_balance ──────────────────────────────────────────────────
    if name == "check_tripo_balance":
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"{TRIPO_API}/user/balance", headers=headers())
            r.raise_for_status()
            data = r.json()
        balance = data.get("data", {}).get("balance", "unknown")
        return [types.TextContent(type="text", text=f"Tripo credit balance: {balance}")]

    # ── check_task_status ────────────────────────────────────────────────────
    if name == "check_task_status":
        task_id = arguments["task_id"]
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"{TRIPO_API}/task/{task_id}", headers=headers())
            r.raise_for_status()
            data = r.json()["data"]
        return [types.TextContent(type="text", text=json.dumps(data, indent=2))]

    # ── generate_3d_character ────────────────────────────────────────────────
    if name == "generate_3d_character":
        prompt = arguments["prompt"]
        neg = arguments.get("negative_prompt", "low quality, blurry, distorted")
        output_dir = Path(arguments.get("output_dir", "./models"))
        fname = arguments.get("filename", "") or prompt[:40].replace(" ", "_").replace("/", "-")

        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"{TRIPO_API}/task",
                headers=headers(),
                json={
                    "type": "text_to_model",
                    "prompt": prompt,
                    "negative_prompt": neg,
                    "model_version": "v2.5-20250123",
                },
            )
            r.raise_for_status()
            task_id = r.json()["data"]["task_id"]

        result = f"⏳ Generation task submitted: {task_id}\nPolling for completion...\n"

        task_data = await poll_task(task_id)
        glb_url = task_data.get("output", {}).get("model", "")

        if not glb_url:
            return [types.TextContent(type="text", text=f"Task done but no model URL found.\n{json.dumps(task_data, indent=2)}")]

        dest = output_dir / f"{fname}.glb"
        await download_file(glb_url, dest)

        result += f"✅ Model ready!\n📁 Saved to: {dest.resolve()}\n🔑 task_id: {task_id}\n\nImport this .glb into Godot via the FileSystem dock."
        return [types.TextContent(type="text", text=result)]

    # ── animate_3d_model ─────────────────────────────────────────────────────
    if name == "animate_3d_model":
        orig_id = arguments["original_task_id"]
        anim_list = arguments.get("animations", ["idle", "walk", "run"])
        output_dir = Path(arguments.get("output_dir", "./models"))
        fname = arguments.get("filename", "") or f"animated_{orig_id[:8]}"

        result = ""

        # Step 1: rig
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"{TRIPO_API}/task",
                headers=headers(),
                json={"type": "animate_rig", "original_model_task_id": orig_id},
            )
            r.raise_for_status()
            rig_task_id = r.json()["data"]["task_id"]
        result += f"⏳ Rigging task: {rig_task_id}\n"
        await poll_task(rig_task_id)
        result += "✅ Rig done.\n"

        # Step 2: retarget with animations
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"{TRIPO_API}/task",
                headers=headers(),
                json={
                    "type": "animate_retarget",
                    "original_model_task_id": orig_id,
                    "rig_task_id": rig_task_id,
                    "animations": [{"name": a} for a in anim_list],
                },
            )
            r.raise_for_status()
            retarget_task_id = r.json()["data"]["task_id"]
        result += f"⏳ Animation retarget task: {retarget_task_id}\n"
        task_data = await poll_task(retarget_task_id)
        result += "✅ Animation done.\n"

        glb_url = task_data.get("output", {}).get("model", "")
        if not glb_url:
            return [types.TextContent(type="text", text=f"{result}\nNo model URL in result.\n{json.dumps(task_data, indent=2)}")]

        dest = output_dir / f"{fname}_animated.glb"
        await download_file(glb_url, dest)

        result += f"📁 Saved to: {dest.resolve()}\n\nIn Godot: Import > AnimationPlayer will have all animations baked in."
        return [types.TextContent(type="text", text=result)]

    # ── generate_and_animate (full pipeline) ─────────────────────────────────
    if name == "generate_and_animate":
        prompt = arguments["prompt"]
        neg = arguments.get("negative_prompt", "low quality, blurry, distorted")
        anim_list = arguments.get("animations", ["idle", "walk", "run"])
        output_dir = Path(arguments.get("output_dir", "./models"))
        fname = arguments.get("filename", "") or prompt[:40].replace(" ", "_").replace("/", "-")

        result = f"🚀 Full pipeline: generate + rig + animate\nPrompt: {prompt}\nAnimations: {anim_list}\n\n"

        # Step 1: generate
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"{TRIPO_API}/task",
                headers=headers(),
                json={
                    "type": "text_to_model",
                    "prompt": prompt,
                    "negative_prompt": neg,
                    "model_version": "v2.5-20250123",
                },
            )
            r.raise_for_status()
            gen_task_id = r.json()["data"]["task_id"]
        result += f"⏳ [1/3] Generating model... task: {gen_task_id}\n"
        await poll_task(gen_task_id)
        result += "✅ Model generated.\n\n"

        # Step 2: rig
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"{TRIPO_API}/task",
                headers=headers(),
                json={"type": "animate_rig", "original_model_task_id": gen_task_id},
            )
            r.raise_for_status()
            rig_task_id = r.json()["data"]["task_id"]
        result += f"⏳ [2/3] Rigging... task: {rig_task_id}\n"
        await poll_task(rig_task_id)
        result += "✅ Rig complete.\n\n"

        # Step 3: retarget
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"{TRIPO_API}/task",
                headers=headers(),
                json={
                    "type": "animate_retarget",
                    "original_model_task_id": gen_task_id,
                    "rig_task_id": rig_task_id,
                    "animations": [{"name": a} for a in anim_list],
                },
            )
            r.raise_for_status()
            retarget_task_id = r.json()["data"]["task_id"]
        result += f"⏳ [3/3] Baking animations... task: {retarget_task_id}\n"
        task_data = await poll_task(retarget_task_id)
        result += "✅ Animations baked.\n\n"

        glb_url = task_data.get("output", {}).get("model", "")
        if not glb_url:
            return [types.TextContent(type="text", text=f"{result}No model URL found.\n{json.dumps(task_data, indent=2)}")]

        dest = output_dir / f"{fname}_animated.glb"
        await download_file(glb_url, dest)

        result += (
            f"🎉 Done! Animated character ready for Godot.\n"
            f"📁 File: {dest.resolve()}\n"
            f"🎬 Animations included: {', '.join(anim_list)}\n\n"
            f"Next steps in Godot:\n"
            f"  1. Drag the .glb into your FileSystem\n"
            f"  2. Instance it in your scene\n"
            f"  3. Add an AnimationPlayer node — animations are already embedded\n"
        )
        return [types.TextContent(type="text", text=result)]

    return [types.TextContent(type="text", text=f"Unknown tool: {name}")]


# ── Entry point ───────────────────────────────────────────────────────────────

async def main():
    async with stdio_server() as (r, w):
        await server.run(r, w, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
