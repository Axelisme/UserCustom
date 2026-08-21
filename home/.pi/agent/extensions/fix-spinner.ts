import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

/**
 * fix-spinner: work around TuiBase renderRequested deadlock
 *
 * Root cause:
 * - TuiBase.requestRender() is throttled (MIN_RENDER_INTERVAL_MS=16) and deduped
 *   via `renderRequested` flag + nextTick -> scheduleRender -> setTimeout.
 * - Loader (spinner) drives animation via setInterval(80ms) -> updateDisplay() -> ui.requestRender()
 * - If ui.stop() happens while renderRequested=true, scheduleRender bails on `stopped`
 *   but leaves renderRequested=true. Subsequent ui.start() calls requestRender()
 *   which early-returns due to dedup, so no timer is ever scheduled again.
 *   All future Loader ticks are dropped until a key triggers requestImmediateRender().
 *
 * Symptom: spinner freezes after external editor / SIGTSTP / switchTuiMode,
 *          resumes for one frame on any key/focus move. Early startup looks fine
 *          because streaming message_updates keep pumping renders.
 *
 * This extension monkey-patches TuiBase.prototype.stop/start at load time
 * to clear the stale flag and force an immediate render on resume.
 * Remove once upstream pi-tui fixes stop() to reset renderRequested.
 */
export default async function fixSpinner(_pi: ExtensionAPI) {
	try {
		const mod = (await import("@earendil-works/pi-tui")) as any;
		// TuiBase is re-exported from pi-tui root; fallback to direct file if needed
		let TuiBase: any = mod.TuiBase;
		if (!TuiBase) {
			const tuiMod = (await import("@earendil-works/pi-tui/dist/tui.js")) as any;
			TuiBase = tuiMod.TuiBase;
		}
		if (!TuiBase || !TuiBase.prototype) return;

		const proto = TuiBase.prototype as any;

		// Avoid double-patching
		if (proto.__fixSpinnerPatched) return;
		proto.__fixSpinnerPatched = true;

		const origStop = proto.stop;
		const origStart = proto.start;

		if (typeof origStop === "function") {
			proto.stop = function (this: any, ...args: any[]) {
				// Clear deadlock state before stopping
				try {
					this.renderRequested = false;
					this.immediateRenderScheduled = false;
					if (this.renderTimer) {
						clearTimeout(this.renderTimer);
						this.renderTimer = undefined;
					}
				} catch {}
				return origStop.apply(this, args);
			};
		}

		if (typeof origStart === "function") {
			proto.start = function (this: any, ...args: any[]) {
				const ret = origStart.apply(this, args);
				// start() internally calls requestRender() which was previously deduped;
				// force an immediate frame to guarantee spinner resumes
				try {
					// Ensure flag is clean then force immediate path (bypasses 16ms throttle)
					this.renderRequested = false;
					if (typeof this.requestImmediateRender === "function") {
						this.requestImmediateRender();
					} else if (typeof this.requestRender === "function") {
						this.requestRender(true);
					}
				} catch {}
				return ret;
			};
		}
	} catch {
		// Silent: pi-tui not available in non-TUI modes (print/json/rpc)
	}
}
