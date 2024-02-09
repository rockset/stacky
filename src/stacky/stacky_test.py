#!/usr/bin/env python3
import unittest
from unittest import mock
from unittest.mock import MagicMock
from stacky import PRInfos, read_config, get_top_level_dir


class TestStringMethods(unittest.TestCase):
    def test_upper(self):
        self.assertEqual("foo".upper(), "FOO")

    def test_isupper(self):
        self.assertTrue("FOO".isupper())
        self.assertFalse("Foo".isupper())

    def test_split(self):
        s = "hello world"
        self.assertEqual(s.split(), ["hello", "world"])
        # check that s.split fails when the separator is not a string
        with self.assertRaises(TypeError):
            s.split(2)

    @mock.patch("get_top_level_dir")
    def test_read_config(self, mock_get_tld):
        patcher = mock.patch("os.path.exists")
        mock_thing = patcher.start()
        mock_thing.return_value = False
        read_config()


if __name__ == "__main__":
    unittest.main()
