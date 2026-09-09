import json
import tempfile
import unittest
from pathlib import Path

from rom_unifier.dats import filter_clrmamepro
from rom_unifier.config import load as load_config
from rom_unifier.detection import detect
from rom_unifier.inventory import scan
from rom_unifier.playlists import build, verify
from rom_unifier.registry import Platform
from rom_unifier.simple import create_plan


class DatTests(unittest.TestCase):
    def test_filter_keeps_only_canonical_extension(self):
        source_text = '''clrmamepro (\n name "Example"\n)\ngame (\n name "A"\n rom ( name "A.bin" size 1 crc 00 )\n)\ngame (\n name "A"\n rom ( name "A.a78" size 2 crc 01 )\n)\n'''
        with tempfile.TemporaryDirectory() as temp:
            source, target = Path(temp) / "in.dat", Path(temp) / "out.dat"
            source.write_text(source_text)
            self.assertEqual(filter_clrmamepro(source, target, "bin"), 1)
            result = target.read_text()
            self.assertIn("A.bin", result)
            self.assertNotIn("A.a78", result)


class ConfigTests(unittest.TestCase):
    def test_empty_required_paths_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            config = Path(temp) / "config.toml"
            config.write_text('[paths]\nsource = ""\ndestination = ""\n')
            with self.assertRaisesRegex(ValueError, "configuration required"):
                load_config(config)

    def test_work_paths_derive_beside_destination(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = root / "config.toml"
            config.write_text(f'[paths]\nsource = "{root / "incoming"}"\ndestination = "{root / "archive"}"\n')
            paths = load_config(config).paths
            self.assertEqual(paths["tools"], root / "tools")
            self.assertEqual(paths["backups"], root / "backups/rom-unifier")


class InventoryTests(unittest.TestCase):
    def test_alias_and_extension_detection(self):
        platform = Platform("nds", "Nintendo DS", "cartridge", ("nds", "zip"), "nds", ("NDS",), "nds")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / "bundle" / "NDS"
            folder.mkdir(parents=True)
            (folder / "game.zip").write_bytes(b"PK")
            result = scan(root, {"nds": platform})
            self.assertEqual(result["platforms"]["nds"]["files"], 1)

    def test_detection_uses_alias_and_archive_member_type(self):
        import zipfile
        platform = Platform("psx", "PlayStation", "disc", ("chd", "cue", "bin", "zip"), "chd", ("ps", "ps1", "psx"), "psx")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "source"
            folder = root / "PS1"
            folder.mkdir(parents=True)
            (folder / "Example.chd").write_bytes(b"not-a-real-chd")
            result = detect(root, {"psx": platform}, Path(temp) / "dats")
            self.assertEqual(result[0].platform, "psx")
            self.assertGreaterEqual(result[0].confidence, 0.60)


class PlaylistTests(unittest.TestCase):
    def test_builds_relative_multidisc_layout(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for number in (1, 2):
                (root / f"Example Game (USA) (Disc {number}).chd").write_bytes(bytes([number]))
            self.assertEqual(build(root, execute=True), 1)
            playlist = root / "Example Game (USA)" / "Example Game (USA).m3u"
            self.assertEqual(playlist.read_text().splitlines(), [
                "Example Game (USA) (Disc 1).chd", "Example Game (USA) (Disc 2).chd"
            ])
            self.assertEqual(verify(root), 1)


class SimpleModeTests(unittest.TestCase):
    def test_plan_is_saved_with_specific_candidate_actions(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, destination = root / "incoming", root / "archive"
            folder = source / "PS1"
            folder.mkdir(parents=True)
            destination.mkdir()
            (folder / "Known Game.chd").write_bytes(b"CHD")
            config = root / "config.toml"
            config.write_text(f'[paths]\nsource = "{source}"\ndestination = "{destination}"\n[runtime]\ndetection_min_confidence = 0.6\n')
            settings = load_config(config)
            psx = Platform("psx", "PlayStation", "disc", ("chd",), "chd", ("ps", "ps1", "psx"), "psx", playlist=True)
            plan = create_plan(settings, {"psx": psx})
            payload = json.loads(plan.read_text())
            self.assertEqual(payload["operations"][0]["candidate_actions"][0]["action"], "candidate-add")
            self.assertTrue((settings.paths["processing"] / "plans/latest.json").exists())


if __name__ == "__main__":
    unittest.main()
