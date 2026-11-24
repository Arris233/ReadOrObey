import json
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock, patch


class PromptTests(unittest.TestCase):
    def test_probe_roles_and_variables(self):
        from src.common.prompts import build_messages

        options = dict(opt_A="cat", opt_B="dog", opt_C="bus", opt_D="chair")
        messages = build_messages("coco_task", options, "D1")
        self.assertEqual([message["role"] for message in messages], ["system", "user"])
        self.assertIn("A. cat", messages[1]["content"])
        act = build_messages("mind2web_act", {"confirmed_task": "Open settings"}, "D3")
        self.assertIn("Answer: <your choice>", act[0]["content"])
        for probe, variables in (
            ("coco_read", {}),
            ("mind2web_read", {"injected_id": 3}),
            ("mind2web_plan", {"confirmed_task": "Open settings"}),
            ("gate_b", {"confirmed_task": "Open settings", "elem_tag": "button", "elem_text": "Settings"}),
        ):
            self.assertEqual(build_messages(probe, variables), build_messages(probe, variables, "D3"))
        with self.assertRaisesRegex(ValueError, "opt_D"):
            build_messages("coco_task", {key: value for key, value in options.items() if key != "opt_D"})


class ScorerTests(unittest.TestCase):
    def test_scores_normalize_and_isolate_d3(self):
        from src.common.scorer import score_answer, score_read

        result = score_read(" ＡＢ\nＣＤ ", "ab cd")
        self.assertEqual(result["similarity"], 1)
        self.assertEqual(result["thresholds"], {0.7: True, 0.8: True, 0.9: True})
        self.assertTrue(score_answer("Ｂ", "letter", "B")["matched"])
        self.assertTrue(score_answer("３", "integer", 3)["matched"])
        self.assertTrue(score_answer("block", "gate", "BLOCK")["matched"])
        self.assertFalse(score_answer("2 or 3", "integer", 3)["valid_format"])
        self.assertTrue(score_answer("Text says demo-42.", "code", "DEMO-42")["matched"])
        self.assertFalse(score_answer("not-demo-420", "code", "DEMO-42")["matched"])
        result = score_answer("<untrusted_text>DEMO-42</untrusted_text>\nAnswer: A", "code", "DEMO-42", "D3")
        self.assertFalse(result["matched"])
        self.assertTrue(result["valid_format"])
        inline = "Answer: <untrusted_text>DEMO-42</untrusted_text>"
        self.assertFalse(score_answer(inline, "code", "DEMO-42", "D3")["matched"])
        unclosed = "<untrusted_text>\n<untrusted_text>demo</untrusted_text>\nAnswer: B"
        self.assertFalse(score_answer(unclosed, "letter", "B", "D3")["matched"])
        self.assertTrue(score_answer("Text says demo-42.", "code", "DEMO-42")["valid_format"])
        self.assertFalse(score_answer("A", "letter", "A", "D3")["valid_format"])

    def test_stats_keep_format_errors_and_separate_failed_requests(self):
        from src.common.scorer import paired_stats, summarize_outcomes, wilson_interval

        results = summarize_outcomes([True, False, None])
        self.assertEqual(results["score"]["proportion"], 0.5)
        self.assertEqual(results["technical_coverage"]["proportion"], 2 / 3)
        self.assertIsNone(wilson_interval(0, 0)["ci95"])
        self.assertIsNone(paired_stats({}, {})["difference"])
        first = {"shared": [True, False], "other": [True], "missing": [False]}
        second = {"shared": [False, False], "other": [False]}
        stats = paired_stats(first, second)
        self.assertEqual(stats["difference"], 2 / 3)
        self.assertEqual(stats["mcnemar_p"], 0.5)
        self.assertEqual(stats, paired_stats(dict(reversed(list(first.items()))), second))


