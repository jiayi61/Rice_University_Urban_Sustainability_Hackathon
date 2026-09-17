from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
from eventflow.universal import UniversalPlanner
from eventflow.pdf_report import remember_plan, saved_report


class ReportTests(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.plan = UniversalPlanner(Path(self.temp.name), None).plan_from_brief(
            'Concert in New York', False, {'attendance': 50000, 'budget_usd': 100000})

    def test_pdf_uses_saved_snapshot(self):
        p = remember_plan(self.plan)
        p['venue']['name'] = 'Browser mutation does not affect server snapshot'
        pdf = saved_report(p['report_id'])
        self.assertTrue(pdf.startswith(b'%PDF-'))
        self.assertGreater(len(pdf), 10000)

    def test_unknown_and_expired_report(self):
        with self.assertRaises(ValueError):
            saved_report('not-a-report')
        with patch('eventflow.pdf_report.time.monotonic', return_value=100):
            p = remember_plan(self.plan)
        with patch('eventflow.pdf_report.time.monotonic', return_value=4000), self.assertRaises(ValueError):
            saved_report(p['report_id'])

    def test_home_has_no_prepared_case(self):
        root = Path(__file__).resolve().parents[1]
        html = (root/'app/static/index.html').read_text()
        js = (root/'app/static/app.js').read_text()
        self.assertIn('id="resultsNav" hidden', html)
        self.assertNotIn('newYorkResult', html)
        self.assertNotIn('openPreparedExample', js)
        self.assertNotIn('text/markdown', js)
        self.assertNotIn('competition-scenarios.json', js)
