import os
import shutil
import sys
import unittest

from fever import Fever


def replace_on_disk(file_path: str, replace_str: str, replacement_str: str):
    with open(file_path, "r") as f:
        original_code = f.read()
    with open(file_path, "w") as f:
        modified_code = original_code.replace(
            replace_str,
            replacement_str,
        )
        f.write(modified_code)
        f.flush()


class TestHotReloading(unittest.TestCase):
    def setUp(self):
        sys.path.append(os.path.join(os.getcwd(), "tests/test_imports"))
        self.fever = Fever()
        self.fever.setup()
        shutil.copytree(
            "tests/test_imports", "tmp_test_imports_backup", dirs_exist_ok=True
        )

    def tearDown(self):
        self.fever.cleanup()
        cleanup_modules = [
            "module_a",
            "module_b",
            "module_c",
            "module_d",
            "module_e",
            "module_f",
            "module_z",
            "submodules",
            "submodules.module_e",
            "subsub",
            "submodules.subsub",
            "submodules.subsub.module_f",
        ]
        for mod in list(sys.modules.keys()):
            if mod in cleanup_modules:
                del sys.modules[mod]
        for k in locals().keys():
            del locals()[k]
        shutil.rmtree("tests/test_imports")
        shutil.copytree("tmp_test_imports_backup", "tests/test_imports")
        sys.path.pop()

    def test_simple_function(self):
        import module_d  # noqa: F401

        res = module_d.function_d("test")
        self.assertEqual(res, 123)

        fpath = "tests/test_imports/module_d.py"
        replace_on_disk(
            fpath,
            """def function_d(name: str) -> int:\n    print(f"Nothing to show here, {name}")\n    return 123""",
            """def function_d(name: str) -> int:\n    print(f"Nothing to show here, {name}")\n    return 456""",
        )
        self.fever.reload()
        res = module_d.function_d("test")
        self.assertEqual(res, 456)

    def test_simple_function_changed_other(self):
        import module_d  # noqa: F401

        res = module_d.other_function_d("test")
        self.assertEqual(res, 321)

        fpath = "tests/test_imports/module_d.py"
        replace_on_disk(
            fpath,
            """def function_d(name: str) -> int:\n    print(f"Nothing to show here, {name}")\n    return 123""",
            """def function_d(name: str) -> int:\n    print(f"Nothing to show here, {name}")\n    return 456""",
        )
        self.fever.reload()
        res = module_d.other_function_d("test")
        self.assertEqual(res, 321)

    def test_simple_function_changed_other_call_both(self):
        import module_d  # noqa: F401

        res_unchanged = module_d.other_function_d("test")
        res_changed = module_d.function_d("test")
        self.assertEqual(res_unchanged, 321)
        self.assertEqual(res_changed, 123)

        fpath = "tests/test_imports/module_d.py"
        replace_on_disk(
            fpath,
            """def function_d(name: str) -> int:\n    print(f"Nothing to show here, {name}")\n    return 123""",
            """def function_d(name: str) -> int:\n    print(f"Nothing to show here, {name}")\n    return 456""",
        )
        self.fever.reload()
        res_unchanged = module_d.other_function_d("test")
        res_changed = module_d.function_d("test")
        self.assertEqual(res_unchanged, 321)
        self.assertEqual(res_changed, 456)

    def test_simple_method(self):
        import module_d  # noqa: F401

        obj = module_d.TestClass()
        self.assertEqual(obj.return_string(), "just a string")

        fpath = "tests/test_imports/module_d.py"
        replace_on_disk(
            fpath,
            """    def return_string(self) -> str:\n        return "just a string"\n""",
            """    def return_string(self) -> str:\n        return "not just a string"\n""",
        )
        self.fever.reload()
        self.assertEqual(obj.return_string(), "not just a string")

    def test_call_magic_method(self):
        import module_d  # noqa: F401

        obj = module_d.MiniTestClass("testy boy")
        self.assertEqual(obj(), "testy boy")

        fpath = "tests/test_imports/module_d.py"
        replace_on_disk(
            fpath,
            """    def __call__(self) -> str:\n        return self._name""",
            """    def __call__(self) -> str:\n        return 'oh la la!'""",
        )
        self.fever.reload()
        self.assertEqual(obj(), "oh la la!")

    def test_len_magic_method(self):
        import module_d  # noqa: F401

        obj = module_d.MiniTestClass("testy boy")
        self.assertEqual(len(obj), 10)

        fpath = "tests/test_imports/module_d.py"
        replace_on_disk(
            fpath,
            """    def __len__(self) -> int:\n        return 10""",
            """    def __len__(self) -> int:\n        return 20""",
        )
        self.fever.reload()
        self.assertEqual(len(obj), 20)

    def test_init_method(self):
        import module_d  # noqa: F401

        obj = module_d.MiniTestClass("testy boy")
        self.assertEqual(str(obj), "My name is testy boy")

        fpath = "tests/test_imports/module_d.py"
        replace_on_disk(
            fpath,
            """    def __init__(self, name: str):\n        self._name = name""",
            """    def __init__(self, name: str):\n        self._name = 'testy girl'""",
        )
        self.fever.reload()
        obj = module_d.MiniTestClass("testy boy")
        self.assertEqual(str(obj), "My name is testy girl")

    # def test_decorated_function(self):
    #     raise NotImplementedError
    #
    # def test_decorated_method(self):
    #     raise NotImplementedError

    def test_circular(self):
        import module_a  # noqa: F401

        res = module_a.function()
        self.assertEqual(res, "hello world")
        fpath = "tests/test_imports/module_a.py"
        replace_on_disk(
            fpath,
            """def function() -> str:\n    print("test.function()")\n    test_module = TestCase()\n    return test_module.elaborate_function("world", [False, False, False])""",
            """def function() -> str:\n    print("test.function()")\n    test_module = TestCase()\n    return test_module.elaborate_function("earth", [False, False, False])""",
        )
        self.fever.reload()
        res = module_a.function()
        self.assertEqual(res, "hello earth")

    def test_circular_lambda_calls(self):
        import module_a  # noqa: F401

        res = module_a.function_with_lambda_call()
        self.assertEqual(res, "hello WORLD")
        fpath = "tests/test_imports/module_a.py"
        replace_on_disk(
            fpath,
            """def function_with_lambda_call() -> str:\n    print("test.function_with_lambda_call()")\n    test_module = TestCase()\n    return test_module.elaborate_function("world", [True, False, True])""",
            """def function_with_lambda_call() -> str:\n    print("test.function_with_lambda_call()")\n    test_module = TestCase()\n    return test_module.elaborate_function("earth", [True, False, True])""",
        )
        self.fever.reload()
        res = module_a.function_with_lambda_call()
        self.assertEqual(res, "hello EARTH")

    def test_circular_two_calls(self):
        import module_a  # noqa: F401

        res = module_a.function_deep_nested()
        self.assertEqual(res, "hello world")
        fpath = "tests/test_imports/module_a.py"
        replace_on_disk(
            fpath,
            """def function_deep_nested() -> str:\n    print("test.function_deep_nested()")\n    test_module = TestCase()\n    test_module()\n    return test_module.elaborate_function("world", [False, False, False])""",
            """def function_deep_nested() -> str:\n    print("test.function_deep_nested()")\n    test_module = TestCase()\n    test_module()\n    return test_module.elaborate_function("earth", [False, False, False])""",
        )
        self.fever.reload()
        res = module_a.function_deep_nested()
        self.assertEqual(res, "hello earth")

    def test_from_import_function(self):
        from module_d import function_d  # noqa: F401

        res = function_d("test")
        self.assertEqual(res, 123)

        fpath = "tests/test_imports/module_d.py"
        replace_on_disk(
            fpath,
            """def function_d(name: str) -> int:\n    print(f"Nothing to show here, {name}")\n    return 123""",
            """def function_d(name: str) -> int:\n    print(f"Nothing to show here, {name}")\n    return 456""",
        )
        self.fever.reload()
        res = function_d("test")
        self.assertEqual(res, 456)
