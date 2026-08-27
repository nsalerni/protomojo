#!/usr/bin/env python3
"""Tests for proto3 JSON mutation oracle rules."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_json_fuzz as json_fuzz


class JsonFuzzOracleTests(unittest.TestCase):
    def test_empty_iterables_are_not_proto3_message_objects(self):
        for text in ('""', "[]", "null", "true", "0"):
            with self.subTest(text=text):
                with self.assertRaises(Exception):
                    json_fuzz.proto3_json_message_value(text)

    def test_object_roots_are_accepted(self):
        self.assertEqual(json_fuzz.proto3_json_message_value("{}"), {})
        self.assertEqual(
            json_fuzz.proto3_json_message_value(' {"int32Values":{}} '),
            {"int32Values": {}},
        )

    def test_python_protobuf_empty_iterables_are_not_oracles(self):
        with tempfile.TemporaryDirectory() as tmp:
            _vectors_pb2, message_types = json_fuzz.compile_python_messages(
                Path(tmp)
            )
            maps = message_types["maps"]
            for text in ('""', "[]"):
                with self.subTest(text=text):
                    message, error = json_fuzz.python_parse(maps, text)
                    self.assertIsNone(message)
                    self.assertIsNotNone(error)

            message, error = json_fuzz.python_parse(maps, "{}")
            self.assertIsNone(error)
            self.assertIsNotNone(message)


if __name__ == "__main__":
    unittest.main()
