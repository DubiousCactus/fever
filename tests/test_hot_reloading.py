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

    def test_nested_functions_level_one(self):
        from submodules.module_e import nested_functions  # noqa: F401

        res = nested_functions()
        self.assertEqual(res, len("nested_a calls nested_b: 123"))
        fpath = "tests/test_imports/submodules/module_e.py"
        replace_on_disk(
            fpath,
            """def nested_functions() -> int:\n    def nested_a() -> str:\n        def nested_b() -> int:\n            return 123\n\n        return f"nested_a calls nested_b: {nested_b()}"\n\n    return len(nested_a())""",
            """def nested_functions() -> int:\n    def nested_a() -> str:\n        def nested_b() -> int:\n            return 123\n\n        return f"nested_a calls modified nested_b: {nested_b()}"\n\n    return len(nested_a())""",
        )
        self.fever.reload()
        res = nested_functions()
        self.assertEqual(res, len("nested_a calls modified nested_b: 123"))

    def test_nested_functions_level_two(self):
        from submodules.module_e import nested_functions  # noqa: F401

        res = nested_functions()
        self.assertEqual(res, len("nested_a calls nested_b: 123"))
        fpath = "tests/test_imports/submodules/module_e.py"
        replace_on_disk(
            fpath,
            """def nested_functions() -> int:\n    def nested_a() -> str:\n        def nested_b() -> int:\n            return 123\n\n        return f"nested_a calls nested_b: {nested_b()}"\n\n    return len(nested_a())""",
            """def nested_functions() -> int:\n    def nested_a() -> str:\n        def nested_b() -> int:\n            return 123456\n\n        return f"nested_a calls nested_b: {nested_b()}"\n\n    return len(nested_a())""",
        )
        self.fever.reload()
        res = nested_functions()
        self.assertEqual(res, len("nested_a calls nested_b: 123456"))

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

    def test_new_function(self):
        import module_a  # noqa: F401
        import module_c  # noqa: F401

        self.assertIn("module_c", sys.modules)
        self.assertIn("module_c", self.fever.dependency_tracker.all_imports)
        res: bool = module_c.other_function("test")
        self.assertTrue(res)

        fpath = "tests/test_imports/module_c.py"
        with open(fpath, "a") as f:
            f.write(
                """def new_function() -> str:\n    return "I think therefore I am"\n"""
            )
            f.flush()
        self.fever.reload()
        self.assertTrue(hasattr(module_c, "new_function"))
        res: bool = module_c.other_function("test")
        new_res: str = module_c.new_function()
        self.assertTrue(res)
        self.assertEqual(new_res, "I think therefore I am")

    def test_new_method(self):
        import module_d  # noqa: F401

        obj = module_d.MiniTestClass("testy soldier")
        self.assertEqual(len(obj), 10)

        fpath = "tests/test_imports/module_d.py"
        with open(fpath, "a") as f:
            f.write("""    def new_method(self) -> int:\n        return 100\n""")
            f.flush()
        self.fever.reload()
        self.assertTrue(hasattr(obj, "new_method"))
        self.assertEqual(len(obj), 10)
        self.assertEqual(obj.new_method(), 100)

    def test_new_class(self):
        import module_a  # noqa: F401
        import module_c  # noqa: F401

        self.assertIn("module_c", sys.modules)
        self.assertIn("module_c", self.fever.dependency_tracker.all_imports)
        res: bool = module_c.other_function("test")
        self.assertTrue(res)

        fpath = "tests/test_imports/module_c.py"
        with open(fpath, "a") as f:
            f.write(
                """\n\nclass TestClass:\n    def call_me_baby(self):\n        return "Hey, I just met you!"\n"""
            )
            f.flush()
        self.fever.reload()
        print(dir(module_c))
        self.assertTrue(hasattr(module_c, "TestClass"))
        self.assertFalse(hasattr(module_c, "call_me_baby"))
        res: bool = module_c.other_function("test")
        new_res: str = module_c.TestClass().call_me_baby()
        self.assertTrue(res)
        self.assertEqual(new_res, "Hey, I just met you!")

    def test_function_with_packages(self):
        import numpy as np  # noqa: F401
        from submodules.module_e import function_foreign_imports  # noqa: F401

        array = function_foreign_imports()
        self.assertTrue(isinstance(array, np.ndarray))
        self.assertTrue((array == np.array([2, 4, 6])).all())

        fpath = "tests/test_imports/submodules/module_e.py"
        replace_on_disk(
            fpath,
            """def function_foreign_imports() -> np.ndarray:\n    x = np.array([1, 2, 3])\n    return x * 2""",
            """def function_foreign_imports() -> np.ndarray:\n    x = np.array([1, 2, 3])\n    return x * 3""",
        )
        self.fever.reload()
        array = function_foreign_imports()
        self.assertTrue(isinstance(array, np.ndarray))
        self.assertTrue((array == np.array([3, 6, 9])).all())

    def test_two_new_functions_with_ordered_dependency(self):
        import module_a  # noqa: F401

        fpath = "tests/test_imports/module_a.py"
        with open(fpath, "a") as f:
            f.write(
                """\n\ndef new_fn_a():\n    return 123\n\ndef new_fn_b():\n    return new_fn_a()+1"""
            )
            f.flush()
        self.fever.reload()
        self.assertTrue(hasattr(module_a, "new_fn_a"))
        self.assertTrue(hasattr(module_a, "new_fn_b"))
        res_a = module_a.new_fn_a()
        res_b = module_a.new_fn_b()
        self.assertEqual(res_a, 123)
        self.assertEqual(res_b, 124)

    @unittest.skip(
        "We don't currently handle unordered dependencies for new function definitions."
    )
    def test_two_new_functions_with_unordered_dependency(self):
        import module_a  # noqa: F401

        fpath = "tests/test_imports/module_a.py"
        with open(fpath, "a") as f:
            f.write(
                """\n\ndef new_fn_a():\n    return new_fn_b()*3\n\ndef new_fn_b():\n    return 1"""
            )
            f.flush()
        self.fever.reload()
        self.assertTrue(hasattr(module_a, "new_fn_a"))
        self.assertTrue(hasattr(module_a, "new_fn_b"))
        res_a = module_a.new_fn_a()
        res_b = module_a.new_fn_b()
        self.assertEqual(res_a, 3)
        self.assertEqual(res_b, 1)

    def test_new_function_with_new_import(self):
        import module_a  # noqa: F401
        import numpy as np  # noqa: F401

        self.assertFalse(hasattr(module_a, "function_with_numpy"))
        fpath = "tests/test_imports/module_a.py"
        with open(fpath, "a") as f:
            f.write(
                """\n\nimport numpy as np\n\ndef function_with_numpy() -> np.ndarray:\n    a = np.array([4, 5, 6])\n    return a + 1\n"""
            )
            f.flush()
        self.fever.reload()
        self.assertTrue(hasattr(module_a, "function_with_numpy"))
        res = module_a.function_with_numpy()
        self.assertTrue(isinstance(res, np.ndarray))
        self.assertTrue((res == np.array([5, 6, 7])).all())

    def test_new_function_with_new_subimports(self):
        import module_a  # noqa: F401
        from numpy import array, ndarray  # noqa: F401

        self.assertFalse(hasattr(module_a, "function_with_numpy_array"))
        fpath = "tests/test_imports/module_a.py"
        with open(fpath, "a") as f:
            f.write(
                """\n\nfrom numpy import array\n\ndef function_with_numpy_array() -> array:\n    a = array([7, 8, 9])\n    return a + 2\n"""
            )
            f.flush()
        self.fever.reload()
        self.assertTrue(hasattr(module_a, "function_with_numpy_array"))
        res = module_a.function_with_numpy_array()
        self.assertTrue(isinstance(res, ndarray))
        self.assertTrue((res == array([9, 10, 11])).all())

    def test_new_function_with_new_subimports_multiple(self):
        import module_a  # noqa: F401
        from numpy import array, linalg, ndarray  # noqa: F401

        self.assertFalse(hasattr(module_a, "function_with_numpy_array"))
        fpath = "tests/test_imports/module_a.py"
        with open(fpath, "a") as f:
            f.write(
                """\n\nfrom numpy import array, linalg, ndarray\n\ndef function_with_numpy_array() -> ndarray:\n    a = array([7, 8, 9])\n    return linalg.norm(a + 2)\n"""
            )
            f.flush()
        self.fever.reload()
        self.assertTrue(hasattr(module_a, "function_with_numpy_array"))
        res = module_a.function_with_numpy_array()
        self.assertTrue(isinstance(res, float))
        self.assertEqual(res, linalg.norm(array([9, 10, 11])))
