"""Actual shipped settings assets in Chromium, on the disposable site only."""
import json
from contextlib import contextmanager
import os
from pathlib import Path
import queue
import signal
import subprocess
import sys
import tempfile
import threading
import time
from urllib.request import urlopen
from urllib.parse import urlsplit

import frappe


def diagnostic_path(url):
    """Only static source/API identifiers, never hosts, arguments or records."""
    path = urlsplit(url or '').path
    if path.startswith(('/assets/frappe/', '/assets/erpnext/', '/assets/erpnext_whatsapp_connection/')):
        return path
    if path.startswith('/api/method/'):
        method = path.removeprefix('/api/method/')
        if method and all(c.isascii() and (c.isalnum() or c in '._') for c in method):
            return path
    return '[redacted]'


def exception_location(details):
    exception = details.get('exception') or {}
    kind = exception.get('className')
    kinds = {'Error','TypeError','ReferenceError','SyntaxError','RangeError','Object','DOMException'}
    frames = (details.get('stackTrace') or {}).get('callFrames') or []
    return {'kind':kind if kind in kinds else 'Other',
        'source':diagnostic_path(details.get('url')), 'line':details.get('lineNumber'),
        'column':details.get('columnNumber'), 'frames':[
            {'source':diagnostic_path(frame.get('url')), 'line':frame.get('lineNumber'),
             'column':frame.get('columnNumber')} for frame in frames[:8]]}


