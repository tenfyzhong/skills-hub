import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT_PATH = SKILL_DIR / "scripts" / "scaffold_project.py"


def load_scaffold_module():
    spec = importlib.util.spec_from_file_location("scaffold_project", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class NodeSpecTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scaffold = load_scaffold_module()

    def test_defaults_to_small_instance(self):
        name, node = self.scaffold.parse_node_spec("api=2")

        self.assertEqual(name, "api")
        self.assertEqual(
            node,
            {
                "count": 2,
                "cpu": 2,
                "memory_gib": 4,
                "instance_type": "t3.medium",
            },
        )

    def test_resolves_cpu_and_memory_to_instance_type(self):
        name, node = self.scaffold.parse_node_spec("worker=3:4:8")

        self.assertEqual(name, "worker")
        self.assertEqual(node["count"], 3)
        self.assertEqual(node["cpu"], 4)
        self.assertEqual(node["memory_gib"], 8)
        self.assertEqual(node["instance_type"], "c7i.xlarge")

    def test_rejects_duplicate_names(self):
        with self.assertRaisesRegex(ValueError, "duplicate node group"):
            self.scaffold.collect_node_groups(["api=1", "api=2"])

    def test_rejects_unavailable_size(self):
        with self.assertRaisesRegex(ValueError, "no supported instance type"):
            self.scaffold.parse_node_spec("huge=1:128:1024")


class ScaffoldProjectTest(unittest.TestCase):
    def test_creates_self_contained_terraform_project(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            target = root / "deployment"
            public_key = root / "id_ed25519.pub"
            public_key.write_text("ssh-ed25519 AAAAC3NzaTest test@example\n")

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--target",
                    str(target),
                    "--namespace",
                    "test-nodes",
                    "--node",
                    "api=2",
                    "--node",
                    "worker=1:4:8",
                    "--aws-profile",
                    "sandbox",
                    "--region",
                    "us-east-1",
                    "--ssh-cidr",
                    "203.0.113.10/32",
                    "--public-key",
                    str(public_key),
                ],
                capture_output=True,
                check=False,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(str(target.resolve()), result.stdout)
            self.assertTrue((target / "README.md").is_file())
            self.assertTrue((target / "deployment.json").is_file())
            self.assertTrue((target / "terraform.tfvars.json").is_file())

            variables = json.loads((target / "terraform.tfvars.json").read_text())
            self.assertEqual(variables["aws_profile"], "sandbox")
            self.assertEqual(variables["region"], "us-east-1")
            self.assertEqual(variables["ssh_cidr"], "203.0.113.10/32")
            self.assertEqual(variables["node_groups"]["api"]["count"], 2)
            self.assertEqual(
                variables["node_groups"]["worker"]["instance_type"],
                "c7i.xlarge",
            )

            main = (target / "main.tf").read_text()
            network = (target / "network.tf").read_text()
            outputs = (target / "outputs.tf").read_text()
            self.assertIn('resource "aws_instance" "node"', main)
            self.assertIn('resource "aws_eip" "node"', main)
            self.assertIn('resource "aws_internet_gateway" "main"', network)
            self.assertIn('resource "aws_route_table" "public"', network)
            self.assertIn('resource "aws_security_group_rule" "internal"', network)
            self.assertIn('output "public_ips"', outputs)
            self.assertIn('output "ssh_commands"', outputs)


if __name__ == "__main__":
    unittest.main()
