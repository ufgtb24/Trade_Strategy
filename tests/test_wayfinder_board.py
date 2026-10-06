"""决策看板 scripts/wayfinder_board.py 的回归测试。

- 依赖与渲染：票解决后仍保留全部直接后继；每条依赖边都画出方向（前置 / 后续）与相关票的状态；徽章配色、树里的计数与
  票号颜色、前沿票的悬停反馈不盖过选中态、点票行选中而徽章优先；选中后按相关票状态标出关系条；关系条显示开关默认打开、
  按 effort 记住；
- 实时刷新：版本只随 map.md 与 issues/*.md 的内容变化（草稿、笔记不算）；读取期间文件被改就拒绝这次快照；HTTP 同时
  提供页面与接口，读取失败时报错而不是给出空看板。

只用 Python 标准库，在临时目录里现造 map.md 与票文件，不读仓库里的真实决策票。PATH 上有 chromium 时另在无头浏览器里
验交互（行、徽章、开关与分组）、偏好恢复（坏记录被拒）与实时刷新保留视图状态、挺过读取失败与删除，没有就跳过这三项。
在仓库根运行：
    python3 -m unittest discover -s tests -p 'test_wayfinder_board.py'
"""
import importlib.util
import json
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BOARD_PATH = REPO_ROOT / "scripts" / "wayfinder_board.py"
CHROMIUM = shutil.which("chromium")