class Browser:
    def __init__(self):
        self.errors = []
        self.http_errors = []
        self.exception_objects = []
        self.responses = queue.Queue(maxsize=16)
        self.stop = threading.Event()
        self.reader_error = None
        self.sequence = 0

    def __enter__(self):
        from websockets.sync.client import connect
        self.profile = tempfile.TemporaryDirectory(prefix='whatsapp-ci-browser-')
        self.process = subprocess.Popen(['/usr/bin/chromium', '--headless', '--no-sandbox',
            '--window-size=1440,1000',
            '--disable-gpu', '--disable-dev-shm-usage', '--disable-background-networking',
            '--no-first-run', '--remote-debugging-port=0', '--proxy-server=direct://',
            '--host-resolver-rules=MAP integration.local 127.0.0.1',
            '--user-data-dir=' + self.profile.name, 'about:blank'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        port_file = Path(self.profile.name) / 'DevToolsActivePort'
        deadline = time.monotonic() + 20
        while not port_file.exists():
            if self.process.poll() is not None or time.monotonic() > deadline:
                self.process.terminate()
                self.process.wait(timeout=10)
                self.profile.cleanup()
                raise AssertionError('Isolated Chromium did not start')
            time.sleep(.1)
        port = int(port_file.read_text().splitlines()[0])
        with urlopen(f'http://127.0.0.1:{port}/json/list', timeout=10) as response:
            page = next(row for row in json.load(response) if row['type'] == 'page')
        self.connection = connect(page['webSocketDebuggerUrl'], open_timeout=10, max_size=8*1024*1024)
        self.reader = threading.Thread(target=self.read, daemon=True)
        self.reader.start()
        self.command('Page.enable')
        self.command('Runtime.enable')
        self.command('Network.enable')
        return self

    def read(self):
        try:
            while not self.stop.is_set():
                try:
                    event = json.loads(self.connection.recv(timeout=.5))
                except TimeoutError:
                    continue
                if event.get('method') == 'Runtime.exceptionThrown':
                    if len(self.errors) >= 50:
                        raise RuntimeError('Browser exception buffer exhausted')
                    details = event['params']['exceptionDetails']
                    self.errors.append(exception_location(details))
                    self.exception_objects.append((details.get('exception') or {}).get('objectId'))
                elif event.get('method') == 'Network.responseReceived':
                    response = event['params']['response']
                    if response.get('status', 0) >= 400 and len(self.http_errors) < 50:
                        self.http_errors.append({'source':diagnostic_path(response.get('url')),
                            'status':response['status']})
                elif 'id' in event:
                    self.responses.put_nowait(event)
        except Exception as error:
            if not self.stop.is_set():
                self.reader_error = error

    def command(self, method, params=None):
        self.sequence += 1
        self.connection.send(json.dumps({'id':self.sequence,'method':method,'params':params or {}}))
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if self.reader_error:
                raise RuntimeError('Browser protocol reader failed') from self.reader_error
            try:
                response = self.responses.get(timeout=.5)
            except queue.Empty:
                continue
            if response.get('id') == self.sequence:
                if 'error' in response:
                    raise AssertionError('Browser protocol command failed: ' + method)
                return response.get('result', {})
        raise TimeoutError('Browser command timed out: ' + method)

    def evaluate(self, expression):
        result = self.command('Runtime.evaluate', {'expression':expression,
            'returnByValue':True, 'awaitPromise':True})
        if result.get('exceptionDetails'):
            raise AssertionError('Native browser expression failed: ' +
                result['exceptionDetails'].get('text', 'Uncaught exception'))
        return result.get('result', {}).get('value')

    def wait(self, expression):
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if self.evaluate(expression):
                return
            time.sleep(.2)
        raise AssertionError('Native settings browser did not reach its required state')

    def click(self, expression):
        """Dispatch real browser input, including native trusted user activation."""
        point = self.evaluate('''(() => {
            const element = (''' + expression + ''');
            if (!element) return {unavailable:'missing'};
            if (element.disabled) return {unavailable:'disabled'};
            element.scrollIntoView({block:'center', inline:'center'});
            const rect = element.getBoundingClientRect();
            if (!rect.width || !rect.height) return {unavailable:'hidden'};
            return {x:rect.x + rect.width/2, y:rect.y + rect.height/2};
        })()''')
        if point.get('unavailable'):
            raise AssertionError('Required native browser control is ' + point['unavailable'])
        for kind, buttons in (('mousePressed', 1), ('mouseReleased', 0)):
            self.command('Input.dispatchMouseEvent', {'type':kind, 'button':'left',
                'buttons':buttons, 'clickCount':1, **point})

    def diagnostics(self):
        # Rejected XHR promises are plain Objects. Read only typed status/error
        # names; never serialize their request, response body or message text.
        statuses = []
        for object_id in list(self.exception_objects):
            if not object_id:
                continue
            result = self.command('Runtime.callFunctionOn', {'objectId':object_id,
                'returnByValue':True, 'functionDeclaration':'''function() {
                    const known = new Set(['PermissionError','ValidationError','AuthenticationError',
                        'MandatoryError','DoesNotExistError','CSRFTokenError','SessionExpired']);
                    const kind = this.responseJSON?.exc_type || this.exc_type;
                    return {status: Number.isInteger(this.status) ? this.status : null,
                        dom_exception: ['NotAllowedError','AbortError','SecurityError'].includes(this.name)
                            ? this.name : null,
                        exception_type: known.has(kind) ? kind : 'Other'};
                }'''})
            if not result.get('exceptionDetails'):
                statuses.append(result.get('result', {}).get('value'))
        return {'exceptions':list(self.errors), 'http_errors':list(self.http_errors),
            'rejected_requests':statuses}

    def __exit__(self, *_):
        self.stop.set()
        self.connection.close()
        self.reader.join(timeout=3)
        try:
            os.killpg(self.process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(self.process.pid, signal.SIGKILL)
            self.process.wait(timeout=5)
        # Chromium children can outlive their parent briefly and recreate
        # profile files during cleanup. This is our dedicated process group.
        try:
            os.killpg(self.process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        self.profile.cleanup()


@contextmanager
def native_http():
    from erpnext_whatsapp_connection.group_acceptance import require_fixture_site
    require_fixture_site()
    import requests
    server = subprocess.Popen([sys.executable, '-c',
        'from frappe.app import serve; serve(port=8000, site="integration.local", no_reload=True)'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    health = requests.Session()
    health.trust_env = False
    try:
        deadline = time.monotonic() + 30
        while True:
            try:
                response = health.get('http://127.0.0.1:8000/api/method/ping',
                    headers={'Host':'integration.local'}, timeout=2)
                if response.status_code == 200:
                    break
            except requests.RequestException:
                pass
            if server.poll() is not None or time.monotonic() > deadline:
                raise AssertionError('Disposable native HTTP server did not start')
            time.sleep(.2)
        yield
    finally:
        health.close()
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)


def validate_browser(company, other_company, sender, password, editor, editor_password):
    from erpnext_whatsapp_connection.group_acceptance import require_fixture_site, GROUP
    require_fixture_site()
    import requests
    from frappe.desk.page.setup_wizard.setup_wizard import enable_setup_wizard_complete

    frappe.set_user('Administrator')
    for app in ('frappe', 'erpnext'):
        enable_setup_wizard_complete(app)
    frappe.db.commit()
    sessions = []
    try:
        def login(user, secret):
            session = requests.Session()
            session.trust_env = False
            session.headers['Host'] = 'integration.local'
            response = session.post('http://127.0.0.1:8000/api/method/login',
                data={'usr':user,'pwd':secret}, timeout=30)
            response.raise_for_status()
            assert session.cookies.get('sid'), 'Synthetic login did not create a session'
            sessions.append(session)
            return session

        editing = login(editor, editor_password)
        with Browser() as browser:
            browser.command('Network.setCookie', {'name':'sid','value':editing.cookies['sid'],
                'domain':'integration.local','path':'/','httpOnly':True})
            browser.command('Page.navigate', {'url':'http://integration.local:8000/desk/erpnext-whatsapp-settings'})
            browser.wait("Boolean(window.cur_frm?.doctype === 'ERPNext WhatsApp Settings' && cur_frm.doc && !cur_frm.doc.__islocal)")
            assert browser.evaluate("Array.from(document.scripts).some(s=>s.src.includes('send_by_whatsapp.js'))"), 'Actual add-on asset was not loaded'
            browser.wait("Boolean(typeof window.erpnext_whatsapp_connection?.attach_document_button === 'function' && typeof window.erpnext_whatsapp_connection?.attach_report_button === 'function')")
            assert browser.evaluate("Boolean(Array.from(document.querySelectorAll('button')).find(b=>b.textContent.trim()==='Configure Company Group'))")
            browser.evaluate("Array.from(document.querySelectorAll('button')).find(b=>b.textContent.trim()==='Configure Company Group').click(); true")
            browser.wait("Boolean(window.cur_dialog?.title === 'Company Group Copy')")
            browser.evaluate('cur_dialog.set_value("company",' + json.dumps(company) + ')')
            assert browser.evaluate('Boolean(cur_dialog.get_value("enabled"))') is False
            browser.evaluate("cur_dialog.fields_dict.load_groups.df.click(); true")
            browser.wait('Boolean(cur_dialog.fields_dict.group.df.options.some(row=>row.value===' + json.dumps(GROUP) + '))')
            browser.evaluate('cur_dialog.set_value("group",' + json.dumps(GROUP) + ')')
            browser.evaluate('cur_dialog.set_value("enabled",1)')
            browser.evaluate("cur_dialog.get_primary_btn().trigger('click'); true")
            browser.wait("Boolean(!cur_dialog?.$wrapper.is(':visible') && cur_frm.is_dirty())")
            browser.wait("Boolean(!document.querySelector('.modal-backdrop'))")
            browser.click('cur_frm.page.btn_primary[0]')
            browser.wait('Boolean(!cur_frm.is_dirty() && frappe.request.ajax_count === 0)')
            browser.evaluate('cur_frm.reload_doc().then(()=>true)')
            assert browser.evaluate('cur_frm.doc.company_groups.some(row=>row.company===' + json.dumps(company)
                + ' && row.group_id===' + json.dumps(GROUP) + ' && row.enabled===1)'), 'Actual settings save/reopen lost company configuration'
            browser.wait('Boolean(window.frappe?.request && frappe.request.ajax_count === 0)')
            if browser.errors:
                raise AssertionError('Actual target assets raised uncaught browser exceptions: ' +
                    json.dumps(browser.diagnostics(), separators=(',', ':')))

        response = editing.get('http://127.0.0.1:8000/api/method/erpnext_whatsapp_connection.company_groups.list_groups',
            params={'company':other_company}, timeout=30)
        assert response.status_code == 403 and response.json().get('exc_type') == 'PermissionError', 'Editor discovered groups through a forbidden Company'

        # Revoke the configured Settings authority while preserving the native
        # add-on Manager carrier. A role label cannot retain group discovery.
        frappe.set_user('Administrator')
        actor = frappe.get_doc('User', editor)
        actor.set('roles', [{'role':'ERPNext WhatsApp Manager'}])
        actor.save(ignore_permissions=True)
        frappe.db.commit()
        response = editing.get('http://127.0.0.1:8000/api/method/erpnext_whatsapp_connection.company_groups.list_groups',
            params={'company':company}, timeout=30)
        assert response.status_code == 403 and response.json().get('exc_type') == 'PermissionError', 'Revoked Settings Write retained group discovery'

        denied = login(sender, password)
        response = denied.get('http://127.0.0.1:8000/api/method/erpnext_whatsapp_connection.company_groups.list_groups',
            params={'company':company}, timeout=30)
        assert response.status_code == 403 and response.json().get('exc_type') == 'PermissionError', 'Sender without Settings Write discovered groups'
    finally:
        for session in sessions:
            session.close()
