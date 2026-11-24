"""Spec 20: an unusable translation reply is asked for once more; a failed request is not."""
import copy
import json
import unittest

from zjm_rag import translate as translate_module

QUERY = "When is the coffee machine descaled?"
LANGUAGES = ["German"]
MODEL = "test-model"
NOT_JSON = "not json"
USABLE = json.dumps({"German": {"translation": "Wann wird die Kaffeemaschine entkalkt?",
                                "reworded": "Wann erfolgt die Entkalkung der Kaffeemaschine?"}})
UNUSABLE_OBJECT = json.dumps({"German": {"translation": "", "reworded": 7}})
NOT_USABLE = "translation reply not usable"
FAILED = "translation request failed"
BRACES_NOT_JSON = "{not json}"


def scripted_llm(steps):
    """An llm that plays `steps` in order (a reply, or an exception to raise) and records each call."""
    calls = []

    def llm(model, messages, reasoning=True):
        calls.append((model, copy.deepcopy(messages), reasoning))
        step = steps[len(calls) - 1]
        if isinstance(step, Exception):
            raise step
        return step
    return llm, calls


class TranslateRetryTest(unittest.TestCase):
    def assert_calls(self, calls, count):
        """Exactly `count` calls, each with the model, the expected messages and reasoning=False."""
        expected = (MODEL, [{"role": "system", "content": translate_module._system_message(LANGUAGES)},
                            {"role": "user", "content": QUERY}], False)
        self.assertEqual(len(calls), count)
        for call in calls:
            self.assertEqual(call, expected)
            self.assertIs(call[2], False)

    def test_unusable_reply_is_asked_again(self):
        llm, calls = scripted_llm([NOT_JSON, USABLE])
        result = translate_module.translate(QUERY, LANGUAGES, MODEL, llm=llm)
        self.assertEqual(result, (["Wann wird die Kaffeemaschine entkalkt?",
                                   "Wann erfolgt die Entkalkung der Kaffeemaschine?"], None))
        self.assert_calls(calls, 2)

    def test_every_attempt_unusable(self):
        self.assertEqual(translate_module.MAX_ATTEMPTS, 2)
        for replies in ([NOT_JSON, UNUSABLE_OBJECT], [None, None], [BRACES_NOT_JSON, BRACES_NOT_JSON]):
            with self.subTest(replies=replies):
                llm, calls = scripted_llm(replies)
                self.assertEqual(translate_module.translate(QUERY, LANGUAGES, MODEL, llm=llm), ([], NOT_USABLE))
                self.assert_calls(calls, translate_module.MAX_ATTEMPTS)

    def test_failed_request_is_not_asked_again(self):
        llm, calls = scripted_llm([RuntimeError("down"), USABLE])
        self.assertEqual(translate_module.translate(QUERY, LANGUAGES, MODEL, llm=llm), ([], FAILED))
        self.assert_calls(calls, 1)
        llm, calls = scripted_llm([NOT_JSON, RuntimeError("down")])
        self.assertEqual(translate_module.translate(QUERY, LANGUAGES, MODEL, llm=llm), ([], FAILED))
        self.assert_calls(calls, 2)


if __name__ == "__main__":
    unittest.main()
