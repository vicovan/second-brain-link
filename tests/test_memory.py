#!/usr/bin/env python3
"""tests/test_memory.py — the plugin memory layer (memory.py, sbl-memory/1).

Stdlib unittest; no network, no model calls. Also asserts the copies shipped in every plugin
are byte-identical (the Codex build flattens per plugin, so each plugin carries its own copy).

    python3 tests/test_memory.py
"""
import filecmp
import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import threading
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
COPIES = [
    REPO / "plugins/job-search/skills/job-scout/scripts/memory.py",
    REPO / "plugins/fundraising/skills/raise-research/scripts/memory.py",
    REPO / "plugins/travel-planner/skills/trip-planner/scripts/memory.py",
    REPO / "engine/scripts/memory.py",
]
SRC = COPIES[0]


def load():
    spec = importlib.util.spec_from_file_location("sbl_memory", SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class MemoryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.brain = pathlib.Path(self.tmp.name) / "jane-brain"
        self.brain.mkdir(parents=True)
        (self.brain / "_STRUCTURE.md").write_text("# structure\n")
        self.m = load()
        self.b = str(self.brain)

    def tearDown(self):
        self.tmp.cleanup()

    def items(self, scope):
        return self.m.Store(self.b).items(scope)

    # -- tiers
    def test_tiers(self):
        u = self.m.observe("job-search", "rule", "user", "Skip roles that require relocation.", ["scoring"], brain=self.b)
        o = self.m.observe("job-search", "lesson", "outcome", "Director roles at 1,000+ person companies got no reply (0/4).", ["scoring"], brain=self.b)
        a = self.m.observe("job-search", "lesson", "agent", "Lead with the identity archetype for security companies.", ["cv"], brain=self.b)
        # default policy "auto" (user decision 2026-09-28): inferences are active at once, flagged agent
        self.assertEqual((u["status"], o["status"], a["status"]), ("active", "active", "active"))
        rec = {i["id"]: i for i in self.m.recall("job-search", ["scoring", "cv"], brain=self.b)}
        self.assertIn(u["id"], rec)
        self.assertIn(o["id"], rec)
        self.assertIn(a["id"], rec, "by default an inference is used at once")
        self.assertEqual(rec[a["id"]]["source"], "agent", "and stays flagged as inferred")

    def test_review_policy(self):
        self.assertEqual(self.m.get_policy(brain=self.b), "auto")
        self.m.set_policy("review", brain=self.b)
        a = self.m.observe("job-search", "lesson", "agent", "Lead with the identity archetype.", ["cv"], brain=self.b)
        self.assertEqual(a["status"], "pending")
        self.assertNotIn(a["id"], [i["id"] for i in self.m.recall("job-search", ["cv"], brain=self.b)])
        self.assertEqual(self.m.approve_all(brain=self.b), 1)
        self.assertIn(a["id"], [i["id"] for i in self.m.recall("job-search", ["cv"], brain=self.b)])

    # -- reinforcement
    def test_reinforce_instead_of_duplicate(self):
        a = self.m.observe("fundraising", "lesson", "outcome", "Warm intros get replies; cold emails do not.", brain=self.b)
        b = self.m.observe("fundraising", "lesson", "outcome", "warm intros get replies, cold emails do not", brain=self.b)
        self.assertEqual(b["action"], "reinforced")
        self.assertEqual(b["id"], a["id"])
        its = self.items("fundraising")
        self.assertEqual(len(its), 1)
        self.assertEqual(its[a["id"]]["strength"], 3)
        c = self.m.observe("fundraising", "lesson", "outcome", "Intros through a portfolio founder convert best.", match=a["id"], evidence="events|replied", brain=self.b)
        self.assertEqual(c["id"], a["id"])
        self.assertEqual(self.items("fundraising")[a["id"]]["strength"], 4)

    def test_user_confirmation_promotes_pending(self):
        self.m.set_policy("review", brain=self.b)
        a = self.m.observe("travel-planner", "preference", "agent", "Prefers boutique hotels near old towns.", brain=self.b)
        self.assertEqual(a["status"], "pending")
        self.m.observe("travel-planner", "preference", "user", "Prefers boutique hotels near old towns.", brain=self.b)
        self.assertEqual(self.items("travel-planner")[a["id"]]["status"], "active")

    def test_supersede_by_user_only(self):
        old = self.m.observe("job-search", "rule", "user", "Exclude Globex.", brain=self.b)
        self.m.observe("job-search", "rule", "agent", "Include Globex again.", supersedes=old["id"], new=True, brain=self.b)
        self.assertEqual(self.items("job-search")[old["id"]]["status"], "active", "an inference may not retire a user rule")
        self.m.observe("job-search", "rule", "user", "Keep Globex.", supersedes=old["id"], new=True, brain=self.b)
        self.assertEqual(self.items("job-search")[old["id"]]["status"], "retired")

    # -- recall
    def test_recall_scopes_and_budget(self):
        self.m.observe("brain", "preference", "user", "Answers as short bullet points.", brain=self.b)
        self.m.observe("shared", "fact", "user", "Will not relocate to the United States.", brain=self.b)
        for i in range(60):
            self.m.observe("job-search", "lesson", "outcome", f"Observation number {i} about portal behaviour at company {i}.", new=True, brain=self.b)
        rec = self.m.recall("job-search", [], budget=300, brain=self.b)
        texts = [i["text"] for i in rec]
        self.assertTrue(any("bullet" in t for t in texts), "agents also recall the brain scope")
        self.assertTrue(any("relocate" in t for t in texts), "and the shared scope")
        self.assertLess(len(rec), 40, "the budget caps recall")
        brain_rec = self.m.recall("brain", brain=self.b)
        self.assertFalse(any("portal" in i["text"] for i in brain_rec), "the brain chat does not recall agent scopes")
        self.assertTrue(any(i.get("last_used") for i in self.items("brain").values()), "recall stamps last_used")

    # -- safety
    def test_refuses_secrets(self):
        for bad in ("password: hunter2hunter2", "card 4111 1111 1111 1111", "key sk-abcdefghijklmnopqrstuvwx"):
            with self.assertRaises(ValueError):
                self.m.observe("brain", "fact", "user", bad, brain=self.b)

    def test_forget_and_render(self):
        a = self.m.observe("brain", "preference", "user", "Lead with the answer.", brain=self.b)
        md = (self.brain / "_memory" / "brain.md").read_text()
        self.assertIn(a["id"], md)
        self.assertTrue((self.brain / "_memory" / "Memory.md").is_file())
        self.assertTrue((self.brain / "_memory" / "Review.md").is_file())
        self.m.set_status(a["id"], "forgotten", brain=self.b)
        self.assertEqual(self.m.recall("brain", brain=self.b), [])
        self.assertNotIn(a["id"], (self.brain / "_memory" / "brain.md").read_text())

    def test_sync_hand_edits(self):
        a = self.m.observe("brain", "preference", "user", "Answers in English.", brain=self.b)
        b = self.m.observe("brain", "preference", "user", "Use metric units.", brain=self.b)
        p = self.brain / "_memory" / "brain.md"
        txt = p.read_text().replace("Answers in English.", "Answers in English, never French.")
        txt = "\n".join(l for l in txt.splitlines() if b["id"] not in l)
        p.write_text(txt)
        res = self.m.sync(brain=self.b)
        self.assertEqual(res, {"edited": 1, "retired": 1})
        its = self.items("brain")
        self.assertEqual(its[a["id"]]["text"], "Answers in English, never French.")
        self.assertEqual(its[b["id"]]["status"], "retired")

    # -- legacy imports
    def test_import_legacy(self):
        d = pathlib.Path(self.tmp.name)
        (d / "job-lessons.md").write_text("# Lessons\n\n## Rules\n\n- [scoring] Skip Workday portals — account wall.\n\n## Statistics\n\n- 20 applied\n")
        (d / "obs.jsonl").write_text(json.dumps({"date": "2026-09-20", "tag": "cv", "text": "Recruiters ignored CVs over two pages."}) + "\n")
        (d / "fund-lessons.md").write_text("# Lessons\n\n- 2026-09-25 — Accelerators want a live demo link in the form.\n")
        r1 = self.m.import_legacy("job-search", str(d / "job-lessons.md"), str(d / "obs.jsonl"), "job", brain=self.b)
        r2 = self.m.import_legacy("fundraising", str(d / "fund-lessons.md"), None, "fund", brain=self.b)
        self.assertEqual((r1["imported"], r2["imported"]), (2, 1))
        js = list(self.items("job-search").values())
        rule = next(i for i in js if "Workday" in i["text"])
        self.assertEqual((rule["status"], rule["tags"]), ("active", ["scoring"]))
        obs = next(i for i in js if "two pages" in i["text"])
        self.assertEqual((obs["status"], obs["source"]), ("active", "agent"), "imported inferences are used at once, flagged")
        self.assertEqual(list(self.items("fundraising").values())[0]["status"], "active")

    # -- concurrency
    def test_concurrent_writers(self):
        errs = []

        def w(n):
            try:
                for i in range(15):
                    self.m.observe("job-search", "lesson", "outcome", f"writer {n} note {i} distinct text", new=True, brain=self.b)
            except Exception as e:  # noqa: BLE001
                errs.append(e)

        ts = [threading.Thread(target=w, args=(n,)) for n in range(4)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(errs, [])
        self.assertEqual(len(self.items("job-search")), 60)

    # -- CLI + brain discovery
    def test_cli_from_inside_a_plugin_ledger(self):
        led = self.brain / ".plugins" / "job-search"
        led.mkdir(parents=True)
        env = dict(os.environ)
        env.pop("SBL_BRAIN", None)
        out = subprocess.run([sys.executable, str(SRC), "observe", "--scope", "job-search", "--kind", "rule",
                              "--source", "user", "--text", "Never apply to crypto companies."],
                             cwd=led, env=env, capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertTrue((self.brain / "_memory" / "job-search.md").is_file(), "found the brain from the ledger folder")
        rec = subprocess.run([sys.executable, str(SRC), "recall", "--scope", "job-search"], cwd=led, env=env, capture_output=True, text=True)
        self.assertIn("crypto", rec.stdout)


class CopiesTest(unittest.TestCase):
    def test_every_plugin_ships_the_same_file(self):
        for c in COPIES:
            self.assertTrue(c.is_file(), f"missing {c}")
            self.assertTrue(filecmp.cmp(SRC, c, shallow=False), f"{c} differs from {SRC}")


if __name__ == "__main__":
    unittest.main(verbosity=1)
