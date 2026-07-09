from pathlib import Path
import unittest


class CompilerPackageTests(unittest.TestCase):
    def test_config_compiler_declares_crt_dependency(self):
        root = Path(__file__).resolve().parents[1]
        requirements = root / "requirements-config-compiler.txt"
        lambda_tf = root / "terraform" / "lambda.tf"

        self.assertIn("awscrt==", requirements.read_text())
        self.assertIn("requirements-config-compiler.txt", lambda_tf.read_text())
        self.assertIn("manylinux2014_x86_64", lambda_tf.read_text())


if __name__ == "__main__":
    unittest.main()
