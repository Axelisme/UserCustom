from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CODEX_SKILLS = ROOT / "home" / ".codex" / "skills"
PI_SKILLS = ROOT / "home" / ".pi" / "agent" / "skills"


def codex_skills_with_scripts() -> list[str]:
    return sorted(
        skill_dir.name
        for skill_dir in CODEX_SKILLS.iterdir()
        if skill_dir.is_dir() and (skill_dir / "scripts").exists()
    )


class SkillOverlayParityTests(unittest.TestCase):
    def test_pi_scripts_dirs_are_symlinks_to_the_codex_owner(self) -> None:
        skills = codex_skills_with_scripts()
        self.assertTrue(skills, "expected at least one codex skill with a scripts/ dir")
        for name in skills:
            with self.subTest(skill=name):
                codex_scripts = CODEX_SKILLS / name / "scripts"
                pi_scripts = PI_SKILLS / name / "scripts"
                self.assertTrue(
                    pi_scripts.exists(), f"{name}: missing pi scripts dir {pi_scripts}"
                )
                self.assertTrue(
                    pi_scripts.is_symlink(),
                    f"{name}: pi scripts dir is not a symlink: {pi_scripts}",
                )
                self.assertEqual(
                    pi_scripts.resolve(),
                    codex_scripts.resolve(),
                    f"{name}: pi scripts symlink does not resolve to the codex owner",
                )


if __name__ == "__main__":
    unittest.main()
