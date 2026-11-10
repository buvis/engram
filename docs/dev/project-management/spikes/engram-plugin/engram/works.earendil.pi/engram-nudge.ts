// Spike, NOT RUN: Pi adapter sketch written from Pi 1.5.0 docs/extensions.md (tool_result can modify result).
import { spawnSync } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { isBashToolResult } from "@earendil-works/pi-coding-agent";

const core = join(dirname(fileURLToPath(import.meta.url)), "..", "nudge", "engram_nudge.py");

export default function (pi: any) {
  pi.on("tool_result", async (event: any, ctx: any) => {
    if (!isBashToolResult(event)) return;
    const payload = JSON.stringify({ tool_input: event.input, cwd: ctx.cwd });
    const done = spawnSync("python3", [core, "plain"], { input: payload, encoding: "utf8", timeout: 12000 });
    const text = (done.stdout ?? "").trim();
    if (!text) return;
    return { content: [...event.content, { type: "text", text }] };
  });
}
