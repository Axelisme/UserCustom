from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOME = ROOT / "home"
CODEX_SKILLS = HOME / ".codex" / "skills"
OVERLAY_SKILLS = (
    HOME / ".claude" / "skills",
    HOME / ".pi" / "agent" / "skills",
)
PROFILES = {
    "acceptance-reviewer": (
        HOME / ".claude/agents/acceptance-reviewer.md",
        HOME / ".pi/agent/agents/acceptance-reviewer.md",
        HOME / ".codex/agents/acceptance-reviewer.toml",
    ),
    "lane-worker": (
        HOME / ".claude/agents/lane-worker.md",
        HOME / ".pi/agent/agents/lane-worker.md",
        HOME / ".codex/agents/lane-worker.toml",
    ),
}

sys.path.insert(0, str(CODEX_SKILLS / "orchestrate" / "scripts"))
from _orchestrate import release  # noqa: E402


class SkillOverlayParityTests(unittest.TestCase):
    """The codex tree owns every skill; the other runtimes only point at it.

    Agent profiles cannot follow that rule. Their frontmatter is deliberately
    runtime-specific — model, tools, and the codex copy is TOML — so only the
    prompt body is shared, and that half is asserted here instead of by a link.
    """

    def test_codex_owns_every_skill_directory(self) -> None:
        skills = sorted(path.name for path in CODEX_SKILLS.iterdir() if path.is_dir())
        self.assertTrue(skills, "expected at least one codex skill")
        for name in skills:
            with self.subTest(skill=name):
                self.assertFalse(
                    (CODEX_SKILLS / name).is_symlink(),
                    f"{name}: codex skill is not the owner",
                )

    def test_overlay_skills_are_symlinks_to_the_codex_owner(self) -> None:
        for overlay in OVERLAY_SKILLS:
            self.assertTrue(overlay.is_dir(), f"missing overlay: {overlay}")
            for entry in sorted(overlay.iterdir()):
                with self.subTest(overlay=overlay.name, skill=entry.name):
                    self.assertTrue(
                        entry.is_symlink(),
                        f"{entry} is not a symlink to the codex owner",
                    )
                    owner = CODEX_SKILLS / entry.name
                    self.assertTrue(owner.is_dir(), f"no codex owner: {owner}")
                    self.assertEqual(entry.resolve(), owner.resolve())

    def test_dispatched_profiles_share_one_prompt_across_runtimes(self) -> None:
        for name, paths in PROFILES.items():
            digests: dict[str, str] = {}
            for path in paths:
                with self.subTest(profile=path):
                    self.assertTrue(path.is_file(), f"missing profile: {path}")
                    agent_name, prompt = release.profile_identity_prompt(path)
                    self.assertEqual(agent_name, name)
                    digests[path.name] = hashlib.sha256(
                        prompt.encode("utf-8")
                    ).hexdigest()
            self.assertEqual(
                len(set(digests.values())),
                1,
                f"{name}: runtime copies disagree on the prompt: {digests}",
            )


if __name__ == "__main__":
    unittest.main()