def load_board_module():
    spec = importlib.util.spec_from_file_location("wayfinder_board", BOARD_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class WayfinderBoardDependencyTests(unittest.TestCase):
    def setUp(self):
        self.board = load_board_module()
        self.tempdir = tempfile.TemporaryDirectory()
        self.effort = Path(self.tempdir.name)
        (self.effort / "issues").mkdir()
        (self.effort / "map.md").write_text(
            "# Test map\n\n## Destination\n\nTest.\n",
            encoding="utf-8",
        )

    def tearDown(self):
        self.tempdir.cleanup()

    def write_ticket(self, number, status, blocked_by=""):
        dependency = f"Blocked by: {blocked_by}\n" if blocked_by else ""
        (self.effort / "issues" / f"{number}-ticket.md").write_text(
            f"# Ticket {number}\n\n"
            f"Type: grilling\n"
            f"Status: {status}\n"
            f"{dependency}\n"
            f"## Question\n\nQuestion {number}.\n",
            encoding="utf-8",
        )

    def test_load_keeps_all_direct_dependents_after_tickets_resolve(self):
        self.write_ticket("01", "resolved")
        self.write_ticket("02", "resolved", "01")
        self.write_ticket("03", "open", "02")

        _, _, tickets = self.board.load(self.effort)
        by_number = {ticket["num"]: ticket for ticket in tickets}

        self.assertEqual(by_number["01"]["dependents"], ["02"])
        self.assertEqual(by_number["02"]["dependents"], ["03"])
        self.assertEqual(by_number["02"]["waiting"], [])
        self.assertEqual(by_number["03"]["waiting"], [])

    def test_build_renders_direction_and_related_ticket_status_for_every_edge(self):
        self.write_ticket("01", "resolved")
        self.write_ticket("02", "resolved", "01")
        self.write_ticket("03", "open", "02")
        self.write_ticket("04", "claimed", "03")
        self.write_ticket("05", "open", "04")

        page, tickets, _ = self.board.build(self.effort)
        by_number = {ticket["num"]: ticket for ticket in tickets}

        resolved_predecessor = (
            '<a class="badge r is-resolved" href="#t01" '
            'title="前置票 01 · 已解决">01</a>'
        )
        resolved_dependent = (
            '<a class="badge b is-resolved" href="#t02" '
            'title="后续票 02 · 已解决">02</a>'
        )
        unresolved_dependent = (
            '<a class="badge b" href="#t03" '
            'title="后续票 03 · 未解决">03</a>'
        )
        unresolved_predecessor = (
            '<a class="badge r" href="#t03" '
            'title="前置票 03 · 未解决">03</a>'
        )
        self.assertEqual(page.count(resolved_predecessor), 3)
        self.assertEqual(page.count(resolved_dependent), 3)
        self.assertEqual(page.count(unresolved_dependent), 3)
        self.assertEqual(page.count(unresolved_predecessor), 4)
        self.assertEqual(by_number["05"]["lane"], "blocked")
        resolved_view = page.split('data-view="resolved"', 1)[1].split(
            "</section>", 1
        )[0]
        self.assertIn("<th>依赖</th>", resolved_view)
        self.assertIn("前置", page)
        self.assertIn("后续", page)

    def test_badges_use_white_text_and_resolved_badges_use_half_strength_fill(self):
        page, _, _ = self.board.build(self.effort)

        self.assertIn(
            "--red:#d6262b; --blue:#1f66e5; --badge-fg:#ffffff;",
            page,
        )
        self.assertNotIn("@media (prefers-color-scheme:dark)", page)
        self.assertNotIn(':root[data-theme="dark"]', page)
        self.assertIn(
            ".badge.r{background:var(--red);color:var(--badge-fg)}",
            page,
        )
        self.assertIn(
            ".badge.b{background:var(--blue);color:var(--badge-fg)}",
            page,
        )
        self.assertIn(
            ".badge.r.is-resolved{background:color-mix(in srgb,var(--red) 50%,transparent);"
            "color:var(--badge-fg)}",
            page,
        )
        self.assertIn(
            ".badge.b.is-resolved{background:color-mix(in srgb,var(--blue) 50%,transparent);"
            "color:var(--badge-fg)}",
            page,
        )

    def test_tree_tickets_expose_direct_relationships_for_selection(self):
        self.write_ticket("01", "resolved")
        self.write_ticket("02", "resolved", "01")
        self.write_ticket("03", "open", "02")
        self.write_ticket("04", "claimed", "03")
        self.write_ticket("05", "open", "04")
        self.write_ticket("06", "resolved", "04")

        page, _, _ = self.board.build(self.effort)

        self.assertIn(
            '<li class="tk is-resolved" data-node="t02" '
            'data-predecessors="01" data-dependents="03">',
            page,
        )
        self.assertIn(
            '<li class="tk is-claimed" data-node="t04" '
            'data-predecessors="03" data-dependents="05,06">',
            page,
        )

    def test_selection_marks_inset_relation_bars_by_related_ticket_status(self):
        page, _, _ = self.board.build(self.effort)

        self.assertIn(
            "tree.querySelectorAll('.rel-predecessor,.rel-dependent').forEach",
            page,
        )
        self.assertIn(
            "markRelated(li.dataset.dependents,'rel-dependent',li);",
            page,
        )
        self.assertIn(
            "markRelated(li.dataset.predecessors,'rel-predecessor',li);",
            page,
        )
        self.assertIn("markRelations(li);", page)
        self.assertIn(
            ".tk > .row{flex-wrap:wrap;cursor:pointer}",
            page,
        )
        self.assertIn(
            ".tk.rel-dependent > .row::before,.tk.rel-predecessor > .row::before{\n"
            '  content:"";position:absolute;left:0;top:4px;bottom:4px;width:8px;\n'
            "  border-radius:4px;pointer-events:none}",
            page,
        )
        self.assertIn(
            ".tk.rel-dependent > .row::before{background:var(--blue)}",
            page,
        )
        self.assertIn(
            ".tk.rel-predecessor > .row::before{background:var(--red)}",
            page,
        )
        self.assertIn(
            ".tk.is-resolved.rel-dependent > .row::before{background:"
            "color-mix(in srgb,var(--blue) 50%,transparent)}",
            page,
        )
        self.assertIn(
            ".tk.is-resolved.rel-predecessor > .row::before{background:"
            "color-mix(in srgb,var(--red) 50%,transparent)}",
            page,
        )
        self.assertIn(
            ".on > .row{background:var(--sel-bg)}",
            page,
        )
        self.assertNotIn(".tk.on > .row{", page)
        self.assertNotIn("border-left:2px solid transparent", page)

    def test_tree_counts_and_ticket_numbers_use_the_darker_muted_color(self):
        page, _, _ = self.board.build(self.effort)

        self.assertIn(
            ".node i{font-family:var(--mono);font-style:normal;font-size:13px;\n"
            "  color:var(--muted);font-variant-numeric:tabular-nums;",
            page,
        )
        self.assertNotIn(
            "color:var(--faint);font-variant-numeric:tabular-nums;",
            page,
        )

    def test_frontier_ticket_has_hover_feedback_without_overriding_selection(self):
        page, _, _ = self.board.build(self.effort)

        white_hover_rule = (
            ".tk > .row:hover{background:color-mix(in srgb,"
            "var(--surface) 88%,black)}"
        )
        hover_rule = (
            ".tk.is-frontier > .row:hover{background:color-mix(in srgb,"
            "var(--frontier-soft) 88%,black)}"
        )
        selected_rule = ".tk.is-frontier.on > .row{background:var(--sel-bg)}"
        selected_hover_rule = (
            ".on > .row:hover,.tk.is-frontier.on > .row:hover{background:"
            "color-mix(in srgb,var(--sel-bg) 88%,black)}"
        )
        self.assertIn(white_hover_rule, page)
        self.assertIn(hover_rule, page)
        self.assertIn(selected_rule, page)
        self.assertIn(selected_hover_rule, page)
        self.assertLess(page.index(white_hover_rule), page.index(hover_rule))
        self.assertLess(page.index(hover_rule), page.index(selected_rule))
        self.assertLess(page.index(selected_rule), page.index(selected_hover_rule))

    def test_ticket_row_click_selects_ticket_but_badges_keep_priority(self):
        page, _, _ = self.board.build(self.effort)

        self.assertIn("var badge=e.target.closest('a.badge');\n    if(badge) return;", page)
        self.assertIn(
            "if(e.button!==0||e.ctrlKey||e.metaKey||e.shiftKey||e.altKey) return;",
            page,
        )
        self.assertIn("var ticketRow=e.target.closest('.tk > .row');", page)
        self.assertIn(
            "location.hash=ticketRow.parentElement.dataset.node;",
            page,
        )

    def test_relation_visibility_controls_default_on_and_persist_by_effort(self):
        page, _, _ = self.board.build(self.effort)

        self.assertIn('<li class="rel-controls" aria-label="关系条显示">', page)
        self.assertIn(
            '<input type="checkbox" id="toggle-predecessors" checked>前置',
            page,
        )
        self.assertIn(
            '<input type="checkbox" id="toggle-dependents" checked>后续',
            page,
        )
        self.assertIn(
            "var REL_KEY='wayfinder-board:relations:'+(document.body.dataset.effort||'');",
            page,
        )
        self.assertIn(
            "var relationPrefs={predecessors:true,dependents:true};",
            page,
        )
        self.assertIn(
            "if(savedRelations&&typeof savedRelations.predecessors==='boolean'&&\n"
            "       typeof savedRelations.dependents==='boolean'){\n"
            "      relationPrefs.predecessors=savedRelations.predecessors;\n"
            "      relationPrefs.dependents=savedRelations.dependents;\n"
            "    }",
            page,
        )
        self.assertIn(
            "if(relationPrefs.dependents) markRelated(li.dataset.dependents,'rel-dependent',li);",
            page,
        )
        self.assertIn(
            "if(relationPrefs.predecessors) markRelated(li.dataset.predecessors,'rel-predecessor',li);",
            page,
        )
        self.assertIn(
            "localStorage.setItem(REL_KEY,JSON.stringify(relationPrefs));",
            page,
        )
        self.assertIn("relationControls.forEach(function(input){", page)
        self.assertIn("markRelations(nodes[current()]);", page)

    @unittest.skipUnless(CHROMIUM, "Chromium is required for board interaction checks")
    def test_browser_executes_row_badge_toggle_and_group_interactions(self):
        self.write_ticket("01", "resolved")
        self.write_ticket("02", "open", "01")
        self.write_ticket("03", "open", "02")
        self.write_ticket("04", "resolved", "02")
        page, _, _ = self.board.build(self.effort)
        probe = textwrap.dedent(
            """
            <script>
            (function(){
              var body=document.body;
              function put(k,v){body.setAttribute('data-test-'+k,String(v));}
              function later(fn){setTimeout(fn,20);}
              later(function(){
                var row2=document.querySelector('[data-node="t02"] > .row');
                var row3=document.querySelector('[data-node="t03"] > .row');
                var bar=getComputedStyle(row3,'::before');
                put('bar-width',bar.width);
                put('bar-gap',Math.round(
                    row3.getBoundingClientRect().height-parseFloat(bar.height)));
                put('selected-bar',getComputedStyle(row2,'::before').content);
                put('resolved-closed',document.querySelector('[data-node="resolved"]')
                    .classList.contains('closed'));
                row3.click();
                later(function(){
                  put('row-click',location.hash);
                  row2.click();
                  later(function(){
                    row2.querySelector('a.badge.r').click();
                    later(function(){
                      put('badge-click',location.hash);
                      row2.click();
                      later(function(){
                        var pred=document.getElementById('toggle-predecessors');
                        var dep=document.getElementById('toggle-dependents');
                        var badgeCount=row2.querySelectorAll('a.badge').length;
                        pred.click();
                        later(function(){
                          put('pred-count',document.querySelectorAll('.rel-predecessor').length);
                          put('dep-count',document.querySelectorAll('.rel-dependent').length);
                          put('badges-stay',row2.querySelectorAll('a.badge').length===badgeCount);
                          var key='wayfinder-board:relations:'+body.dataset.effort;
                          var saved=JSON.parse(localStorage.getItem(key));
                          put('saved',saved.predecessors+','+saved.dependents);
                          pred.click();
                          document.querySelector('[data-node="unresolved"] > .row > a.node').click();
                          later(function(){
                            put('group-clears',document.querySelectorAll(
                              '.rel-predecessor,.rel-dependent').length);
                          });
                        });
                      });
                    });
                  });
                });
              });
            })();
            </script>
            """
        )
        page = page.replace("</body>", probe + "</body>")

        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as browser_dir:
            browser_dir = Path(browser_dir)
            board_path = browser_dir / "board.html"
            board_path.write_text(page, encoding="utf-8")
            result = subprocess.run(
                [
                    CHROMIUM,
                    "--headless=new",
                    "--no-sandbox",
                    "--disable-gpu",
                    "--disable-background-networking",
                    "--disable-component-update",
                    "--disable-sync",
                    "--no-first-run",
                    "--disable-extensions",
                    f"--user-data-dir={browser_dir / 'profile'}",
                    "--virtual-time-budget=1500",
                    "--dump-dom",
                    board_path.as_uri() + "#t02",
                ],
                capture_output=True,
                text=True,
                timeout=30,
                check=True,
            )

        dom = result.stdout
        self.assertIn('data-test-bar-width="8px"', dom)
        self.assertIn('data-test-bar-gap="8"', dom)
        self.assertIn('data-test-selected-bar="none"', dom)
        self.assertIn('data-test-resolved-closed="true"', dom)
        self.assertIn('data-test-row-click="#t03"', dom)
        self.assertIn('data-test-badge-click="#t01"', dom)
        self.assertIn('data-test-pred-count="0"', dom)
        self.assertIn('data-test-dep-count="2"', dom)
        self.assertIn('data-test-badges-stay="true"', dom)
        self.assertIn('data-test-saved="false,true"', dom)
        self.assertIn('data-test-group-clears="0"', dom)

    @unittest.skipUnless(CHROMIUM, "Chromium is required for preference restore checks")
    def test_browser_restores_valid_preferences_and_rejects_corrupt_records(self):
        self.write_ticket("01", "resolved")
        self.write_ticket("02", "open", "01")
        self.write_ticket("03", "open", "02")
        base_page, _, _ = self.board.build(self.effort)

        def render_with(saved_value):
            board_script = "<script>" + self.board.JS + "</script>"
            bootstrap = (
                "<script>localStorage.setItem('wayfinder-board:relations:'"
                "+document.body.dataset.effort,"
                + json.dumps(saved_value)
                + ");</script>"
            )
            probe = textwrap.dedent(
                """
                <script>
                document.body.setAttribute('data-test-predecessors',
                  document.getElementById('toggle-predecessors').checked);
                document.body.setAttribute('data-test-dependents',
                  document.getElementById('toggle-dependents').checked);
                document.body.setAttribute('data-test-pred-count',
                  document.querySelectorAll('.rel-predecessor').length);
                document.body.setAttribute('data-test-dep-count',
                  document.querySelectorAll('.rel-dependent').length);
                </script>
                """
            )
            page = base_page.replace(
                board_script, bootstrap + board_script, 1
            ).replace("</body>", probe + "</body>")
            with tempfile.TemporaryDirectory(dir=REPO_ROOT) as browser_dir:
                browser_dir = Path(browser_dir)
                board_path = browser_dir / "board.html"
                board_path.write_text(page, encoding="utf-8")
                result = subprocess.run(
                    [
                        CHROMIUM,
                        "--headless=new",
                        "--no-sandbox",
                        "--disable-gpu",
                        "--disable-background-networking",
                        "--disable-component-update",
                        "--disable-sync",
                        "--no-first-run",
                        "--disable-extensions",
                        f"--user-data-dir={browser_dir / 'profile'}",
                        "--virtual-time-budget=500",
                        "--dump-dom",
                        board_path.as_uri() + "#t02",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=True,
                )
            return result.stdout

        restored = render_with(
            json.dumps({"predecessors": False, "dependents": True})
        )
        self.assertIn('data-test-predecessors="false"', restored)
        self.assertIn('data-test-dependents="true"', restored)
        self.assertIn('data-test-pred-count="0"', restored)
        self.assertIn('data-test-dep-count="1"', restored)

        for corrupt in (
            "{broken",
            json.dumps({"predecessors": False, "dependents": "bad"}),
        ):
            with self.subTest(corrupt=corrupt):
                fallback = render_with(corrupt)
                self.assertIn('data-test-predecessors="true"', fallback)
                self.assertIn('data-test-dependents="true"', fallback)
                self.assertIn('data-test-pred-count="1"', fallback)
                self.assertIn('data-test-dep-count="1"', fallback)


class WayfinderBoardLiveRefreshTests(unittest.TestCase):
    def setUp(self):
        self.board = load_board_module()
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.effort = Path(self.tempdir.name)
        (self.effort / "issues").mkdir()
        (self.effort / "map.md").write_text(
            "# Test map\n\n## Destination\n\nTest.\n", encoding="utf-8"
        )

    def write_ticket(self, number, status, blocked_by="", question=None,
                     answer="", claimed=""):
        path = self.effort / "issues" / f"{number}-ticket.md"
        path.write_text(
            f"# Ticket {number}\n\nType: grilling\nStatus: {status}\n"
            + (f"Claimed: {claimed}\n" if claimed else "")
            + (f"Blocked by: {blocked_by}\n" if blocked_by else "")
            + f"\n## Question\n\n{question or f'Question {number}.'}\n"
            + (f"\n## Answer\n\n{answer}\n" if answer else ""),
            encoding="utf-8",
        )
        return path

    def test_revision_follows_map_and_ticket_contents_only(self):
        ticket = self.write_ticket("01", "open")
        first = self.board.snapshot(self.effort)[0]

        self.assertEqual(self.board.snapshot(self.effort)[0]["revision"], first["revision"])
        (self.effort / "notes.md").write_text("scratch", encoding="utf-8")
        (self.effort / "drafts").mkdir()
        (self.effort / "drafts" / "02-draft.md").write_text("# draft", encoding="utf-8")
        self.assertEqual(self.board.snapshot(self.effort)[0]["revision"], first["revision"])

        ticket.write_text(ticket.read_text(encoding="utf-8").replace("open", "claimed"),
                          encoding="utf-8")
        edited = self.board.snapshot(self.effort)[0]
        self.assertNotEqual(edited["revision"], first["revision"])
        self.assertIn('<li class="tk is-claimed" data-node="t01"', edited["tree"])

        map_path = self.effort / "map.md"
        map_path.write_text(map_path.read_text(encoding="utf-8") + "\nMore.\n",
                            encoding="utf-8")
        self.assertNotEqual(self.board.snapshot(self.effort)[0]["revision"],
                            edited["revision"])

    def test_snapshot_refuses_files_that_change_while_being_read(self):
        ticket = self.write_ticket("01", "open")
        original_load = self.board.load

        def load_during_edit(effort):
            ticket.write_text(ticket.read_text(encoding="utf-8") + "\nEdited.\n",
                              encoding="utf-8")
            return original_load(effort)

        self.board.load = load_during_edit
        with self.assertRaisesRegex(OSError, "读取期间文件发生变化"):
            self.board.snapshot(self.effort)

    def test_http_serves_live_page_api_and_failures_without_empty_board(self):
        import threading
        import urllib.error
        import urllib.request

        ticket = self.write_ticket("01", "open")
        server = self.board.make_server(self.effort, port=0)
        self.addCleanup(server.server_close)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        url = f"http://127.0.0.1:{server.server_port}"

        with urllib.request.urlopen(url + "/") as response:
            page = response.read().decode("utf-8")
        self.assertIn('"live": true', page)
        self.assertIn('data-node="t01"', page)
        with urllib.request.urlopen(url + "/api/board") as response:
            self.assertIn("no-store", response.headers["Cache-Control"])
            initial = json.load(response)
        self.assertEqual({"title", "summary", "tree", "main", "revision", "generated_at"},
                         set(initial))
        self.assertIn(initial["revision"], page)

        ticket.write_text(ticket.read_text(encoding="utf-8").replace("open", "resolved"),
                          encoding="utf-8")
        with urllib.request.urlopen(url + "/api/board") as response:
            self.assertNotEqual(json.load(response)["revision"], initial["revision"])

        with self.assertRaises(urllib.error.HTTPError) as missing:
            urllib.request.urlopen(url + "/../map.md")
        self.assertEqual(missing.exception.code, 404)

        (self.effort / "map.md").unlink()
        with self.assertRaises(urllib.error.HTTPError) as failed:
            urllib.request.urlopen(url + "/api/board")
        self.assertEqual(failed.exception.code, 503)
        self.assertIn("map.md", json.load(failed.exception)["error"])
        with urllib.request.urlopen(url + "/") as response:
            broken = response.read().decode("utf-8")
        self.assertIn("读不出这个 effort", broken)
        self.assertIn('"revision": null', broken)
        self.assertIn('"live": true', broken)

    @unittest.skipUnless(CHROMIUM, "Chromium is required for live refresh checks")
    def test_browser_refresh_keeps_view_state_and_survives_failure_and_delete(self):
        self.write_ticket("01", "resolved")
        long_question = "\n\n".join(f"阅读段落 {n}" for n in range(90))
        ticket = self.write_ticket("02", "open", "01", long_question, answer="答案正文。")
        self.write_ticket("03", "open", "02")
        initial = self.board.snapshot(self.effort)[0]
        page, _, _ = self.board.build(self.effort, live=True)
        self.write_ticket("02", "claimed", "01", "刷新增加的内容\n\n" + long_question,
                          answer="答案正文。", claimed="2026-09-23 tester")
        updated = self.board.snapshot(self.effort)[0]
        ticket.unlink()
        removed = self.board.snapshot(self.effort)[0]
        payload = json.dumps([initial, updated, removed], ensure_ascii=False).replace(
            "<", "\\u003c"
        )
        probe = r"""<script>
const snapshots=PAYLOAD;const result={};let n=0,reference=null,offset=0;
const record=()=>{const p=document.createElement('pre');p.id='probe';p.textContent=JSON.stringify(result);document.body.append(p);};
const para=()=>[...document.querySelectorAll('[data-view="t02"] p')].find(p=>p.textContent.trim()==='阅读段落 45');
window.fetch=async()=>{n++;const round=n;setTimeout(()=>{try{
 if(round===1)result.unchanged=reference===para();
 if(round===2){
  result.selected=location.hash==='#t02';
  result.moved=document.querySelector('[data-node="claimed"] [data-node="t02"]')!==null;
  result.summary=document.getElementById('summary').textContent.includes('认领 1');
  const block=para();result.scroll=!!block&&block!==reference&&Math.abs(block.getBoundingClientRect().top-offset)<3;
  result.groupKept=!document.querySelector('[data-node="resolved"]').classList.contains('closed');
  result.toggleKept=!document.getElementById('toggle-predecessors').checked&&!document.querySelector('.rel-predecessor');
  result.related=document.querySelector('[data-node="t03"]').classList.contains('rel-dependent');
  result.answerKept=document.querySelector('[data-view="t02"] details.answer').open;
  result.fresh=document.getElementById('refresh').textContent.startsWith('最后成功读取');
 }
 if(round===3){result.stale=!document.getElementById('error').hidden;
  result.retained=!document.querySelector('[data-view="t02"]').hidden&&!!para();}
 if(round===4){const main=document.getElementById('main').textContent;
  result.deleted=main.includes('票已删除')&&main.includes('02 · Ticket 02');
  result.noJump=location.hash==='#t02';
  result.recovered=document.getElementById('error').hidden;record();}
}catch(e){result.error=String(e);record();}},100);
 if(n===3)throw Error('模拟连接失败');
 // late font loads shift layout, so measure the reading line as the refresh lands
 if(n===2)offset=para().getBoundingClientRect().top;
 return {ok:true,json:async()=>snapshots[n===1?0:n===2?1:2]};};
setTimeout(()=>{try{
 document.querySelector('[data-node="resolved"] > .row > button.tg').click();
 document.getElementById('toggle-predecessors').click();
 document.querySelector('[data-view="t02"] details.answer').open=true;
 reference=para();reference.scrollIntoView();
}catch(e){result.error=String(e);record();}},100);
</script>""".replace("PAYLOAD", payload)
        page = page.replace('<script id="bootstrap"', probe + '<script id="bootstrap"')

        with tempfile.TemporaryDirectory(dir=REPO_ROOT) as browser_dir:
            browser_dir = Path(browser_dir)
            board_path = browser_dir / "board.html"
            board_path.write_text(page, encoding="utf-8")
            result = subprocess.run(
                [
                    CHROMIUM,
                    "--headless=new",
                    "--no-sandbox",
                    "--disable-gpu",
                    "--disable-background-networking",
                    "--disable-component-update",
                    "--disable-sync",
                    "--no-first-run",
                    "--disable-extensions",
                    f"--user-data-dir={browser_dir / 'profile'}",
                    "--virtual-time-budget=10000",
                    "--dump-dom",
                    board_path.as_uri() + "#t02",
                ],
                capture_output=True,
                text=True,
                timeout=35,
                check=True,
            )

        import html
        import re

        found = re.search(r'<pre id="probe">(.*?)</pre>', result.stdout, re.S)
        self.assertIsNotNone(found, result.stderr[-1500:])
        observed = json.loads(html.unescape(found[1]))
        self.assertNotIn("error", observed, observed)
        for name in ["unchanged", "selected", "moved", "summary", "scroll", "groupKept",
                     "toggleKept", "related", "answerKept", "fresh", "stale", "retained",
                     "deleted", "noJump", "recovered"]:
            self.assertTrue(observed.get(name), (name, observed))


if __name__ == "__main__":
    unittest.main()