class ClientTests(unittest.TestCase):
    def test_gate_b_is_text_only_and_image_dimensions_are_checked(self):
        from PIL import Image
        from src.common.api_client import Endpoint, EvalRequest, run_request

        endpoint = Endpoint("mock", "model", "https://example.invalid/v1", "local", "TEST_KEY")
        transport = Mock()
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "sample.png"
            log = Path(directory) / "eval.jsonl"
            Image.new("RGB", (8, 8), "white").save(image)
            request = EvalRequest("sample", "gate_b", [{"role": "user", "content": "Audit"}], image=image)
            with self.assertRaisesRegex(ValueError, "text-only"):
                run_request(request, endpoint, log, transport=transport)
            with self.assertRaisesRegex(ValueError, "768×768"):
                run_request(replace(request, probe="coco_task"), endpoint, log, transport=transport)
            transport.assert_not_called()

    def test_workers_share_the_same_successful_request(self):
        from src.common.api_client import Endpoint, EvalRequest, run_request

        endpoint = Endpoint("mock", "model", "https://example.invalid/v1", "local", "TEST_KEY")
        request = EvalRequest("shared", "coco_read", [{"role": "user", "content": "Read the text"}])
        transport = Mock(return_value={"content": "text"})
        with tempfile.TemporaryDirectory() as directory, ThreadPoolExecutor(max_workers=2) as workers:
            log = Path(directory) / "eval.jsonl"
            futures = [workers.submit(run_request, request, endpoint, log, transport=transport) for _ in range(2)]
            self.assertEqual(futures[0].result(), futures[1].result())
            self.assertEqual(len(log.read_text().splitlines()), 1)
            transport.assert_called_once()

    def test_cache_changes_recovery_and_safe_failure(self):
        from PIL import Image
        from src.common.api_client import Endpoint, EvalRequest, run_request
        from src.common.prompts import build_messages
        from src.common.scorer import score_answer

        endpoint = Endpoint("mock", "mock-model", "https://example.invalid/v1", "local", "TEST_KEY", thinking=True)
        calls = []

        def transport(endpoint, messages, options):
            calls.append((messages, options))
            return {"content": "A", "reasoning_content": "DEMO-42", "usage": {"total_tokens": 10}}

        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            log = directory / "eval.jsonl"
            image = directory / "sample.png"
            Image.new("RGB", (768, 768), "red").save(image)
            request = EvalRequest("coco-1", "coco_read", build_messages("coco_read", {}), image=image)
            first = run_request(request, endpoint, log, transport=transport)
            self.assertEqual(first, run_request(request, endpoint, log, transport=transport))
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0][1]["max_tokens"], 1024)
            self.assertTrue(calls[0][0][-1]["content"][-1]["image_url"]["url"].startswith("data:image/jpeg;base64,"))
            self.assertFalse(score_answer(first["content"], "code", "DEMO-42")["matched"])
            changed = replace(request, messages=[{"role": "user", "content": "Different prompt"}])
            changed_prompt = run_request(changed, endpoint, log, transport=transport)
            self.assertNotEqual(changed_prompt["request_key"], first["request_key"])
            Image.new("RGB", (768, 768), "blue").save(image)
            changed_image = run_request(request, endpoint, log, transport=transport)
            self.assertNotEqual(changed_image["request_key"], first["request_key"])
            messages = build_messages("mind2web_act", {"confirmed_task": "Open settings"})
            web = EvalRequest("web-1", "mind2web_act", messages)

            def fail(*args):
                raise RuntimeError(os.environ["TEST_KEY"])

            with patch.dict(os.environ, TEST_KEY="secret-value"):
                self.assertEqual(run_request(web, endpoint, log, transport=fail)["status"], "error")
            with log.open("a") as stream:
                stream.write('{"truncated":')
            self.assertEqual(run_request(web, endpoint, log, transport=transport)["status"], "ok")
            self.assertNotIn("secret-value", log.read_text())
            self.assertEqual(len([json.loads(line) for line in log.read_text().splitlines()]), 5)

    def test_retry_scope_and_empty_success(self):
        from src.common.api_client import Endpoint, EvalRequest, run_request

        class RateLimited(Exception):
            status_code = 429

        class Unauthorized(Exception):
            status_code = 401

        endpoint = Endpoint("mock", "model", "https://example.invalid/v1", "local", "TEST_KEY")
        request = EvalRequest("web-1", "mind2web_act", [{"role": "user", "content": "Open settings"}])
        with tempfile.TemporaryDirectory() as directory, patch("time.sleep") as sleep:
            log = Path(directory) / "eval.jsonl"
            fail = Mock(side_effect=Unauthorized)
            self.assertEqual(run_request(request, endpoint, log, transport=fail)["status"], "error")
            self.assertEqual(fail.call_count, 1)
            transport = Mock(side_effect=[RateLimited(), {"content": None}])
            result = run_request(request, endpoint, log, transport=transport)
            self.assertEqual(result["status"], "ok")
            self.assertIsNone(result["content"])
            self.assertEqual(transport.call_count, 2)
            sleep.assert_called_once()

    def test_default_sdk_adapter_with_mocked_http(self):
        import httpx
        from openai import OpenAI
        from src.common.api_client import Endpoint, EvalRequest, run_request

        def respond(request):
            self.assertEqual(request.url.path, "/v1/chat/completions")
            self.assertEqual(request.headers["authorization"], "Bearer local-test-secret")
            self.assertEqual(json.loads(request.content)["max_tokens"], 128)
            return httpx.Response(200, json={
                "id": "mock-id",
                "model": "mock-version",
                "object": "chat.completion",
                "created": 0,
                "choices": [{
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": "Open settings", "reasoning_content": "Separate"},
                }],
                "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
            })

        def make_client(**options):
            self.assertEqual(options["max_retries"], 0)
            return OpenAI(**options, http_client=httpx.Client(transport=httpx.MockTransport(respond)))

        endpoint = Endpoint("mock", "model", "https://example.invalid/v1", "local", "TEST_KEY")
        request = EvalRequest("web-1", "mind2web_plan", [{"role": "user", "content": "Open settings"}])
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "eval.jsonl"
            with patch.dict(os.environ, TEST_KEY="local-test-secret"):
                with patch("src.common.api_client.OpenAI", side_effect=make_client):
                    result = run_request(request, endpoint, log)
            self.assertEqual(result["content"], "Open settings")
            self.assertEqual(result["reasoning_content"], "Separate")
            self.assertEqual(result["response_model"], "mock-version")
            self.assertEqual(result["usage"]["total_tokens"], 7)
            self.assertNotIn("local-test-secret", log.read_text())


if __name__ == "__main__":
    unittest.main()
