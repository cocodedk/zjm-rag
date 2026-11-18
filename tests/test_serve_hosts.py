import os
import sys
import threading
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))
from test_safety import _req, _run_cli

from zjm_rag.http import make_server


def _serve(case, **kw):
    server = make_server(port=0, **kw)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    case.addCleanup(server.server_close)
    case.addCleanup(server.shutdown)
    return f"http://127.0.0.1:{server.server_address[1]}"


class ServeHostsTest(unittest.TestCase):
    def test_listed_host_is_accepted(self):
        base = _serve(self, allow_hosts=("zjm",))
        self.assertEqual(_req(base, "/health", headers={"Host": "zjm:8765"}), 200)
        self.assertEqual(_req(base, "/health", headers={"Host": "other:8765"}), 403)
        self.assertEqual(_req(base, "/health", headers={"Origin": "http://zjm"}), 403)

    def test_nothing_listed_is_unchanged(self):
        base = _serve(self)
        self.assertEqual(_req(base, "/health", headers={"Host": "zjm:8765"}), 403)
        self.assertEqual(_req(base, "/health"), 200)

    def test_cli_passes_allow_host(self):
        server = mock.Mock()
        server.server_address = ("127.0.0.1", 0)
        server.serve_forever.side_effect = KeyboardInterrupt
        with mock.patch.dict(os.environ, {"ZJM_IN_CONTAINER": "1"}), \
                mock.patch("zjm_rag.http.make_server", return_value=server) as fake:
            code, _, err = _run_cli(["serve", "--allow-host", "zjm", "--allow-host", "db"])
        self.assertEqual(code, 0, err)
        self.assertEqual(set(fake.call_args.kwargs["allow_hosts"]), {"zjm", "db"})


if __name__ == "__main__":
    unittest.main()
