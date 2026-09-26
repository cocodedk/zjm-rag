import json
import tempfile
import unittest
from pathlib import Path

from zjm_rag import ZjmError
from zjm_rag import config as config_module


def write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj))


class ConfigTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.environ = {"HOME": str(self.tmp / "home")}

    def test_lookup_order(self):
        explicit = self.tmp / "explicit.json"
        write(explicit, {"embedding": "local/explicit"})
        env_path = self.tmp / "env.json"
        write(env_path, {"embedding": "local/env"})
        cwd = self.tmp / "project"
        cwd_conf = cwd / ".zjm" / "config.json"
        write(cwd_conf, {"embedding": "local/cwd"})
        parent_conf = self.tmp / ".zjm" / "config.json"
        write(parent_conf, {"embedding": "local/parent"})
        xdg = self.tmp / "xdg"
        xdg_conf = xdg / "zjm" / "config.json"
        write(xdg_conf, {"embedding": "local/xdg"})
        environ = {**self.environ, "ZJM_CONFIG": str(env_path), "XDG_CONFIG_HOME": str(xdg)}

        self.assertEqual(config_module.load(str(explicit), cwd=str(cwd), environ=environ)["embedding"],
                         "local/explicit")
        self.assertEqual(config_module.load(cwd=str(cwd), environ=environ)["embedding"], "local/env")
        self.assertEqual(config_module.load(cwd=str(cwd), environ=self.environ | {"XDG_CONFIG_HOME": str(xdg)})
                         ["embedding"], "local/cwd")
        self.assertEqual(config_module.load(cwd=str(no_cwd_conf := self.tmp / "nowhere"),
                                            environ=self.environ | {"XDG_CONFIG_HOME": str(xdg)})["embedding"],
                         "local/xdg")
        no_cwd_conf = self.tmp / "nowhere"
        self.assertEqual(config_module.load(cwd=str(no_cwd_conf), environ=self.environ)["embedding"],
                         "local/potion-code-16m-v2")

    def test_bad_config_names_file(self):
        bad_key = self.tmp / "bad_key.json"
        write(bad_key, {"nope": 1})
        bad_egress = self.tmp / "bad_egress.json"
        write(bad_egress, {"egress": {"nope": True}})
        bad_type = self.tmp / "bad_type.json"
        write(bad_type, {"allow": "not-a-list"})
        bad_json = self.tmp / "bad.json"
        bad_json.write_text("{not json")
        bad_embedding = self.tmp / "bad_embedding.json"
        write(bad_embedding, {"embedding": "openai/gpt"})
        for path in (bad_key, bad_egress, bad_type, bad_json, bad_embedding):
            with self.assertRaisesRegex(ZjmError, str(path)):
                config_module.load(str(path), environ=self.environ)
        missing = self.tmp / "missing.json"
        with self.assertRaisesRegex(ZjmError, str(missing)):
            config_module.load(str(missing), environ=self.environ)

    def test_defaults(self):
        environ = {**self.environ, "XDG_DATA_HOME": str(self.tmp / "xdg-data")}
        cfg = config_module.load(cwd=str(self.tmp / "nowhere"), environ=environ)
        self.assertEqual(cfg["home"], str(self.tmp / "xdg-data" / "zjm"))
        self.assertEqual(cfg["allow"], [])
        self.assertEqual(cfg["egress"], {"rank": False, "answer": False, "translate": False})
        self.assertIsNone(cfg["path"])
        rank_only = self.tmp / "rank_only.json"
        write(rank_only, {"egress": {"rank": True}})
        cfg2 = config_module.load(str(rank_only), environ=self.environ)
        self.assertEqual(cfg2["egress"], {"rank": True, "answer": False, "translate": False})


if __name__ == "__main__":
    unittest.main()
