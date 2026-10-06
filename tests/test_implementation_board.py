"""实施看板 scripts/implementation_board.py 的回归测试。

- 票：只凭 issues/*.md 推出分组与可开工前沿，不需要地图或清单；五种角色与执行进度互不混淆，没有完成记录的 done 不放行
  后继；依赖写错（成环、指向不存在的票、编号重复）照样显示、不放行后继，依赖尾巴含糊或完成记录自相矛盾的票不能就绪；
  项目自定义的标签别名与正式的依赖写法；代码块与引用里的示例不算元数据，重复字段报错、不认识的状态归为无效；链接写坏
  只影响那张票；
- 问题（questions/*.md）：解析与各类报错、推荐项必须对应一条路线、解释 needs-info 的阻塞与解除、被未结问题列出的就绪票
  移出前沿、状态读不懂的问题按未结处理；问题文件计入版本、与票双向链接，看板不能写进 questions/；
- 页面与服务：静态看板带完整且安全的 Markdown（脚本与 javascript: 链接被转义），不读地图、清单、草稿等别的状态文件；
  HTTP 只读、不许越出目录，刷新失败返回错误而不是空快照；空的存储不算草稿发布，导出不能覆盖票文件。

只用 Python 标准库，在临时目录里现造票与问题文件，不读仓库里的真实票。PATH 上有 chromium 时另在无头浏览器里验真实页面
（导航、刷新、改名、读取失败与删除，问题优先显示与双向跳转），没有就跳过这两项。在仓库根运行：
    python3 -m unittest discover -s tests -p 'test_implementation_board.py'
"""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BOARD = ROOT / 'scripts/implementation_board.py'


def module():
    spec = importlib.util.spec_from_file_location('implementation_board', BOARD)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


class ImplementationBoardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'issues').mkdir()

    def ticket(self, number, status='ready-for-agent', progress=None, blocked='none', extra='', title=None):
        path = self.root / 'issues' / f'{number}-ticket.md'
        path.write_text(f'# {number}: {title or "任务" + number}\n\n**Status:** {status}\n'
                        + (f'Progress: {progress}\n' if progress else '')
                        + f'**Blocked by:** {blocked}\n\n**What to build:** 可观察交付\n\n'
                        + '- [ ] 验收行为\n' + extra, encoding='utf-8')
        return path

    def test_official_tickets_derive_frontier_without_a_map_or_manifest(self):
        self.ticket('01')
        self.ticket('02', blocked='01')
        board = module().load(self.root)
        tickets = {t['num']: t for t in board['tickets']}
        self.assertEqual(tickets['01']['frontier'], 'agent')
        self.assertEqual(tickets['02']['frontier'], '')
        self.assertEqual(tickets['02']['waiting'], [tickets['01']['key']])
        self.assertEqual(tickets['01']['dependents'], [tickets['02']['key']])
        self.assertEqual(tickets['01']['progress'], 'not-started')
        self.assertEqual(board['counts']['pending'], 2)

    def test_all_official_roles_and_execution_progress_remain_distinct(self):
        self.ticket('01', progress='done', extra='\n## Completion\n验收已通过，提交 abc123。\n')
        self.ticket('02', blocked='01')
        self.ticket('03', status='ready-for-human', blocked='01')
        self.ticket('04', status='needs-info', progress='in-progress')
        self.ticket('05', status='needs-triage')
        self.ticket('06', status='wontfix')
        self.ticket('07', progress='in-progress')
        self.ticket('08', blocked='06')
        self.ticket('09', progress='done')  # No completion evidence: do not unlock a successor.
        self.ticket('10', blocked='09')
        board = module().load(self.root)
        ts = {t['num']: t for t in board['tickets']}
        self.assertEqual([ts[n]['group'] for n in ['01', '02', '03', '04', '05', '06', '07']],
                         ['done', 'pending', 'pending', 'needs-info', 'needs-triage', 'wontfix', 'active'])
        self.assertTrue(ts['01']['complete'])
        self.assertEqual(ts['02']['frontier'], 'agent')
        self.assertEqual(ts['03']['frontier'], 'human')
        self.assertEqual(ts['04']['progress'], 'in-progress')
        self.assertFalse(ts['08']['frontier'])
        self.assertFalse(ts['09']['complete'])
        self.assertFalse(ts['10']['frontier'])
        self.assertTrue(ts['07']['warnings'])

    def test_bad_dependencies_stay_visible_and_never_unlock_successors(self):
        self.ticket('01', progress='done', blocked='02', extra='\n## Completion\n完成。')
        self.ticket('02', progress='done', blocked='01', extra='\n## Completion\n完成。')
        self.ticket('03', blocked='99')
        duplicate = self.ticket('04')
        duplicate.with_name('04-duplicate.md').write_text(duplicate.read_text())
        self.ticket('05', blocked='04')
        self.ticket('06')
        self.ticket('07', blocked='01')
        board = module().load(self.root)
        self.assertEqual(len(board['tickets']), 8)
        ts = {t['num']: t for t in board['tickets']}
        self.assertTrue(ts['01']['errors'])
        self.assertTrue(ts['03']['errors'])
        self.assertTrue(ts['05']['errors'])
        self.assertFalse(ts['01']['complete'])
        self.assertFalse(ts['07']['frontier'])
        self.assertEqual(ts['06']['frontier'], 'agent')

    def test_project_aliases_and_official_dependency_references(self):
        labels = self.root / 'labels.md'
        labels.write_text('| Role | Label | Meaning |\n| --- | --- | --- |\n' + ''.join(
            f'| `{role}` | `{alias}` | 描述 |\n' for role, alias in [
                ('needs-triage', 'assess'), ('needs-info', 'details'),
                ('ready-for-agent', 'agent-ready'), ('ready-for-human', 'human-ready'), ('wontfix', 'declined')]))
        self.ticket('01', status='agent-ready', title='前置 任务', progress='done', extra='\n## 完成记录\n验收通过。')
        self.ticket('02', status='agent-ready', blocked='前置 任务')
        self.ticket('03', status='human-ready', blocked='[前置](01-ticket.md)')
        self.ticket('04', status='details', blocked='None (can start immediately)')
        board = module().load(self.root, labels)
        ts = {t['num']: t for t in board['tickets']}
        self.assertEqual(ts['02']['frontier'], 'agent')
        self.assertEqual(ts['03']['frontier'], 'human')
        self.assertEqual(ts['04']['group'], 'needs-info')
        self.assertEqual(ts['02']['status'], 'agent-ready')
        labels.write_text(labels.read_text().replace('human-ready', 'agent-ready'))
        bad = module().load(self.root, labels)
        self.assertTrue(bad['errors'])
        self.assertFalse(any(t['frontier'] for t in bad['tickets']))

    def test_examples_are_not_metadata_and_duplicate_fields_are_reported(self):
        self.ticket('01', blocked='None (can start immediately)', extra='\n## 示例\n```\nStatus: done\n```\n')
        path = self.ticket('02')
        path.write_text(path.read_text().replace('**Status:**', '> Status: wontfix\n```text\nStatus: wontfix\n```\n**Status:**'))
        path = self.ticket('03')
        path.write_text(path.read_text().replace('**Status:** ready-for-agent', '**Status:** ready-for-agent\nStatus: wontfix'))
        path = self.ticket('04')
        path.write_text(path.read_text().replace('**Status:** ready-for-agent', '**Status:** unknown'))
        ts = {t['num']: t for t in module().load(self.root)['tickets']}
        self.assertEqual(ts['01']['frontier'], 'agent')
        self.assertEqual(ts['02']['frontier'], 'agent')
        self.assertTrue(ts['03']['errors'])
        self.assertFalse(ts['03']['frontier'])
        self.assertEqual(ts['04']['group'], 'invalid')

    def test_static_board_contains_full_safe_markdown_and_ignores_other_state_files(self):
        self.ticket('01', extra='\n## Purpose\n保留产品贡献。\n\n## 示例\n```html\n<script>alert(1)</script>\n```\n'
                    '\n| 列 | 内容 |\n| --- | --- |\n| A | B |\n\n[坏链接](javascript:alert)\n')
        board = module()
        first = board.load(self.root)
        (self.root / 'map.md').write_text('Status: resolved')
        (self.root / 'manifest.json').write_text('{"tickets": []}')
        (self.root / 'ticket-breakdown.md').write_text('all done')
        (self.root / 'drafts').mkdir()
        (self.root / 'drafts/02-no.md').write_text('not published')
        self.assertEqual(board.load(self.root)['revision'], first['revision'])
        page = board.build(self.root)
        self.assertIn('实施票看板', page)
        self.assertNotIn('<script>alert(1)</script>', page)
        self.assertNotIn('href="javascript:', page)
        data = board.presentation(first)
        body = data['tickets'][0]['body_html']
        self.assertIn('<table>', body)
        self.assertIn('disabled', body)
        self.assertIn('&lt;script&gt;', body)
        self.assertIn('保留产品贡献', body)

    def test_http_is_read_only_and_failed_refresh_is_not_an_empty_snapshot(self):
        import threading
        import urllib.error
        import urllib.request
        path = self.ticket('01')
        board = module()
        server = board.make_server(self.root, port=0)
        self.addCleanup(server.server_close)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.shutdown)
        url = f'http://127.0.0.1:{server.server_port}'
        with urllib.request.urlopen(url + '/api/board') as response:
            self.assertIn('no-store', response.headers['Cache-Control'])
            initial = json.load(response)
        original = path.read_bytes()
        with self.assertRaises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(urllib.request.Request(url + '/api/board', data=b'{}', method='POST'))
        self.assertEqual(exc.exception.code, 405)
        self.assertEqual(path.read_bytes(), original)
        with self.assertRaises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(url + '/../../AGENTS.md')
        self.assertEqual(exc.exception.code, 404)
        path.write_text(path.read_text().replace('ready-for-agent', 'needs-info'))
        with urllib.request.urlopen(url + '/api/board') as response:
            self.assertNotEqual(json.load(response)['revision'], initial['revision'])
        path.unlink()
        (self.root / 'issues').rmdir()
        (self.root / 'issues').write_text('not a directory')
        with self.assertRaises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(url + '/api/board')
        self.assertEqual(exc.exception.code, 503)

    def test_browser_navigation_refresh_rename_failure_and_delete(self):
        import html
        import re
        import shutil
        import subprocess
        chromium = shutil.which('chromium')
        if not chromium:
            self.skipTest('Chromium required for real DOM/refresh verification')
        self.ticket('01', progress='done', extra='\n## Completion\n验收通过。')
        path = self.ticket('02', blocked='01', extra='\n## Purpose\n用户目标\n\n## 正文\n' + '\n\n'.join('阅读段落 '+str(n) for n in range(90)))
        self.ticket('03', blocked='02', extra='\n## 说明\n独特搜索词\n')
        self.ticket('04', status='needs-info')
        board = module()
        initial = board.presentation(board.load(self.root))
        page = board.build(self.root, live=True)
        renamed = path.with_name('02-renamed.md')
        path.rename(renamed)
        renamed.write_text(renamed.read_text().replace('**Blocked by:**', 'Progress: in-progress\nClaimed: 2026-09-22 tester\n**Blocked by:**').replace('## 正文', '## 新增说明\n刷新增加的内容\n\n## 正文'))
        updated = board.presentation(board.load(self.root))
        renamed.unlink()
        removed = board.presentation(board.load(self.root))
        payload = json.dumps([initial, updated, removed], ensure_ascii=False).replace('<', '\\u003c')
        probe = r'''<script>
const snapshots=PAYLOAD;const result={};let n=0,reference=null,anchor=null,offset=0;
const record=()=>{let p=document.getElementById('probe');if(!p){p=document.createElement('pre');p.id='probe';document.body.append(p);}p.textContent=JSON.stringify(result);};
window.fetch=async()=>{n++;const round=n;setTimeout(()=>{try{
 if(round===1)result.unchanged=reference===document.querySelector('[data-anchor="'+anchor+'"]');
 if(round===2){result.renamed=decodeURIComponent(location.hash).includes('02-renamed.md');result.active=document.querySelector('details[data-group="active"] [data-ticket="02-renamed.md"]')!==null;const block=document.querySelector('[data-anchor="'+anchor+'"]');result.scroll=!!block&&Math.abs(block.getBoundingClientRect().top-offset)<3;}
 if(round===3){result.stale=!document.getElementById('error').hidden;result.retained=document.getElementById('main').textContent.includes('用户目标');}
 if(round===4){result.deleted=document.getElementById('main').textContent.includes('票已删除');result.noJump=decodeURIComponent(location.hash).includes('02-renamed.md');result.recovered=document.getElementById('error').hidden;record();}
}catch(e){result.error=String(e);record();}},100);
 if(n===3)throw Error('模拟连接失败');return {ok:true,json:async()=>snapshots[n===1?0:n===2?1:2]};};
setTimeout(()=>{try{
 result.clarifyClosed=!document.querySelector('[data-group="clarify"]').open;
 document.querySelector('[data-ticket="02-ticket.md"]').click();
 result.selected=decodeURIComponent(location.hash).includes('02-ticket.md');
 const predecessor=document.querySelector('[data-ticket="01-ticket.md"]');result.related=predecessor.classList.contains('rel-before');
 document.querySelector('[data-ticket="02-ticket.md"] .badge.r').click();result.badge=decodeURIComponent(location.hash).includes('01-ticket.md');
 const search=document.getElementById('search');search.value='独特搜索词';search.dispatchEvent(new Event('input'));result.search=document.getElementById('main').textContent.includes('任务03')&&!document.getElementById('main').textContent.includes('任务02');
 search.value='';search.dispatchEvent(new Event('input'));document.querySelector('[data-ticket="02-ticket.md"]').click();
 const toggle=document.getElementById('before');toggle.checked=false;toggle.dispatchEvent(new Event('change'));result.toggle=!document.querySelector('.rel-before');
 reference=document.querySelectorAll('#main [data-anchor]')[45];anchor=reference.dataset.anchor;reference.scrollIntoView();offset=reference.getBoundingClientRect().top;
}catch(e){result.error=String(e);record();}},100);
</script>'''.replace('PAYLOAD', payload)
        page = page.replace('<script id="bootstrap"', probe + '<script id="bootstrap"')
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            directory = Path(directory)
            output = directory / 'board.html'
            output.write_text(page, encoding='utf-8')
            result = subprocess.run([chromium, '--headless=new', '--no-sandbox', '--disable-gpu',
                '--disable-background-networking', '--disable-component-update', '--disable-sync',
                '--no-first-run', '--disable-extensions', f'--user-data-dir={directory / "profile"}',
                '--virtual-time-budget=10000', '--dump-dom', output.as_uri()], capture_output=True, text=True, timeout=35, check=True)
        found = re.search(r'<pre id="probe">(.*?)</pre>', result.stdout, re.S)
        self.assertIsNotNone(found, result.stderr[-1500:])
        observed = json.loads(html.unescape(found[1]))
        self.assertNotIn('error', observed, observed)
        for name in ['clarifyClosed','selected','related','badge','search','toggle','unchanged','renamed','active','scroll','stale','retained','deleted','noJump','recovered']:
            self.assertTrue(observed.get(name), (name, observed))

    def question(self, number, status='open', blocks='none', recommended='路线甲', routes=('路线甲', '路线乙'),
                 extra='', filename=None, title=None):
        folder = self.root / 'questions'
        folder.mkdir(exist_ok=True)
        path = folder / (filename or f'Q{number}-question.md')
        body = f'# {title or "Q" + number + ": 问题" + number}\n\nStatus: {status}\nBlocks: {blocks}\nRaised: 2026-09-25 tester\n'
        if recommended is not None:
            body += f'Recommended: {recommended}\n'
        body += '\n## 在决定什么\n白话说明。\n\n## 可选路线\n'
        body += ''.join(f'### {chr(65 + i)}. {r}\n- 做法：示例\n' for i, r in enumerate(routes)) + extra
        path.write_text(body, encoding='utf-8')
        return path

    def test_question_parsing_and_errors(self):
        self.ticket('01')
        self.question('01', blocks='01')
        self.question('02', status='pending', blocks='01')
        (self.root / 'questions' / 'bad-name.md').write_text('# Q09: 坏名字\n\nStatus: open\nBlocks: none\n', encoding='utf-8')
        self.question('04', blocks='')
        self.question('05', blocks='07')
        self.question('06', filename='Q06-a.md')
        self.question('06', filename='Q06-b.md')
        self.question('08', title='Q09: 编号不符')
        qs = {q['key']: q for q in module().load(self.root)['questions']}
        good = qs['Q01-question.md']
        self.assertEqual((good['num'], good['blocks'], good['errors'], good['warnings']), ('Q01', ['01-ticket.md'], [], []))
        self.assertTrue(any('无法识别问题状态' in e for e in qs['Q02-question.md']['errors']))
        self.assertTrue(any('文件名' in e for e in qs['bad-name.md']['errors']))
        self.assertTrue(any('缺少Blocks' in e for e in qs['Q04-question.md']['errors']))
        self.assertTrue(any('Blocks里的票不存在' in e for e in qs['Q05-question.md']['errors']))
        self.assertIn('问题编号重复', qs['Q06-a.md']['errors'])
        self.assertIn('问题编号重复', qs['Q06-b.md']['errors'])
        self.assertIn('标题编号与文件编号不一致', qs['Q08-question.md']['errors'])

    def test_recommended_must_name_a_route(self):
        self.ticket('01')
        self.question('01', recommended=None)
        self.question('02', recommended='不存在的路线')
        self.question('03', recommended='路线乙')
        self.question('04', routes=('路线甲（推荐）', '路线乙'), recommended='路线甲')
        qs = {q['num']: q for q in module().load(self.root)['questions']}
        self.assertIn('待答问题缺少Recommended', qs['Q01']['warnings'])
        self.assertTrue(any('不等于任何路线' in w for w in qs['Q02']['warnings']))
        self.assertEqual(qs['Q03']['warnings'], [])
        self.assertEqual(qs['Q04']['warnings'], [])

    def test_question_explains_needs_info_block_and_release(self):
        first = self.ticket('01', status='needs-info')
        self.ticket('02')
        question = self.question('01', blocks='01')
        board = module().load(self.root)
        ts = {t['num']: t for t in board['tickets']}
        self.assertEqual(ts['01']['questions'], ['Q01-question.md'])
        self.assertEqual(ts['01']['warnings'], [])
        self.assertEqual((board['counts']['questions_open'], board['counts']['questions_unresolved']), (1, 1))
        question.write_text(question.read_text().replace('Status: open', 'Status: resolved'), encoding='utf-8')
        board = module().load(self.root)
        ts = {t['num']: t for t in board['tickets']}
        self.assertIn('问题已结，仍needs-info：Q01', ts['01']['warnings'])
        self.assertEqual(board['counts']['questions_unresolved'], 0)
        first.write_text(first.read_text().replace('needs-info', 'ready-for-agent'), encoding='utf-8')
        ts = {t['num']: t for t in module().load(self.root)['tickets']}
        self.assertEqual((ts['01']['frontier'], ts['01']['warnings'], ts['01']['questions']), ('agent', [], []))

    def test_ready_ticket_listed_by_unresolved_question_leaves_frontier(self):
        self.ticket('01')
        self.ticket('02', progress='in-progress', extra='\nClaimed: 2026-09-25 tester\n')
        self.question('01', status='drafting', blocks='01, 02')
        ts = {t['num']: t for t in module().load(self.root)['tickets']}
        self.assertEqual(ts['01']['frontier'], '')
        self.assertIn('列入未结问题却仍可开工：Q01', ts['01']['warnings'])
        self.assertEqual(ts['02']['questions'], ['Q01-question.md'])
        self.assertFalse(any('仍可开工' in w for w in ts['02']['warnings']))

    def test_unparseable_question_fails_closed(self):
        self.ticket('01')
        self.question('01', status='bogus', blocks='01')
        board = module().load(self.root)
        ticket = board['tickets'][0]
        self.assertEqual(ticket['frontier'], '')
        self.assertEqual(ticket['questions'], ['Q01-question.md'])
        self.assertTrue(board['questions'][0]['unresolved'])

    def test_question_files_change_revision_link_both_ways_and_are_protected(self):
        self.ticket('01', extra='\n见 [Q01](../questions/Q01-question.md)\n')
        board = module()
        first = board.load(self.root)
        (self.root / 'questions').mkdir()
        (self.root / 'questions' / '.Q01-question.md.tmp').write_text('半截', encoding='utf-8')
        (self.root / 'questions' / '.Q02-hidden.md').write_text('# Q02: 隐藏', encoding='utf-8')
        second = board.load(self.root)
        self.assertEqual((second['revision'], second['questions']), (first['revision'], []))
        self.question('01', blocks='none', extra='\n挡住 [01](../issues/01-ticket.md)\n')
        third = board.presentation(board.load(self.root))
        self.assertNotEqual(third['revision'], first['revision'])
        self.assertIn('data-select="ticket:01-ticket.md"', third['questions'][0]['body_html'])
        self.assertIn('data-select="question:Q01-question.md"', third['tickets'][0]['body_html'])
        with self.assertRaises(SystemExit):
            board.main([str(self.root), '-o', str(self.root / 'questions' / 'board.html')])

    def test_http_board_includes_questions(self):
        import threading
        import urllib.request
        self.ticket('01', status='needs-info')
        self.question('01', blocks='01')
        board = module()
        server = board.make_server(self.root, port=0)
        self.addCleanup(server.server_close)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        with urllib.request.urlopen(f'http://127.0.0.1:{server.server_port}/api/board') as response:
            data = json.load(response)
        self.assertEqual(data['questions'][0]['num'], 'Q01')
        self.assertIn('白话说明', data['questions'][0]['body_html'])
        self.assertEqual(data['tickets'][0]['questions'], ['Q01-question.md'])

    def test_browser_shows_questions_first_and_links_both_ways(self):
        import html
        import re
        import shutil
        import subprocess
        chromium = shutil.which('chromium')
        if not chromium:
            self.skipTest('Chromium required for real DOM verification')
        self.ticket('01', status='needs-info')
        self.ticket('02')
        self.question('01', blocks='01', recommended='路线甲')
        self.question('02', status='resolved', blocks='none')
        board = module()
        page = board.build(self.root)
        probe = r"""<script>
const result={};const main=()=>document.getElementById('main').textContent;
const record=()=>{const p=document.createElement('pre');p.id='probe';p.textContent=JSON.stringify(result);document.body.append(p);};
setTimeout(()=>{try{
 const tree=document.getElementById('tree');const first=tree.querySelector('details');
 result.first=first&&first.dataset.group==='questions'&&first.open;
 result.closed=!!tree.querySelector('details[data-group="closedq"]')&&!tree.querySelector('details[data-group="closedq"]').open;
 result.banner=main().includes('1 个问题等你答复')&&main().includes('推荐：路线甲');
 result.summary=document.getElementById('summary').textContent.includes('待答问题 1');
 result.rowTag=document.querySelector('[data-ticket="01-ticket.md"]').textContent.includes('待决 Q01');
 document.querySelector('[data-question="Q01-question.md"]').click();
 result.detail=decodeURIComponent(location.hash).includes('question:Q01-question.md')&&main().includes('推荐')&&main().includes('白话说明');
 document.querySelector('#main .badge.r').click();
 result.toTicket=decodeURIComponent(location.hash).includes('ticket:01-ticket.md');
 document.querySelector('#main .qtag').click();
 result.back=decodeURIComponent(location.hash).includes('question:Q01-question.md');
}catch(e){result.error=String(e);}record();},200);
</script>"""
        page = page.replace('<script id="bootstrap"', probe + '<script id="bootstrap"')
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            directory = Path(directory)
            output = directory / 'board.html'
            output.write_text(page, encoding='utf-8')
            result = subprocess.run([chromium, '--headless=new', '--no-sandbox', '--disable-gpu',
                '--disable-background-networking', '--disable-component-update', '--disable-sync',
                '--no-first-run', '--disable-extensions', f'--user-data-dir={directory / "profile"}',
                '--virtual-time-budget=5000', '--dump-dom', output.as_uri()], capture_output=True, text=True, timeout=35, check=True)
        found = re.search(r'<pre id="probe">(.*?)</pre>', result.stdout, re.S)
        self.assertIsNotNone(found, result.stderr[-1500:])
        observed = json.loads(html.unescape(found[1]))
        self.assertNotIn('error', observed, observed)
        for name in ['first', 'closed', 'banner', 'summary', 'rowTag', 'detail', 'toTicket', 'back']:
            self.assertTrue(observed.get(name), (name, observed))

    def test_ambiguous_dependency_tail_and_contradictory_completion_cannot_be_ready(self):
        self.ticket('01', progress='done', extra='\n## Completion\n已完成。')
        self.ticket('02')
        self.ticket('03', blocked='01 02')
        self.ticket('04', progress='not-started', extra='\n## Completion\n已完成。')
        path = self.ticket('05', progress='not-started')
        path.write_text(path.read_text().replace('Progress:', 'Completed: 2026-09-22\nProgress:'))
        self.ticket('06', blocked='01 错误的标题')
        ts = {t['num']: t for t in module().load(self.root)['tickets']}
        for n in ['03', '04', '05', '06']:
            self.assertFalse(ts[n]['frontier'], n)
            self.assertTrue(ts[n]['errors'], n)

    def test_malformed_link_does_not_break_other_tickets(self):
        self.ticket('01', extra='\n## Reference\n[坏引用](http://[)\n')
        self.ticket('02')
        rendered = module().presentation(module().load(self.root))
        self.assertEqual(len(rendered['tickets']), 2)
        self.assertIn('坏引用', rendered['tickets'][0]['body_html'])
        self.assertEqual(rendered['tickets'][1]['frontier'], 'agent')

    def test_empty_store_is_not_draft_publication_and_export_cannot_overwrite_tickets(self):
        import subprocess
        (self.root / 'issues').rmdir()
        (self.root / 'drafts').mkdir()
        draft = self.root / 'drafts/01-only-draft.md'
        draft.write_text('# 草案\nStatus: draft\n')
        board = module()
        self.assertEqual(board.load(self.root)['counts']['total'], 0)
        self.assertFalse((self.root / 'issues').exists())
        self.assertEqual(draft.read_text(), '# 草案\nStatus: draft\n')
        output = self.root / 'view.html'
        result = subprocess.run(['python3', str(BOARD), str(self.root), '-o', str(output)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('静态快照', output.read_text())
        (self.root / 'issues').mkdir()
        path = self.ticket('01')
        before = path.read_bytes()
        result = subprocess.run(['python3', str(BOARD), str(self.root), '-o', str(path)], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(before, path.read_bytes())
