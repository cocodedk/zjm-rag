"""Decision fallback, overrides and provenance without live provider requests."""
import io
import json
import os
import unittest
import urllib.error
from unittest import mock

from fakes import FakeRunner, fake_jev, fake_llm, make_config, make_locker

from zjm_rag import ZjmError, ask, find, jev
from zjm_rag.cli import _args_to_body, _parser
from zjm_rag.cli_human import human
from zjm_rag.ops import OPS, check


class JevTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-secret", "TYPESAFE_API_KEY": "ts-secret"}, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.sent = []
        self.urls = []

    def transport(self, responses):
        responses = iter(responses)

        def send(req, timeout):
            self.sent.append(json.loads(req.data))
            self.urls.append((req.full_url, req.get_header('Authorization')))
            response = next(responses)
            if isinstance(response, Exception):
                raise response
            return io.BytesIO(json.dumps(response).encode())

        opener = mock.Mock()
        opener.open.side_effect = send
        return mock.patch.object(jev.urllib.request, 'build_opener', return_value=opener)

    def test_order_and_actual_returned_model(self):
        response = {'answers': {}, 'model': 'resolved-provider-model'}
        failures = [urllib.error.URLError('secret transport detail'), {'error': 'secret body'}, []]
        with self.transport([*failures, response]):
            self.assertEqual(jev.post({'questions': {}}), response)
        self.assertEqual([p['model'] for p in self.sent], [
            'perplexity/pplx-decider-v1.1-27b', 'jev-1.14.0', 'openai/gpt-6-luna-decisions',
            'microsoft/microsoft-decision-1'])
        self.assertEqual(self.urls[1], (jev.TYPESAFE_URL, 'Bearer ts-secret'))
        self.assertEqual({u for i, u in enumerate(self.urls) if i != 1}, {(jev.URL, 'Bearer test-secret')})

    def test_jev_goes_to_typesafe_others_to_openrouter(self):
        for given, expected in (('~typesafe/jev-latest', (jev.TYPESAFE_URL, 'TYPESAFE_API_KEY', 'jev-1.14.0')),
                                ('typesafe/jev-1.13', (jev.TYPESAFE_URL, 'TYPESAFE_API_KEY', 'jev-1.13.0')),
                                ('jev-1.14.0', (jev.TYPESAFE_URL, 'TYPESAFE_API_KEY', 'jev-1.14.0')),
                                ('openai/gpt-6-luna-decisions',
                                 (jev.URL, 'OPENROUTER_API_KEY', 'openai/gpt-6-luna-decisions'))):
            with self.subTest(given=given):
                self.assertEqual(jev.route(given), expected)
        with mock.patch.dict(os.environ, {'TYPESAFE_API_KEY': ''}), \
                self.transport([{'answers': {}, 'model': 'luna'}]):
            jev.post({}, model='jev-1.14.0')   # listed: a missing key hands over to the next model
        self.assertEqual([p['model'] for p in self.sent], ['openai/gpt-6-luna-decisions'])
        with mock.patch.dict(os.environ, {'TYPESAFE_API_KEY': ''}), self.transport([]), \
                self.assertRaisesRegex(ZjmError, 'TYPESAFE_API_KEY is not set'):
            jev.post({}, model='jev-preview')   # unlisted: one attempt

    def test_precedence_and_custom_model_single_attempt(self):
        for argument, requested, environment, expected in (
            ('cli', 'request', 'env', 'cli'),
            (None, 'request', 'env', 'request'),
            (None, None, 'env', 'env'),
            (None, None, '', jev.DEFAULT_MODELS[0]),
        ):
            with self.subTest(expected=expected), mock.patch.dict(os.environ, {'JEV_MODEL': environment}), \
                    self.transport([{'answers': {}, 'model': expected}]):
                payload = {'model': requested} if requested else {}
                jev.post(payload, model=argument)
                self.assertEqual(self.sent[-1]['model'], expected)
        self.sent.clear()
        with self.transport([urllib.error.URLError('private')]), self.assertRaises(ZjmError):
            jev.post({}, model='custom')
        self.assertEqual(len(self.sent), 1)
        self.sent.clear()
        with self.transport([{'error': 'unavailable'}, {'answers': {}}]):
            jev.post({}, model=jev.DEFAULT_MODELS[2])
        self.assertEqual([p['model'] for p in self.sent], list(jev.DEFAULT_MODELS[2:]))

    def test_successful_low_score_does_not_fallback(self):
        response = {'answers': {'f1': {'noul': 0.01}}, 'model': 'pplx-returned'}
        with self.transport([response]):
            self.assertEqual(jev.post({'questions': {'f1': {'type': 'noul'}}}), response)
        self.assertEqual(len(self.sent), 1)

    def test_exhaustion_caps_and_redaction(self):
        with self.transport([{'error': 'test-secret'}] * 4), self.assertRaises(ZjmError) as caught:
            jev.post({})
        self.assertEqual(len(self.sent), 4)
        self.assertNotIn('test-secret', str(caught.exception))
        self.assertNotIn('ts-secret', str(caught.exception))
        with self.transport([]), self.assertRaisesRegex(ZjmError, '512 KiB'):
            jev.post({'state': 'x' * jev.MAX_REQUEST_BYTES})
        self.sent.clear()
        with mock.patch.object(jev, 'MAX_RESPONSE_BYTES', 10), \
                self.transport([{'long': 'x' * 20}] * 4), self.assertRaisesRegex(ZjmError, '1 MiB'):
            jev.post({})
        self.assertEqual(len(self.sent), 4)

    def test_model_flows_through_surfaces_and_results(self):
        cfg = make_config(self)
        make_locker(self, cfg)
        payloads = []

        def rank(payload):
            payloads.append(payload)
            return {**fake_jev([0.9, 0.8, 0.7])(payload), 'model': 'actually-returned'}

        args = _parser().parse_args(['find', 'q', '-l', 'lib', '--model', 'selected'])
        body = _args_to_body('find', args)
        self.assertIsNone(check('find', body))
        result = OPS['find'][0](body, config=cfg, runner=FakeRunner(), jev=rank)
        self.assertEqual(payloads[-1]['model'], 'selected')
        self.assertEqual(result['returned_model'], 'actually-returned')
        self.assertIn('decision model: actually-returned', human('find', result))
        result = ask('q', ['lib'], model='selected', config=cfg, runner=FakeRunner(), jev=rank, llm=fake_llm())
        self.assertEqual(result['returned_model'], 'actually-returned')
        self.assertEqual(result['find']['returned_model'], 'actually-returned')
        self.assertEqual(OPS['ask'][1]['properties']['model'], {'type': 'string'})
        result = find('q', ['lib'], rank=False, config=cfg, runner=FakeRunner(), jev=rank)
        self.assertIsNone(result['returned_model'])
        self.assertEqual(len(payloads), 2)
