import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { getCurrentSystemPrompt } from "@earendil-works/pi-ai";

/** Temporary Pi 0.87.0 custom-message kickoff repair. See README.md for removal. */
export default function herdrFirstPrompt(pi: ExtensionAPI) {
  if (!process.env.PI_HERDR_SUBAGENT_ID?.trim() || !process.env.PI_HERDR_SUBAGENT_ATTEMPT_ID?.trim()) return;

  pi.on("context_with_system", (event, ctx) => {
    // Inspect the replayed prompt, not just the head: resumed sessions can carry patches.
    if (getCurrentSystemPrompt(event.messages).trim()) return;
    const prompt = ctx.getSystemPrompt();
    if (!/<subagent_role_guidance>\s*\S[\s\S]*?<\/subagent_role_guidance>/.test(prompt)
      || !/<subagent_dispatch>\s*\S[\s\S]*?<\/subagent_dispatch>/.test(prompt)) return;

    const head = event.messages[0];
    if (head?.role !== "system") return;
    // Request-local only. Keep tool declarations and every other message unchanged.
    return { messages: [{ ...head, content: prompt }, ...event.messages.slice(1)] };
  });
}
