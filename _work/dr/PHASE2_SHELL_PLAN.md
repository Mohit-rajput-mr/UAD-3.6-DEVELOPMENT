# DR phase 2 — editor shell: implementation plan

> **Owner addendum 2026-10-11 (T-1210, overrides where it differs).** Every
> region is a window: the top bar, the Sections rail, the right sidebar
> (Field guidance / Sign-off / Problems / worksheet drawer), the report pane
> and the Sketch each get their own **minimize, maximize, close/restore** and
> **drag-resize**, remembered per user -- "similar to how each browser window
> can be controlled". Nothing is fixed in place or size. Minimized regions
> collapse to an icon/chip from which they are restored; maximize gives one
> region the whole work area; close hides it until restored from the ribbon /
> View menu / palette. The report takes the room the others give up (and has
> its own zoom). The Sketch opens as a window (docked or floating, resizable,
> maximizable) rather than a fixed full-screen overlay. Spacing is less
> cramped (owner: "all components look too tight", "report looks too small").
> Applies to steps S2 (panels), S3 (title/status bar, focus, zoom) and S8
> (split view); S2 must deliver the window chrome for all regions.

_Synthesised 2026-10-11 from two independent read-only designs (minimal-risk, operator-first). Brief §3-§4; plan D1 (built into engine/app/ui). Tasks T-272..T-277, T-505, T-507, T-508._

## Control inventory (nothing dropped)

How to read this. Nothing is dropped. "Original" means the real DOM node is moved: its id and handler stay the same. "Clone" means a ribbon or palette entry (data-cmd, data-for) that runs the same command, either by clicking the original or by calling the same function with the button it came from. It mirrors the original's disabled, checked and text state. "Command" means an entry in the one registry behind the ribbon, palette, keys and tests. With ?shell=0, every control stays exactly where it is today.

Files:
- /home/user/UAD-3.6-DEVELOPMENT/engine/app/ui/index.html
- /home/user/UAD-3.6-DEVELOPMENT/engine/uad/report/flow.py (EDIT_JS/FIT_JS)

HEADER (<header>, l.673-687). Its markup does not change. Under body.shell, CSS turns it into a 40 px title bar.
- #backhome (All reports; flushPending then showLaunch). Stays at the left. Also the command app.home, in the quick-access toolbar and the palette.
- .logo mk-w/mk-b and the .bt wordmark (T-271). They stay. In case view under body.shell only the mark shows. The launcher is unchanged.
- #nav (setNav). Launcher only, unchanged.
- #crumb (setCrumb from drawHead). chrome.js redraws it as report chips:
  - a highlighted type chip, e.g. "2- to 4-unit · 3 units";
  - borrower 2.001 · client 2.012;
  - subject address 3.000;
  - a status chip (Draft / In review / Signed / Exported, with signed_by in its title).
  The case name moves to the chip title and the status bar. Under ?shell=0, setCrumb writes it as today.
- #stat (fatal / warning / to read / XSD vN). Stays, and is now redrawn by drawStat() from setReview() on every review. This fixes the stale header count, E-186: the owner saw 144 in the header and 143 in Sign-off. Under body.shell the chips are clickable and open Problems filtered to that severity; XSD vN is also shown in the status bar.
- #dl-product (UADDownload.open). Stays: web only, hidden on desktop. Also a palette command.
- #theme (tellTheme). Stays. Clone in Home›View. Palette. The theme now goes to every report frame through frames.send(to:'all').
- #topbar progress line: unchanged.
- New: a quick-access toolbar in the header with Save, Next problem, Split, Focus and Palette. These are commands only.

WORK HEAD (#head, drawHead l.1265). Still drawn, so ?shell=0 and every drawHead call site are unchanged. Hidden under body.shell.
- h1 case name: chip title and status bar.
- State chip: status chip.
- property_type: type chip.
- <code>case_id: status bar; a click copies it.
- "updated x ago": status bar.
- "signed by": status chip title.
- #tabs buttons stay in the hidden #tabs. View commands .click() them, so drawHead/drawWork remain the only path:
  - Report: Home›View and Report›Views.
  - Property (structure), Additional Data (extra), History: Report›Views.
  - Preview: Report›Views and Deliver›Check.
  - Comparables: Comparables›Grid.
  - Location Map: Location Map›Map tool.
  - Review Master: Review›All problems. In shell mode this opens the Problems panel expanded to at most 50% width, beside the report (brief §4: never covering it). The classic drawReview view serves ?shell=0 and widths of 820 px or less.
  - Sign-off (NARROW only): Deliver›Sign-off. In shell mode NARROW() returns false because the docks own narrow widths, so Sign-off is the right-dock panel, reachable from its rail icon at any width.

REPORT TOOLBAR (.rf-bar, drawReportForm l.1492-1516). On 'form-drawn' the originals are adopted into Ribbon›Home. They are released on 'case-open'/'case-close', which fire before #shell is rebuilt, so drawReportForm's $('#id') wiring never finds a stale duplicate. The empty bar is hidden under body.shell.
- Label "Filling in the report itself" and the .rf-note text: moved verbatim into the Home›Show "Legend ▾" popover, and used as a tooltip.
- .rf-key colour legend (Type… / Select ▾ / $ # / MM/DD/YYYY / Yes/No): Home›Show›Legend ▾.
- #rf-gaps ({uad:'gaps'}): original in Home›Show, still an <input type=checkbox> (test_checkbox_centre checks and unchecks it). Clone in Review›Markers. Now sent to every pane.
- #rf-marks (S.showMarks, localStorage uad-marks, postMarks): original in Home›Show, labelled "Problem markers". Clone in Review›Markers, plus a toggle in the Problems panel header. In shell mode it is on by default when nothing is stored (T-507, brief §4); a stored choice wins.
- #rf-imp-wrap / #rf-imported (showImportedToggle): original in Home›Show; still hidden until the case has an import.
- #rf-lib (commentLibrary, #libpop, Alt+1..9): original in Home›Fill. Clone as the palette entry "Insert comment…". Clones call commentLibrary(the button that was clicked), so the popover anchors to what was clicked, not to a hidden original.
- #rf-sadj (worksheets()): original in Home›Tools. It stays on the default tab because test_worksheet_grid clicks it. The Worksheets tab gets:
  - a large clone;
  - one button per worksheet kind, from the same GET /cases/{id}/worksheets list worksheets() reads, each calling worksheets(kind);
  - "This row (Ctrl+J)", which sends wsOpen to the active pane.
  A clone also goes in Comparables›Adjust.
- #rf-sketch (openSketch, #sketch-ov): original in Home›Tools. The Sketch tab gets an "Open sketch" clone and "Go to Sketch section" (goto secn 7, offered only when that section prints).
- #rf-setup (reportSetup): original in Home›Report. Clone in Report›Setup.
- #rf-maps (POST /maps): original in Home›Map & market. Clones in Location Map›"Sales comparison map" and Comparables. They mirror its disabled state and its "Drawing the map…" text.
- #rf-market (marketImport): original in Home›Map & market. Clones in Report›Market and Exhibits›Market.
- #rf-msearch (marketSearch): original in Home›Map & market. Clones in Report›Market and Exhibits›Market.
- #rf-auto (chooseFillSource, primary) and the hidden #rf-auto-file: originals in Home›Fill; the file input moves with the button. Clone in the Report tab.
- #rf-reload (swapFrame): original in Home›Fill. Clone in Report›Setup as "Reload layout". Palette. It swaps every pane.
- body.kind-other keeps hiding #rf-maps/#rf-market/#rf-msearch/#rf-auto by id. Clones carry [data-for] plus the command predicate when(kind==='urar'). The Comparables, Location Map and Sketch tabs are hidden on update and completion reports.
- #rf-agent fill-progress strip: stays above the panes; its text is mirrored in the status bar.
- .rf-busy "Updating layout": stays; the status bar also shows "Layout: updating…" from S.checking.
- #rf-body and #rf: never re-parented.

NEW HOME GROUPS. Commands only; no new write path.
- Save:
  - Save (Ctrl+S) and Save & Next (Ctrl+Shift+S) send {uad:'flush', page:true, next} to the active pane.
  - That is the same savePage as the page-side Save / Save & Next.
- This section:
  - "Shown in report" clicks #secsw-on in #insp-sec; offered only for optional sections.
  - "Add ▾" lists S.adds and posts the existing {uad:'add-go', i}.
  - "Mark reviewed" clicks the #acks checkbox for S.atSection (POST /acknowledge).
- Navigate: Go to field (Ctrl+G), Prev / Next problem (Shift+F8 / F8), Palette (Ctrl+K).
- View: Focus (F11), Split ▾ (off / side by side / stacked; new window in stage 2), Sections panel, Right panel ▾, Zoom ▾, Theme.

OTHER RIBBON TABS
- Exhibits:
  - Add exhibit ▾: the report's own .exadd entries from S.adds; a click sends add-go.
  - Photos by section ▾: counts from S.media; a click sends goto.
  - The market clones.
- Review: Problems panel, All problems (expanded), Prev / Next problem, Fix at cursor (Ctrl+.), Re-run review (reviewSoon now), Mark section reviewed, Guidance panel, the marker clones.
- Deliver:
  - Sign-off panel, Move to review (#rev), Sign off (#sign), Open PDF (#openpdf), Export ZIP (#zip), MISMO XML and Portable XML (the existing links), Preview;
  - New Restricted Appraisal Update (#mkru), New Completion Report (#mkcr);
  - a package-status chip, from the #pkg result fillSignoff already fetches.
  Each clicks the element in #insp-sign, so there is one code path.

SECTIONS RAIL (nav#rail; drawRail, markRail, .railitem with badges, progress, st-good/warn/bad, "left out")
- On 'shell-built' it is moved, not rebuilt, into the left dock's "Sections" panel.
- The panel header gets a filter box. It only filters what is displayed.
- Collapsed, it uses today's number-only look (the 820 px one) plus status dots.

INSPECTOR (aside#insp, drawInsp). It becomes the right dock itself: a dock header, an icon rail and panel wrappers. The #insp-* nodes are moved inside, so $('#insp-sign') still finds them and drawInsp never rebuilds.
- Problems: new, at the top.
- Field guidance holds three existing nodes, moved with their render functions unchanged:
  - #insp-guide (renderGuide, including the T-510 "Make it …" buttons);
  - #insp-sec (#secsw-on);
  - #insp-add (.addit).
  Guidance badges its icon; it never takes over the panel that is open.
- Sign-off: #insp-sign (fillSignoff), contents unchanged: counts, verdict, blockers, #pkg, #acks, #rev, #sign, #zip, #openpdf, the MISMO XML and portable XML links, #back, #mkru, #mkcr.
- Bug fixed in the move (S0a, E-187):
  - fillSignoff assigns $$('#zip').onclick twice, at l.2973 and l.2996. The second replaces the first, so on a client-layout host (Vercel) Export ZIP never calls exportZip().
  - Fix: one handler. It refuses when unsigned (the existing dialog); otherwise it calls exportZip() when !HOST.serverLayout, or follows the link.

WORKSHEET DRAWER (#wsdock, body.ws-open)
- Controls: #wsd-title, #wsd-rate, #wsd-thr, #wsd-round, #wsd-ok, #wsd-cancel, .wsd-x, #wsd-all, #wsd-saveprof, #wsd-delprof, #wsd-back, .wsd-row.
- Unchanged. While open it takes the right column. The ws-open grid rule is restated under body.shell (left dock / report / --ws-w) and the right dock hides.
- The Esc capture handler and Ctrl+J are unchanged. Pane 2's 'worksheet' and 'ws-esc' messages are forwarded to worksheets() and wsClose().

REVIEW MASTER VIEW (drawReview, findingRow, applyFixButton, jump)
- Kept for ?shell=0 and widths of 820 px or less.
- findingRow gets the honest labels in S7: "Fix: <label>", "Go to field", "Go to section", or a plain reason.
- "Re-run the review" also appears in the Problems panel header and the Review tab.

OTHER VIEWS (#panel), unchanged:
- drawStructure (+ Dwelling / Living unit / ADU / Outbuilding, #ob-type, remove);
- drawExtra;
- drawComps (kind tabs, + comparable, saveCell, column drag and resize, remove, photo);
- the map iframe (its own Save to report);
- Preview (#pv, #keep-preview);
- drawHistory.

OVERLAYS, unchanged; commands open them:
- setup su-*;
- fill-source sheet (#fs-file / #fs-sample / #fs-cancel);
- market import (#mk-copy / #mk-example / #mk-go / #mk-close);
- market search (#ms-go / #ms-close);
- #libpop, #sketch-ov, UADDialog (.uadd-back), toasts.

INSIDE THE REPORT FRAME (flow.EDIT_JS)
- Unchanged: + Add rows and exhibits, the (+) .wsi worksheet icons, pick lists, Yes/No boxes, certx, ptyadd/ptyx, Summary click-through, Alt+1..9, Ctrl+J, Enter / Esc / Ctrl+Enter on fields.
- The page-side Save / Save & Next (.pageside, UAD_SIDE 240 px) are kept. Under body.shell the parent sends {uad:'side', mode:'compact'}, a 48 px icon gutter; focus mode sends 'none'. ?shell=0 keeps 'full'.

LAUNCHER (case list, new report, import): unchanged. The ribbon, docks and status bar are hidden there.

## Architecture

DECISION
- Backbone: Design A, the feature-flagged, additive shell.
  - New files go under /home/user/UAD-3.6-DEVELOPMENT/engine/app/ui/shell/.
  - index.html gets one-line hooks; original controls are moved, never re-implemented.
  - The iframe is never re-parented, the worksheet drawer is untouched, and every existing test keeps its ids and geometry.
  - Why: index.html and EDIT_JS carry dozens of CATALOG fixes, phase 1 (T-416) is still in flight on the lead branch, and the shell has to reach production behind a kill switch.
- Grafted from Design B:
  1. setReview(rv): one sink for every review result, replacing A's five scattered emits. It fixes the stale #stat at its source.
  2. A frames registry: broadcast send, plus replay at 'ready' and in finishSwap. Today finishSwap re-sends gaps and imported but not marks, and the swap frame's 'ready' is swallowed at l.1318. This is E-188, and pane 2 needs it too.
  3. The double #zip onclick fix.
  4. Report geometry: a compact 48 px Save gutter and zoom, handled inside the frame, with a measured chrome budget at 1280×720 CSS px (the owner's laptop at 150%).
  5. Field resolution inside the frame: goto v2 plus a locate round trip. The parent never depends on contentDocument, and pane 2 and a detached window behave the same.
  6. In-frame BroadcastChannel sync for split view. A second window then comes for free.
  7. Engine enrichment early: role, where/locus, plain XSD text and not_counted on review items.
  8. The richer ribbon groups, the quick-access toolbar, viewport-based dock defaults and the focus-mode mini bar. "All problems" becomes the expanded side panel rather than a full-screen view.
  9. One CSS file per module, so parallel steps never merge into one shell.css.
  10. Extra keys: Ctrl+Shift+S, Ctrl+., F6 and Ctrl+/.
- Rejected from B:
  - Deleting the classic paths now (NARROW, .rf-bar, drawReview). They stay behind ?shell=0 until the owner accepts phase 2; new task T-1209 removes them.
  - The worksheet drawer as a dock panel: no gain, and it breaks test_worksheet_grid's geometry.
  - A popover in EDIT_CSS: form.py is ecstatic-bohr's print side. The card is drawn by the parent instead.
  - ?key= on the form route. Not needed: _rendered/_shared_page already serves the kept layout by key.
  - Folding in T-1201: it was handed to epic-brahmagupta, so its repair route is consumed when it lands.
  - Ctrl+Alt+= / - / 0 (AltGr on European layouts) and Ctrl+Shift+M (Chrome's profile switcher).
- Rejected from A:
  - Parent-side contentDocument locate (frame messages instead).
  - The S10 full-screen Review Master re-render (brief §4).
  - A single shell.css with regions.
  - The numbers T-1204 and E-184: both are taken. T-1204 went to epic-brahmagupta; E-184 is T-1072's CATALOG entry.
  - Free in the lead's block: T-1205..T-1249 and E-186..E-189. Claim E-190..E-199 in _work/agents/claude-sleepy-hypatia-e2pzcn.json before using them.

FEATURE FLAG (A)
- core.js adds body.shell, and every shell rule is scoped under it.
- Default on. ?shell=0, or localStorage uad-shell=off, gives the classic editor and is remembered; ?shell=1 turns the shell back on.
- Vanilla JS, no build step (D2: React stays for the new large screens in ui-shared).

FILES (engine/app/ui/shell/). S0a creates them all as stubs, with their <link>/<script> tags, so no later step touches index.html's <head>.
- core.js;
- shell.css (body grid and tokens only);
- commands.js;
- ribbon.js + ribbon.css;
- docks.js + docks.css;
- chrome.js + chrome.css (title bar, status bar, focus mode);
- problems.js + problems.css;
- markers.js + markers.css;
- palette.js + palette.css;
- split.js + split.css.
Each module starts with `if(!UADShell.enabled())return;`.

LOAD ORDER AND CACHE
- Synchronous <script src="/ui/shell/x.js?v={{SHELLV}}"> tags go after the main inline script. They run before DOMContentLoaded, and so before start(), and can read the global S, $ and api and call drawHead, goToReport, checkFresh, swapFrame, applyFixButton, reviewSoon, refresh, worksheets and markRail.
- <link> tags go in <head>.
- main.py home() substitutes {{SHELLV}} with a SHA-1 of the bytes of ui/shell/*, computed once at import, never from file times (AI_HANDOVER rule).
- Vercel rewrites every path to api/index.py, so the same home() serves both hosts. /ui is plain StaticFiles with no cache-busting today, so without this a new index.html could run with an old shell file.

core.js (window.UADShell)
- enabled().
- Bus: on/emit, fed by the DOM CustomEvents 'uad:*'.
- State: localStorage 'uad-shell-v1':
  {v, ribbon{tab, collapsed}, left{w, pinned, collapsed}, right{w, pinned, collapsed, open{problems, guide, signoff}}, problems{sev, src, group, thisSection}, split{mode, ratio}, zoom, palette{mru}}.
  Versioned, clamped on load, every access in try/catch. Defaults depend on the viewport:
  - at least 1600 px wide: both docks pinned (left 220, right 340);
  - narrower: icon rails, unpinned;
  - under 800 px high: ribbon collapsed.
- commands.register({id, label, tab, group, icon, keys, run, when, state, adopt:'#id'}), plus run(id) and list(). Unknown ids are tolerated, so modules can land in any order.
- panels.register({id, title, icon, el, badge, side}). Until docks.js lands, the stub host mounts panels at the top of #insp.
- Keymap: normalise(e), one capture keydown listener, Esc stack, combos pushed to every frame at 'ready' and 'frame-ready' as {uad:'shell-keys', combos}, and the forwarded {uad:'key', combo} dispatched.
- frames:
  - all(), active(), of(source), send(msg, {to:'all'|'active'}), replay(win);
  - #rf is pane 1 and #rf2 pane 2;
  - swap frames are tagged and ignored; #pv receives theme only;
  - active() is the last pane that sent {uad:'focus'}, defaulting to pane 1.
- Message router: re-emits frame messages tagged with their pane.

HOOKS IN index.html (S0a, the only index.html work outside S7)
- shellEmit(t, d) emits:
  - case-close: top of showLaunch;
  - case-open: top of openCase, before #shell.innerHTML;
  - shell-built: right after #shell.innerHTML;
  - view: top of drawWork;
  - head: end of drawHead;
  - form-drawn: end of drawReportForm;
  - insp: end of drawInsp;
  - write {path, ok}: in apiRaw, for non-GET requests.
- setReview(rv) replaces the five S.review sites: EDITOR.get in openCase (l.1168), refresh (l.1191), saved-sections (l.1488), autoFillDone (l.1755) and reviewSoon (l.2396). It:
  - sets S.review;
  - calls drawRail, markRail and postMarks;
  - calls drawStat(), the #stat block taken out of drawHead (l.1289-1293);
  - calls fillSignoff when #insp-sign is visible;
  - emits 'review'.
  Callers keep their own drawHead/drawWork/drawInsp after it.
- tellTheme, postMarks, the #rf-gaps and #rf-imported handlers, insert, add-go and wsFrame go through UADShell.frames.send when it exists, falling back to #rf as today. 'ready' and finishSwap call frames.replay: theme, gaps, imported, marks, side and zoom.
- NARROW becomes `()=>!(window.UADShell&&UADShell.ownsNarrow())&&matchMedia('(max-width:1240px)').matches`.
- The single #zip handler.
- The link and script tags.

FRAME PROTOCOL v2 (S0b; flow.py EDIT_JS and FIT_JS only; additive)
- S0b adds anchored blocks so later edits never collide: /* shell:bridge */, /* shell:goto */, /* shell:marks */, /* shell:side */, /* shell:sync */ (left empty; S8 fills it), and in FIT_JS /* shell:zoom */.
- 'saved' gains {fid, tf, tk, gf, gc, iscope, ordinal, shown (the printed value from res.d.value)}. A payload-less 'saved' (rooms, media, certx) still means "something changed".
- {uad:'pending', n} as inflight changes; {uad:'save-failed', fid, detail} on a failed write.
- Key forwarder: on capture keydown, if not defaultPrevented and the combo is in the parent's list, preventDefault and tell {uad:'key', combo}.
- {uad:'flush', page, next}: blur, await inflight, optionally savePage for the page in view; replies {uad:'flushed', ok, failed}.
- {uad:'refocus'} restores the last focused field. {uad:'focus'} is sent on focusin and mousedown.
- goto v2 {fid, secn, gc, scope, k, focus, code} tries, in order:
  1. .v[data-fid], matched by the longest data-iscope prefix;
  2. .bxs .bx[data-fid];
  3. td[data-gf][data-gc];
  4. the k-th [data-tf];
  5. goSection.
  It then scrolls to the centre and flashes 'found', and focuses the control: caret at the end of a contenteditable; a pick list focused but not opened; the first box of a Yes/No group. It replies goto-result {found, fid, gc, how}. Today's callers are unchanged.
- {uad:'locate', fids} → {uad:'located', map:{fid:'field'|'section'|''}}, counting visible elements only.
- marks v2 accepts today's arrays [fid, sev, msg] (index.html and test_checkbox_centre post them) or objects {fid, sev, code, msg, gc?, scope?}. With gc, only that grid column is outlined; today the whole row lights up. Hover or focus on .mk-* sends {uad:'mark-at', fid, gc, rect}; leaving or scrolling sends {uad:'mark-off'}.
- {uad:'side', mode:'full'|'compact'|'none'} sets UAD_SIDE to 240 / 48 / 0. Compact shows icon Save buttons; the savecheck popover anchoring is re-checked.
- FIT_JS: {uad:'zoom', z:'fit'|0.5-1.0}. zoom = fit × z, capped at 1.0 until pick-list and grid-editor positions are verified above it.

LAYOUT (body.shell)
- Body rows: title bar 40 / #ribbon auto (92 open, 28 collapsed) / main 1fr / #statusbar 22. Each element gets an explicit grid-row, so a hidden ribbon cannot shift main.
- main#shell: div#dock-l / minmax(0,1fr) / aside#insp.
  - On 'shell-built', docks.js inserts #dock-l and moves nav#rail into it. Moving the nav is safe: there is no iframe in it.
  - body.shell.ws-open: dock-l / report / --ws-w.
- Collapsed dock: a 36-44 px icon rail with badges (Problems shows the fatal count).
- Unpinned: a shutter, position:absolute over the report edge. It never changes #rf's width and closes on a click in the report or on Esc.
- Resize: a 6 px splitter with pointer capture. body.shell-drag sets iframe{pointer-events:none}. Double-click resets. Width is clamped to 180 px..50vw.
- Narrow screens: at 1240 px or less, the docks become rails or shutters (ownsNarrow() is true), so Sign-off stays reachable. At 820 px or less, the ribbon shows tabs plus an overflow menu. ?shell=0 keeps today's media queries.
- Budget at 1280×720:
  - chrome at most 160 px expanded and 90 px collapsed;
  - with both docks collapsed and the compact gutter, page zoom 1.0;
  - B estimates 0.52 today. S0a records the measured baseline; estimates are not recorded as fact.

FOCUS MODE (chrome.js)
- body.shell-focus hides the title bar, ribbon, docks and status bar, and frames get side 'none'.
- A 6 px hot edge at the top reveals a mini bar: Exit, counts, Prev / Next problem.
- F8, Ctrl+K and Ctrl+S keep working.
- Not persisted, so no one reloads into a screen with no chrome.
- The Fullscreen API is used only when F11 started focus mode; failures are ignored.

SPLIT VIEW (split.js; stage 1 is two panes)
- #rf2 (class rf-frame, src /api/cases/<id>/form?case=<id>&pane=2) and a gutter are appended to .reportform, which becomes a CSS grid: "p1 gut p2", or stacked. #rf and #rf-body are never moved, because moving an iframe or an ancestor reloads it.
- Pane 2's header: a section picker (goto), close, swap and orientation.
- Sync (S8 fills /* shell:sync */):
  - Channel: BroadcastChannel('uad-case-'+id).
  - After each successful write, the pane publishes {seq, src, fid | tf+tk | gf+gc, iscope, ordinal, shown}.
  - Receivers patch the matching element unless it is focused or .saving, and update [data-derived].
  - relayout, reshaped, structure and media make the parent run checkFresh('form') for pane 1 and split.js's own copy of the swap for pane 2 (same busy rules as swapFrame).
  - The same channel serves the stage-2 window (?pane=solo, T-1208) and two tabs open on one case.
- Routing:
  - goto, F8, insert, add-go and Ctrl+J go to the active pane;
  - marks, theme, gaps, imported, side and zoom go to all panes;
  - pane 2 is inert during the fill run;
  - the status bar names the active pane.

HEADER AND STATUS BAR (chrome.js)
- GET /api/cases/{id} gains summary {type_name, units, borrower, client, address}:
  - derived through bind in printed form;
  - type_name from templates.PROPERTY_TYPES;
  - memoised per document version.
  Enriched 'saved' messages for 2.001, 2.012 and 3.000 patch the chips at once.
- #statusbar:
  - save state ("Saving…" from pending, "Save failed" (a click locates the field), "Saved · 2 s ago" ticker);
  - counts, with a click opening Problems;
  - current section (S.atSection);
  - focused field id;
  - view;
  - layout state (S.checking / S.swaps);
  - active pane;
  - zoom controls (−, Fit, +);
  - XSD version;
  - case id (a click copies it) and "updated".

PER-USER STATE
- localStorage per browser profile. The desktop launcher's --user-data-dir makes that per Windows user.
- There is no server-side identity behind the shared passcode, so nothing goes to case prefs.

## Problems side panel

WHAT IT IS
- problems.js registers the panel 'problems' through UADShell.panels. It sits at the top of the right dock; before S2 lands, at the top of #insp; on narrow screens, as a shutter.
- The "Expand" command (Review›All problems, and the Review Master view command in shell mode) widens it to at most 50%, beside the report. It never covers the report (brief §4).
- The title-bar totals always count the whole report, whatever the filter.

DATA SOURCE
- The existing GET /api/cases/{id}/review, already held in S.review. It is memoised per document version server-side.
- Each item carries source, severity, code, message, field_id, section_number, section, subsection, label, path, detail and fix.
- E1 adds:
  - role (Finding.role is computed today but dropped by Item);
  - where {scope, comp, unit}: the failing instance;
  - plain: plain English for XSD text;
  - not_counted (true when detail starts "not counted:", the T-506 shown_in items).
- counts and ready are unchanged.
- No new endpoint and no polling: on the serverless host every review costs a durable pull.

LIVE UPDATES
- The panel redraws on the 'review' bus event, which setReview() emits. That covers refresh, reviewSoon (1.5 s after 'saved'), saved-sections, autoFillDone, applyFixButton, the worksheet OK and the optional-section switch.
- Between a 'saved' and the next 'review' the header shows "Checking…", then "as of 14:02:11".
- "Re-run" calls reviewSoon() at once.
- Rows are keyed by code|field_id|where, so selection and scroll survive a refresh. New rows flash and cleared rows fade.
- The redraw is skipped when a hash of the keys is unchanged.
- At most 300 rows per group, with "show all".
- Counts use the same items and section_number as the rail's sevCount. A test pins that the panel, rail badges, #stat, status bar and Sign-off agree.

FILTERS (persisted in shell state; search lasts the session only)
- Severity chips with counts, multi-select:
  - Fatal: every Fatal item, XSD included, matching #stat and Sign-off;
  - Warning;
  - Info (severity 'Review');
  - Schema: source 'schema', also tagged on its rows.
  Default: Fatal + Warning + Schema.
- Source filter: H-1 compliance / B-1 usability / owner checks / XSD / completeness.
- "This section only", which follows S.atSection.
- Search over code, message, label, field_id and section, debounced at 120 ms.
- Group by Section (default), Severity or Rule.

GROUPING
- In report order:
  - "File structure (XSD)" first;
  - then "Whole file (no field on the page)" for section_number 0;
  - then the sections in S.sections order, with the rail's names.
- Within a group: Fatal, then Warning, then Info, then by code. Groups collapse and show their F/W counts.
- Last, collapsed: "Not counted: sections this report leaves out (n)", holding the not_counted items. They are honest and visible, and never mixed into the counts.

EACH ROW
- A severity glyph and the code (H-1 Message ID, U10.x, O1-4 or XSD).
- The plain one-line message:
  - item.plain when present;
  - otherwise the message with the "For assistance with this message, contact the appraisal software vendor." boilerplate stripped.
- The location, e.g. "Unit Interior › Finished Above Grade · Unit 2" or "· Comparable 2", from where.
- Where E1 shows more than one instance may fail, the row says "first of possibly several": H-1 reports the first failing instance, so after a fix the next one can appear with the same count.
- The selected row expands to show the H-1 logic, the detail and its actions.
- Keys in the panel: Up / Down select, Enter goes to the field, Ctrl+. applies the fix, Home / End.

CLICK TO FIELD: UADShell.problems.locate(item)
1. If S.view is not 'report', call goToReport({secn}) and keep the item pending. The report iframe is kept alive, so this is instant.
2. Wait while the active pane is not ready or a swap is in flight (S.swaps.form): retry on the next 'ready' or after finishSwap, for up to 30 s.
3. Send frames.active() goto v2 {fid, secn, gc:where.comp, scope:where.scope, k:where.unit, focus:true, code, sev}.
   - The frame resolves .v / .bx / grid column / table row, scrolls to the centre, flashes 'found' and focuses the control.
   - Focusing a contenteditable raises the frame's focusin, then /guide, so Field guidance follows.
   - The frame's spy() posts 'at', so the rail and status bar follow.
4. On goto-result found:false, show the honest next step (see Fix this). The existing toasts stay for the rail and jump paths.
5. Until E1 lands, where is empty: the frame picks the first empty candidate, then the first visible one. A presence rule fires on its first missing instance.

REACHABILITY
- After each 'ready', each finishSwap and each review, the panel sends {uad:'locate', fids} and gets back {uad:'located', map}.
- canLocate(item) reads that map. No row ever shows a button that would do nothing.

F8 / SHIFT+F8
- Commands problems.next and problems.prev walk the filtered, sorted list.
- The cursor starts at the first item in a section at or after S.atSection, and wraps at the ends.
- They work with the panel closed: each step runs locate and opens the marker card at the field. If the panel is open, its selection follows.

INLINE MARKERS (T-507, markers.js)
- The existing outline pipeline is kept: postMarks → {uad:'marks'} → EDIT_JS mark() → .mk-fatal / .mk-warn, toggled by #rf-marks.
- postMarks now sends objects {fid, sev, code, msg, gc, scope}, so a grid row lights only the faulty comparable column.
- In shell mode markers are on when nothing is stored (brief §4: "every field with a problem shows a red/amber marker inline"). A stored uad-marks wins.
- On 'mark-at', the parent draws a card at the frame's rect plus the field's rect. No CSS is injected into the frame and form.py is not touched. The card shows:
  - the severity;
  - every S.review finding on that fid (and gc): H-1 id, plain message, rule logic in small text;
  - "Fix: <label>" when item.fix exists;
  - "Rule & guidance", which focuses the field so Field guidance shows it;
  - "Show in list", which selects the row in the panel;
  - "Next ▸ F8".
- The card closes on 'mark-off', a scroll or Esc.

FIX THIS (T-508). Reuses T-510; there is no second write path.
- T-510 already gives Item.fix = {field_id, value, label}. applyFixButton(fx) sends PATCH /cases/{id}/fields/{fid}, then calls swapFrame('form'), refresh() and reviewSoon(). The same button already appears in renderGuide.
- E2 adds engine/uad/fixes.py. It attaches fixes to H-1 items only where the spec leaves exactly one answer:
  - an enumeration value matching exactly one A-1 value ignoring case and spacing;
  - a single near-miss within edit distance 2, with confirm:true;
  - a malformed stored date or number that parses unambiguously (parser shared with T-278);
  - values from existing engine authorities only (rent_math, grid_math), never new arithmetic.
- fix may also carry route / scope / ordinal / key for grid, table and comparable writes, and confirm.
- S7 extends applyFixButton:
  - honour route, using the same PATCH routes EDIT_JS uses (/cells, /comparables/{n}/fields);
  - honour confirm, asking UADDialog.confirm first.
  The panel row, the marker card, Field guidance, the palette ("Fix: Make it Subject to Repair") and Ctrl+. all call it.
- Primary action per row, the first that applies:
  1. "Fix: <label>";
  2. "Go to field" (located = field);
  3. "Go to section" (located = section);
  4. "Show section" (an optional section switched off: PUT /sections/optional/n through #secsw-on, then go);
  5. "Go to <gate question>" (a field hidden by an answered gate: the new read-only engine/uad/gates.py names it, using form.edit_hides with no form.py edit);
  6. "Open in Additional Data" (a field whose only home is drawExtra).
  Otherwise there is no button, only a plain reason:
  - "Written by the package (Does Not Display)";
  - "Section not in this report (B-1), not counted";
  - "File structure (XSD): software defect. Repair comes with T-1201". When epic-brahmagupta's POST /cases/{id}/repair lands, kind:'repair' fixes call it.
- The navigate-only "Fix this" label is retired everywhere, findingRow included.

## Keyboard and command palette

WHERE KEYS ARE REGISTERED
- core.js owns the only keymap. Each module declares keys on its own commands, e.g. {id:'problems.next', keys:['F8']}.
- One normaliser: [Ctrl (Meta on a Mac)][Alt][Shift] + key, where key is e.key uppercased when it is one character, otherwise e.key ('F8', 'Tab', 'PageDown', '\\', '.', '/').
- One capture-phase keydown listener on the parent document.
- Report frames: the parent's keydown never fires while the caret is inside an iframe.
  - At every 'ready' and 'frame-ready' (#rf and #rf2), core sends {uad:'shell-keys', combos}.
  - The S0b forwarder calls preventDefault for exactly those combos (when not already defaultPrevented) and posts {uad:'key', combo}.
  - The map stays in one place, so a new key never needs a flow.py change.
- The sketch and map iframes have no forwarder: F8 and Ctrl+K do nothing there, and Esc closes them as today.
- The palette lists every command with its keys. Ctrl+/ (or ? outside a text field) opens a cheat sheet generated from the keymap.

THE MAP
- Ctrl+S: save.
  - {uad:'flush', page:true} to every pane: blur the open edit (EDIT_JS's focusout commit), await inflight, then savePage for the page in view, which is the page-side Save.
  - Parent inputs (the comps grid's saveCell) are blurred too.
  - The status bar says "Saved · just now", or lists the fields that failed.
  - The browser's Save As is blocked. It never presses the worksheet's OK.
  - Every value is already saved per field, and the status text says exactly what happened.
- Ctrl+Shift+S: Save & Next.
- Ctrl+G: palette in Fields scope ('@').
  - Search by label or field id (3.000, 22.07.30), using GET /api/fields/directory.
  - Fields on this report (from the locate map) come first; others are marked "not in this report".
  - It lands through locate, with focus.
- Ctrl+K: palette, all scopes.
  - Prefixes: commands '>', sections '#' (printed only), fields '@', problems '!', Add '+' (posts add-go).
  - Most recently used first.
  - On close, focus returns through {uad:'refocus'}.
- F8 / Shift+F8: next / previous problem. Works with the panel closed.
- Ctrl+.: apply the fix for the problem at the cursor (the selected row, or the focused field's finding). It asks first when fix.confirm is set.
- Ctrl+Tab / Ctrl+Shift+Tab: next / previous printed section (clicks the next .railitem). Alt+PageDown / Alt+PageUp do the same everywhere, because browser tabs keep Ctrl+Tab.
- F11: focus mode. Ctrl+Shift+F is the fallback everywhere, with the palette and Home›View›Focus.
- Ctrl+F1: collapse or expand the ribbon. Double-clicking a ribbon tab does the same.
- Ctrl+\: split side by side, on and off. Stacked mode and the stage-2 new window are ribbon and palette only.
- F6 / Shift+F6: move focus between title bar/ribbon, Sections, report, right dock and status bar (Office convention, §14 accessibility).
- Zoom: status-bar controls and the palette only. No key: plain Ctrl+= / - / 0 stay with the browser.
- Panels: no default keys. They open from the ribbon, the icon rails and the palette ("Problems panel", "Field guidance", "Sign-off", "Sections").

ESC: ONE PRIORITY STACK IN core. It closes the first open item, in this order:
1. the palette;
2. the marker card;
3. UADDialog (.uadd-back), whose own handler acts;
4. #libpop and the sheets (setup, fill, market), whose own handlers act;
5. the worksheet drawer, through its existing capture handler, unchanged;
6. an open dock shutter;
7. focus mode.
- Inside the report frame, EDIT_JS keeps first claim: Esc reverts a field or closes a pick list (defaultPrevented) and is never forwarded.
- The frame's existing {uad:'ws-esc'} still closes an open worksheet. When none is open, the shell runs steps 6 and 7.

KEPT AS THEY ARE (owned by EDIT_JS, never in the forwarded list)
- Ctrl+J: the worksheet for the current row.
- Alt+1..9: comment library.
- Enter, Ctrl+Enter, Esc in fields.
- Space and Enter on pick lists, boxes, .wsi and room / party / exhibit controls.
- Arrow keys in the grid editor, setup screen and dialogs.
- The worksheet drawer's Esc capture handler.

NEVER BOUND
- Ctrl+Alt+<anything>: AltGr is Ctrl+Alt on European layouts; on German, AltGr+0 is }.
- Alt+digit.
- Ctrl+B / I / U: contenteditable rich-text commands.
- Ctrl+Z / Y: browser undo in a field; left free for §14 undo.
- Ctrl+P.
- Ctrl+T / N / W.
- Ctrl+Shift+M: Chrome's profile switcher.
- Any plain character key.
- A guard test fails if a shell combo hits this list.

MANUAL VERIFICATION REQUIRED
- Ctrl+Tab, F11, F6, Ctrl+S, Ctrl+G, Ctrl+K, Ctrl+F1, Ctrl+. and F8 must be checked by hand in the Edge --app window (desktop/launcher.py), in Chrome and, later, in Tauri / WebView2.
- Playwright delivers synthetic key events even for combos a real browser keeps, so a green test does not prove these keys work.
- S9 records each as verified or "unverified (reason)".

## Risks

1. Duplicate ids after adopting controls.
   - drawReportForm wires buttons with $('#id') straight after innerHTML. If the previous case's moved buttons are still in #ribbon, which comes earlier in document order, the new case's buttons are never wired.
   - Mitigation: release the adopted nodes on 'case-open' and 'case-close'. Both fire before #shell is rebuilt.
   - A test opens A, then B, then the list, then A, and checks every id exists exactly once.

2. Moving an iframe, or any ancestor of one, reloads it.
   - #rf, #rf-body and #pv are never re-parented. Docks move only nav#rail and the #insp-* blocks, which hold no iframe.
   - Split view uses CSS grid areas on .reportform and appends #rf2.
   - Tests assert that #rf's contentWindow is unchanged.

3. Body grid auto-placement.
   - A hidden #ribbon or #statusbar shifts main into the wrong row. Every element gets an explicit grid-row.
   - Fixed overlays (#topbar, toasts, dialogs) are out of grid flow.

4. Iframes swallow pointer events during splitter drags.
   - body.shell-drag sets iframe{pointer-events:none}, plus pointer capture.

5. Keys the browser keeps for itself.
   - Ctrl+Tab, F11 and F6 (in some browsers and in the Edge --app window), and Ctrl+Shift+M (Chrome's profile switcher, so unbound) may never reach the page. Ctrl+S, Ctrl+G and Ctrl+K need preventDefault.
   - Playwright's synthetic events pass regardless, so green tests prove nothing about these keys.
   - Mitigation: each key has a fallback (Alt+PageDown/PageUp, Ctrl+Shift+F, the palette, the ribbon), and S9 runs a manual checklist recorded as verified or unverified. Tauri (D3) removes most of this.

6. Typing conflicts.
   - Never bind Ctrl+Alt+<anything>: AltGr is Ctrl+Alt on European layouts, so B's Ctrl+Alt+= / - / 0 zoom is dropped.
   - Never bind Alt+digit (comment library), Ctrl+J (worksheet), Ctrl+B/I/U (contenteditable) or Ctrl+Z/Y.
   - EDIT_JS keeps first claim on Esc inside fields and pick lists, and the worksheet's capture handler is untouched.
   - A guard test enforces all of this.

7. Render-key churn and flow.py ownership.
   - renders._code_digest includes flow.py, so any EDIT_JS or FIT_JS change re-lays every kept report on its next open (seconds on Vercel).
   - Mitigation:
     - all frame work goes into S0b in anchored blocks; only S8's sync block follows;
     - the deploy happens once, in S9, at a quiet time;
     - plan() and render() (ecstatic-bohr) and EDIT_CSS/form.py are not touched;
     - the marker card is drawn by the parent.

8. Stale static assets.
   - /ui is plain StaticFiles with no cache-busting.
   - Mitigation: ?v={{SHELLV}}, a SHA-1 of the content, never file times, so every Vercel instance agrees. home() serves both hosts through api/index.py.

9. Existing tests depend on controls and defaults.
   - test_worksheet_grid clicks #rf-sadj and checks the drawer sits beside the report.
   - test_checkbox_centre checks and unchecks #rf-gaps as a real checkbox, and posts marks as arrays.
   - Mitigation:
     - the originals live in the default Home tab;
     - body.ws-open is restated for the shell;
     - marks v2 accepts arrays as well as objects;
     - turning markers on by default needs one explicit uncheck of #rf-marks in test_checkbox_centre's 'no problem shown' phase. Same intent; state made explicit, which is allowed under "validate your validators".

10. Markers on by default changes what the owner sees on every report.
    - A blank 2-4 report has about 149 fatals of outlines.
    - It follows brief §4 ("every field with a problem shows a marker"). The toggle and its stored choice stay.
    - Flag it in HANDOFF so the owner can reverse it.

11. Findings carry no instance until E1.
    - compliance.evaluate stops at the first failing instance and keeps only role_seen. Until E1, "first empty candidate" can land on the wrong unit or comparable.
    - E1 must leave the 12 samples' findings identical, and needs keen-turing's agreement: compliance.py and review.py hooks are theirs.
    - H-1 reports one instance per rule, so a fixed row can be replaced by the next instance with the same count. The row says "first of possibly several", or the fix looks failed.

12. 'Fix this' must never invent an answer or be a dead button.
    - fixes.py applies only where the spec leaves one answer. Each class is validated on the 12 samples (no suggestion) and on mutated copies (the finding clears, nothing new appears, still XSD-valid).
    - There is no second write path: T-510's shape and applyFixButton, extended with route and confirm.
    - The locate map, the gate lookup and the optional-section switch decide the button. Otherwise a reason is shown instead of a button.

13. Ownership and numbering collisions.
    - Design A's T-1204 and E-184 are taken: T-1204 was handed to epic-brahmagupta, and E-184 is T-1072's CATALOG entry.
    - T-1201 (XSD repair) belongs to epic-brahmagupta, so kind:'repair' waits for their route.
    - Use T-1205.. and E-186..E-189, and claim E-190..E-199 in the lead's status file before using them. keen-turing holds E-170..179; ecstatic-bohr holds E-300..339.
    - Post on the agents board before S0a (index.html), S0b and S8 (EDIT_JS), and E1/E2 (compliance.py / review.py).
    - Never push to another session's branch.

14. Phase 1 still in flight.
    - T-416 edits the #rf-maps handler in drawReportForm, next to S0a's form-drawn emit.
    - Phase-1 dropdown work sits near sendNow, where S0b enriches 'saved'.
    - Rebase both S0 steps on the lead branch head and coordinate T-416's merge first.

15. Stale header counts are a live bug today.
    - Only drawHead writes #stat. reviewSoon, saved-sections and the EDITOR.get path do not. The owner's screenshot shows 144 against 143.
    - setReview() fixes it at the source (E-186). A test pins that the header, status bar, panel, rail badges and Sign-off agree.

16. The double #zip onclick is a live production bug.
    - The second assignment drops the client-side exportZip() on Vercel.
    - It is fixed in S0a with a test (E-187), rather than copied into the ribbon.

17. Marks are not replayed after a swap.
    - finishSwap re-sends gaps and imported only, and the swap frame's 'ready' is swallowed, so outlines vanish until the next review.
    - frames.replay fixes it (E-188), and pane 2 needs it too.

18. Split view: cost and correctness.
    - Two frames double the DOM, and a structural change re-lays both panes.
    - Sync: ignore your own source token; never patch a focused or saving element; sequence numbers per field.
    - The last write wins when one field is edited in both panes.
    - The fill run replays only into #rf, so pane 2 is inert during it.
    - BroadcastChannel also syncs two tabs on one case. That is intended, and documented.
    - Half-width panes are small even with the compact gutter. Stacked is the default under 1600 px.
    - The detached window needs Tauri multi-window configuration later.

19. The compact Save gutter.
    - Moving from 240 to 48 px changes where savecheck popovers anchor and could clip them at the page edge.
    - S0b's e2e covers 'Saved ✓' in compact mode. ?shell=0 keeps 240.

20. The kill switch doubles the layouts to maintain.
    - Both ?shell=0 and the shell must pass the smoke test until T-1209 retires the classic path after the owner's acceptance.

21. Narrow screens.
    - Under the shell, ownsNarrow() hands widths of 1240 px or less to the docks (rails and shutters), so Sign-off stays reachable. ?shell=0 keeps today's NARROW tab.
    - Docks must not fight the 1240 px and 820 px media queries (main and aside.inspector rules); they are overridden under body.shell. Test at 1200 px.

22. localStorage may be unavailable (private window, locked profile).
    - Every access is in try/catch, with defaults.
    - "Per user" means per browser profile; the desktop launcher's --user-data-dir makes that per Windows user. There is no cross-device roaming.

23. The performance budget.
    - The shell must not slow opening a case or typing.
    - Skip unchanged redraws, cap rows, debounce search, observe single elements only (never the frame), and avoid polling (every /review is a durable pull on the serverless host).
    - Measure in S9 against T-1064.

24. No fake controls.
    - Every ribbon, quick-access, palette and panel button resolves to a registered command whose run() does something real. The 'click every ribbon command' test enforces it.
    - Clones mirror the original's disabled and busy state.
    - kind-other predicates hide the URAR-only commands and tabs.

25. Same-origin and client-layout pages.
    - The client-layout page uses document.open/write, which erases listeners the parent attaches.
    - All frame behaviour (keys, hover, goto, locate, sync) therefore lives in EDIT_JS, and the parent talks to frames only by message.

## Steps

### S0a — Shell core, index.html hooks, setReview, frames registry, kill switch, cache digest, test kit (new task T-1205; fixes E-186 stale header counts, E-187 #zip client export, E-188 marks not replayed after a swap)

- Tasks: 1) Write shell/core.js:
   - enabled() flag: ?shell=0/1, localStorage uad-shell, body.shell;
   - bus;
   - versioned 'uad-shell-v1' store with viewport defaults;
   - commands and panels registries (stub host at the top of #insp);
   - keymap with normaliser, capture listener, shell-keys push at ready/frame-ready, Esc stack;
   - frames registry: all, active, of, send, replay;
   - ownsNarrow();
   - message router tagging the pane.
2) Create every module stub (commands, ribbon, docks, chrome, problems, markers, palette, split) and its CSS stub, plus shell.css with the body.shell grid and an explicit grid-row on header / #ribbon / main / #statusbar.
3) index.html, hooks only:
   - shellEmit and the eight emits;
   - setReview(rv) replacing the five S.review sites (l.1168, 1191, 1488, 1755, 2396), with drawStat() taken out of drawHead;
   - tellTheme / postMarks / gaps / imported / insert / add-go / wsFrame routed through frames.send with a fallback to #rf;
   - frames.replay at 'ready' and in finishSwap (theme, gaps, imported, marks);
   - the NARROW one-liner;
   - one #zip handler in fillSignoff;
   - the <link> and <script> tags with ?v={{SHELLV}}.
4) main.py home(): substitute {{SHELLV}} with a content SHA-1 of ui/shell/*, computed once.
5) engine/tests/shell_kit.py: test_worksheet_grid's in-process uvicorn fixture made shared (cookie = app.main.ACCESS.token, 1600x1000, pageerror capture), with helpers open_case, frame, until, and measure_chrome at 1280x720 to record the baseline chrome height and page zoom.
6) Add shell/*.js to test_browser_scripts _sources and shell/*.css to _stylesheets.
7) Register T-1205..T-1209. CATALOG E-186, E-187 and E-188, each with its test.
8) Post on the agents board first: index.html hooks, plus the numbers being used.
- Files: /home/user/UAD-3.6-DEVELOPMENT/engine/app/ui/shell/ (all new: core.js, shell.css, commands.js, ribbon.js/.css, docks.js/.css, chrome.js/.css, problems.js/.css, markers.js/.css, palette.js/.css, split.js/.css stubs); /home/user/UAD-3.6-DEVELOPMENT/engine/app/ui/index.html (hooks, setReview, drawStat, frames routing, replay, NARROW line, #zip handler, tags; no other region); /home/user/UAD-3.6-DEVELOPMENT/engine/app/main.py (home() only); /home/user/UAD-3.6-DEVELOPMENT/engine/tests/shell_kit.py (new); /home/user/UAD-3.6-DEVELOPMENT/engine/tests/test_shell_core.py (new); /home/user/UAD-3.6-DEVELOPMENT/engine/tests/test_browser_scripts.py (source lists); /home/user/UAD-3.6-DEVELOPMENT/knowledge/errors/CATALOG.md; /home/user/UAD-3.6-DEVELOPMENT/TASKS.md
- Tests: test_shell_core.py:
- With the shell on: body.shell is set, no pageerror.
- ?shell=0: the classic #tabs and .rf-bar are visible and there is no body.shell; the choice survives a reload; ?shell=1 restores the shell.
- {{SHELLV}} is replaced in the served index; the digest is the same across two imports and changes when a shell file changes.
- E-186: after an edit that changes the counts, #stat == Sign-off counts == S.review.counts, without a reload.
- E-188: after swapFrame('form') with Show problems on, the new frame has .mk-* outlines before any new review.
- E-187: with HOST.serverLayout false and the case signed, clicking #zip calls exportZip() (stubbed); unsigned, it raises the existing dialog.
- A 'uad:review' DOM event fires from each of the five paths.
Also run:
- the 8 browser tests: test_worksheet_grid, test_checkbox_centre, test_add_list, test_choice_saves_browser, test_grid_rows_browser, test_vehicle_storage, test_client_pdf, test_desktop;
- test_browser_scripts;
- the full suite;
- harness 12, expecting 88/0/20.
Pin playwright==1.56.0 (Chromium 1194).
- Depends on: Rebase onto the lead branch claude/sleepy-hypatia-e2pzcn (307370b, T-1072/T-125). Coordinate with T-416, which is still in flight: it edits the #rf-maps handler in drawReportForm, next to the form-drawn emit. Wave 0: runs in parallel with S0b and E1, because it touches no flow.py and no engine file.

### S0b — Frame protocol v2 in EDIT_JS / FIT_JS (new task T-1206)

- Tasks: All additive, inside anchored blocks /* shell:bridge|goto|marks|side|sync */ and FIT_JS /* shell:zoom */; the sync block is left empty for S8.
1) 'saved' gains {fid, tf, tk, gf, gc, iscope, ordinal, shown}. {uad:'pending', n} from send()/inflight. {uad:'save-failed', fid, detail} in sendNow's !res.ok branch.
2) Key forwarder driven by the parent's {uad:'shell-keys', combos}. {uad:'flush', page, next} → {uad:'flushed', ok, failed} (blur, await inflight, savePage for the page in view). {uad:'refocus'}. {uad:'focus'} on focusin and mousedown.
3) goto v2:
   - resolution order: .v[data-fid] with the longest data-iscope prefix → .bxs .bx → td[data-gf][data-gc] → the k-th [data-tf] → goSection;
   - scroll to the centre, flash 'found';
   - focus rules: caret at the end of a contenteditable, a pick list focused but not opened, the first Yes/No box;
   - goto-result gains gc and how;
   - existing {fid, secn} callers behave exactly as today.
4) {uad:'locate', fids} → {uad:'located', map}, visible elements only.
5) marks v2:
   - accept arrays (as today) or objects;
   - with gc, outline only that column;
   - mouseover / focusin on .mk-* → {uad:'mark-at', fid, gc, rect};
   - mouseleave / scroll → {uad:'mark-off'}.
6) {uad:'side', mode}: 240 / 48 / 0 px gutter with icon Save buttons in compact mode; savecheck anchoring kept on the page.
7) FIT_JS: {uad:'zoom', z} multiplies the fit factor, capped at 1.0.
8) Post on the agents board: EDIT_JS/FIT_JS change once, which gives every kept report a new render key at the next deploy. ecstatic-bohr's plan()/render() are not touched.
- Files: /home/user/UAD-3.6-DEVELOPMENT/engine/uad/report/flow.py (EDIT_JS and FIT_JS strings only); /home/user/UAD-3.6-DEVELOPMENT/engine/tests/test_frame_protocol.py (new; carries its own fixture in the test_checkbox_centre / test_worksheet_grid pattern so it does not wait for S0a)
- Tests: test_frame_protocol.py drives the real editor and posts to and listens on #rf from the page:
- Typing in 3.000 yields 'saved' with fid=3.000 and shown equal to the printed value.
- 'pending' goes 1, then 0.
- A forced 400 yields 'save-failed' with the fid.
- After shell-keys ['F8'], F8 pressed in a focused field arrives as {uad:'key', combo:'F8'}.
- Ctrl+J and Alt+1 are never forwarded and still work.
- flush with an open edit sends the PATCH, then 'flushed' ok.
- goto v2 on a 2-4 report with gc=2 focuses td[data-gf][data-gc=2]; scope picks unit 2's copy; a pick list is focused but not opened.
- locate returns field / section / '' correctly for a printed field, a field in a section that is off, and a field not on the report.
- marks with object items and gc outline one column; array items (test_checkbox_centre's form) still work.
- Hovering an outlined field posts mark-at with a rect inside the frame.
- side 'compact' leaves Save visible and working ('Saved ✓'); side 'none' gives a page wider by 240 px.
- zoom 0.75 gives .page style.zoom = fit × 0.75; the preview without the message is unchanged.
Also run:
- the 8 browser tests, test_checkbox_centre especially (unchanged);
- test_golden;
- harness 12.
- Depends on: Rebase onto the lead branch. Board post. Wave 0: runs in parallel with S0a and E1, because it touches no index.html and no engine file other than flow.py's script strings.

### E1 — Review items carry their instance, role, plain text and not-counted flag (new task T-1207)

- Tasks: 1) compliance.evaluate records the failing instance's element at the point it already sets role_seen (l.998 and l.1020). This is a new Finding field, default ''. Rule logic does not change.
2) New engine/uad/locate.py turns that instance into where:
   - scope: the stable path of the nearest dwelling/unit scope, matching the data-iscope the editor prints;
   - comp: n, numbered as comparables.py numbers data-gc;
   - unit: k, in unit order.
3) review.Item gains:
   - role;
   - where;
   - plain: XSD 'Expected is ( X )' turned into plain English, e.g. 'AMENITY_CATEGORY_DETAIL is before AMENITIES; a software defect, not something to type';
   - not_counted.
   to_json includes them.
4) Post to keen-turing on the agents board first: compliance.py and review.py hooks are theirs.
- Files: /home/user/UAD-3.6-DEVELOPMENT/engine/uad/compliance.py (evaluate: record the instance only); /home/user/UAD-3.6-DEVELOPMENT/engine/uad/review.py (Item fields, _compliance_items / schema items); /home/user/UAD-3.6-DEVELOPMENT/engine/uad/locate.py (new); /home/user/UAD-3.6-DEVELOPMENT/engine/tests/test_problem_locus.py (new)
- Tests: - On the 12 D-1 samples, findings are identical before and after (codes, field_ids, severities, counts, ready); test_golden and test_applicable_findings are unchanged.
- On a mutated 2-4 copy with unit 2's above-grade GLA blanked, where.scope names unit 2 and matches the data-iscope the form prints for that copy.
- On SF1 with comparable 2's site size removed, where.comp == 2.
- plain is produced for the T-509 AMENITY fixture.
- not_counted is true exactly for the shown_in items.
Also run:
- test_compliance_*;
- validate_compliance_engine;
- test_usability;
- test_owner_checks;
- harness 12.
- Depends on: None; can start now. Needs keen-turing's agreement on the board. Wave 0: runs in parallel with S0a and S0b. E2 must follow it, because both edit review.py.

### S1 — Ribbon and command registry replace the tab row and the report toolbar (T-272)

- Tasks: 1) commands.js registers a command for every inventory control:
   - views: click the hidden #tabs buttons;
   - Deliver: click the #insp-sign elements;
   - adopted controls: by adopt:'#id';
   - the new Home groups: Save and Save & Next via flush; This section via #secsw-on / add-go / the #acks checkbox; Navigate; View;
   - Worksheets per kind via worksheets(kind);
   - Exhibits: Add exhibit from S.adds, Photos by section from S.media.
2) ribbon.js:
   - #ribbon inserted after <header>, built from one layout table (tab → group → command ids; unknown ids are skipped);
   - tabs Home · Report · Comparables · Sketch · Location Map · Exhibits · Worksheets · Review · Deliver.
3) On 'form-drawn', move the .rf-bar originals (same ids and handlers) into Home's groups. On 'case-open' and 'case-close', remove them.
4) Clones carry data-cmd / data-for and mirror disabled / checked / text through a MutationObserver on the single original. Popover commands pass the clicked button as the anchor.
5) The quick-access toolbar in the header.
6) Hide .work-head and the empty .rf-bar under body.shell.
7) Collapse to one row with Ctrl+F1 or a tab double-click. When collapsed, a tab click drops the ribbon as an overlay that closes after a command. The tab and the collapsed state persist.
8) when() honours kind-other. A disabled button says why in its title.
9) ARIA tablist / tab / toolbar with roving tabindex. Icons only below 1100 px; overflow menu at 820 px or less. Square corners and monochrome inline SVG (the owner's style).
10) The Legend popover holds the .rf-note text verbatim.
- Files: /home/user/UAD-3.6-DEVELOPMENT/engine/app/ui/shell/commands.js, /home/user/UAD-3.6-DEVELOPMENT/engine/app/ui/shell/ribbon.js, /home/user/UAD-3.6-DEVELOPMENT/engine/app/ui/shell/ribbon.css, /home/user/UAD-3.6-DEVELOPMENT/engine/tests/test_shell_ribbon.py (new)
- Tests: test_shell_ribbon.py:
- Every inventory id exists exactly once after opening case A, then case B, then the list, then A again.
- The originals sit inside #ribbon Home. page.click('#rf-sadj') opens #wsdock. page.uncheck('#rf-gaps') clears show-gaps in the frame.
- The brief's 'click every ribbon command' test:
  - every ribbon and quick-access button's data-cmd is registered and has run();
  - clicking each changes real state or opens its dialog;
  - destructive commands open their dialog, and the test cancels it.
- Report›Preview shows #pv. Deliver›Export ZIP before sign-off raises the existing dialog.
- Ctrl+F1 brings the ribbon under 48 px tall and survives a reload.
- At 1280x720, chrome is at most 160 px expanded and at most 90 px collapsed.
- The report frame starts higher than with ?shell=0.
- On a derived Completion Report, the map / market / fill clones and the Comparables / Location Map / Sketch tabs are hidden.
- The Comment library opened from a clone on another tab anchors to that clone.
Also run the 8 browser tests.
- Depends on: S0a; S0b for the Save / flush commands (tolerant until it is merged). Wave 1: runs in parallel with S2, S3, S4, S5, S6 and E2. Its own files only; no index.html, no flow.py.

### S2 — Dockable, collapsible, resizable side panels (T-273)

- Tasks: 1) On 'shell-built', insert div#dock-l as the first grid child and move nav#rail into it, with a filter box in the panel header.
2) aside#insp becomes the right dock: dock header, icon rail, accordion panel wrappers.
   - Move #insp-guide, #insp-sec and #insp-add into 'Field guidance', and #insp-sign into 'Sign-off'.
   - Re-wrap on 'insp'.
   - Host the panels registered through UADShell.panels; Problems arrives from S4.
3) Collapse to an icon rail with badges. The left one uses the 820 px number-only look plus status dots.
4) An unpinned shutter overlays the report edge and closes on a click in the report or on Esc (Esc stack). Pin docks it back.
5) Splitter with pointer capture; body.shell-drag iframe{pointer-events:none}; double-click resets; clamp 180 px..50vw.
6) Guidance badges and never takes over the open panel.
7) Persist {collapsed, pinned, w, open}. Viewport defaults from core.
8) Restate body.ws-open for body.shell (left dock / report / --ws-w; right dock hidden).
9) ownsNarrow() returns true. At 1240 px or less: rails and shutters, with Sign-off reachable from its icon. At 820 px or less: both docks overlay.
10) Send {uad:'side', mode:'compact'} to all frames under body.shell (replayed by core).
- Files: /home/user/UAD-3.6-DEVELOPMENT/engine/app/ui/shell/docks.js, /home/user/UAD-3.6-DEVELOPMENT/engine/app/ui/shell/docks.css, /home/user/UAD-3.6-DEVELOPMENT/engine/tests/test_shell_docks.py (new)
- Tests: test_shell_docks.py:
- Collapsing the left dock leaves it at most 48 px wide and widens #rf; the state survives a reload.
- Dragging the right splitter over the iframe gives 420±2 px, which persists; a double-click resets it.
- Unpinning the right dock lets #rf reach the edge. An icon click opens the shutter without changing #rf's width; a click in the report closes it.
- With the #rf-sadj drawer open, rf.right ≤ drawer.left; the dock returns when the drawer closes.
- #sign and #zip still work from the Sign-off panel.
- At a 1200 px viewport the Sign-off panel opens from its rail icon. With ?shell=0, the Sign-off tab still exists.
- At 1280x720 with both docks collapsed and the compact gutter, page zoom is 1.0. Record the measured value against the S0a baseline.
- #rf's contentWindow is unchanged throughout (no reload).
Also run test_worksheet_grid and the other browser tests.
- Depends on: S0a (S0b for side). Wave 1: runs in parallel with S1, S3, S4, S5, S6 and E2.

### S3 — Title bar chips, status bar, focus mode, zoom control (T-276, T-274)

- Tasks: 1) api.get_case: add summary {type_name, units, borrower, client, address}:
   - derived through bind in printed form;
   - type_name from templates.PROPERTY_TYPES;
   - memoised per document version.
2) chrome.js title bar:
   - type chip, highlighted;
   - borrower · client;
   - address;
   - status chip;
   - live count chips (#stat stays; clicking a chip opens Problems filtered);
   - patched at once from enriched 'saved' for 2.001, 2.012, 3.000 and the unit count.
3) #statusbar:
   - save state (pending / failed (a click locates the field) / 'Saved · Ns ago' ticker);
   - counts;
   - section;
   - focused field id;
   - view;
   - layout state;
   - active pane;
   - zoom − / Fit / + (sends {uad:'zoom'} to all frames, persisted, 50-100%);
   - XSD version;
   - case id (a click copies it) and updated.
4) Focus mode:
   - triggers: F11, Ctrl+Shift+F, Home›View, palette;
   - body.shell-focus, and side 'none' to the frames;
   - a 6 px hot-edge mini bar (Exit, counts, Prev / Next problem);
   - Esc as the last stack item;
   - not persisted;
   - Fullscreen API only when F11 started it, failures caught.
- Files: /home/user/UAD-3.6-DEVELOPMENT/engine/app/ui/shell/chrome.js, /home/user/UAD-3.6-DEVELOPMENT/engine/app/ui/shell/chrome.css, /home/user/UAD-3.6-DEVELOPMENT/engine/app/api.py (get_case only), /home/user/UAD-3.6-DEVELOPMENT/engine/tests/test_case_summary.py (new), /home/user/UAD-3.6-DEVELOPMENT/engine/tests/test_shell_chrome.py (new)
- Tests: test_case_summary.py:
- On all 12 samples, summary address / borrower / client equal what bind prints. Expected values are computed through bind, never hand-typed.
- type_name comes from PROPERTY_TYPES.
test_shell_chrome.py:
- A 2-4 unit case shows '2- to 4-unit' with its highlight class.
- A borrower name typed in the frame shows in the title bar without a reload.
- After an edit that changes the counts: title chips == #stat == status bar == Sign-off == S.review.counts.
- The status bar goes Saving… then Saved, and shows a forced failure.
- Scrolling the frame to section 12 shows its name in the status bar.
- Zoom 75% sets .page zoom to fit × 0.75 and persists.
- F11 hides the title bar, ribbon and docks; #rf width ≥ viewport − 4; the mini bar appears at the top edge.
- With the worksheet open, the first Esc closes it and the second exits focus.
Also run the 8 browser tests.
- Depends on: S0a and S0b. Wave 1: runs in parallel with S1, S2, S4, S5, S6 and E2. api.py: get_case only; S5 adds a separate route.

### S4 — Problems side panel with live filters, click-to-field and F8 (T-505)

- Tasks: Build problems.js as described in problems_panel:
- registration, and Expand to at most 50% for 'All problems'. The Review Master view command opens it in shell mode; drawReview stays for ?shell=0 and widths of 820 px or less.
- severity / source / this-section filters, search, group by Section / Severity / Rule, and the collapsed 'Not counted' group;
- plain message, using item.plain when present;
- keyed live diff on 'review', 'Checking…' / 'as of', and Re-run;
- locate(item) through frames.active() goto v2 with where when present, a pending queue while loading or swapping, and the honest result;
- the locate / located reachability map and canLocate();
- commands problems.toggle / expand / next (F8) / prev (Shift+F8), with the panel closed or open;
- keys inside the panel;
- a 'Problem markers' toggle bound to #rf-marks;
- rows offer only Go to field / Go to section and the existing T-510 fix button for now; S7 adds the full action set.
- Files: /home/user/UAD-3.6-DEVELOPMENT/engine/app/ui/shell/problems.js, /home/user/UAD-3.6-DEVELOPMENT/engine/app/ui/shell/problems.css, /home/user/UAD-3.6-DEVELOPMENT/engine/tests/test_problems_panel.py (new)
- Tests: test_problems_panel.py, on a blank 2-4 case and an SF1 copy:
- The panel is beside #rf, never over it (rf.right ≤ panel.left), and Expand keeps it beside the report.
- Per-section counts equal the rail badges; totals equal #stat.
- The Warning filter shows only warnings; searching a known code gives exactly its rows; the Not-counted group holds exactly the not_counted items.
- Clicking a row:
  - the frame's activeElement has that data-fid and is inside the viewport;
  - the rail's aria-current equals its section;
  - Field guidance shows the field;
  - all within 300 ms of the frame being ready.
- Typing the missing value removes the row within 10 s, and every count drops in step.
- F8 then Shift+F8 walk in list order with the panel collapsed.
- A finding on a field not in the layout shows no 'Go to field'.
- A click made during a swap lands after the swap.
Also run the 8 browser tests.
- Depends on: S0a and S0b; uses E1's where and plain when merged and degrades without them. Wave 1: runs in parallel with S1, S2, S3, S5, S6 and E2. Works without S2 (top of #insp).

### S5 — Keyboard bindings, command palette, fields directory (T-277)

- Tasks: 1) palette.js:
   - a combobox overlay with scopes All / '>' commands / '#' sections / '@' fields / '!' problems / '+' add;
   - subsequence scoring, at most 50 rows, most recently used first;
   - Up / Down / Enter / Esc, then refocus.
2) api.py: GET /api/fields/directory {fid:[label, section, subsection]}, projected from spec/field_index.json locations[0], lru_cached, with cache headers. Fields absent from the locate map are marked 'not in this report'.
3) Bind:
   - Ctrl+K and Ctrl+G;
   - Ctrl+S / Ctrl+Shift+S (flush; status bar result);
   - Ctrl+Tab / Ctrl+Shift+Tab, with Alt+PageDown / PageUp;
   - F6 / Shift+F6 region cycle;
   - Ctrl+. (fix at cursor; uses S7's applier when present, the T-510 button path until then);
   - Ctrl+/ cheat sheet.
   Ctrl+\ is registered by S8.
4) The collision guard test against the never-bound list.
- Files: /home/user/UAD-3.6-DEVELOPMENT/engine/app/ui/shell/palette.js, /home/user/UAD-3.6-DEVELOPMENT/engine/app/ui/shell/palette.css, /home/user/UAD-3.6-DEVELOPMENT/engine/app/api.py (new fields/directory route only), /home/user/UAD-3.6-DEVELOPMENT/engine/tests/test_shell_keys.py (new), /home/user/UAD-3.6-DEVELOPMENT/engine/tests/test_fields_directory.py (new)
- Tests: test_shell_keys.py, each combo from the parent and with the caret in a report contenteditable:
- Ctrl+K opens the palette and lists all four kinds of entry; 'outbuild' then Enter puts the rail's aria-current on its section and scrolls the frame.
- Ctrl+G 'Physical Address' focuses [data-fid="3.000"].
- Esc closes the palette and focus returns to the field.
- Ctrl+S on an edited field sends the PATCH, the status bar says Saved, and there is no download event.
- Ctrl+Tab moves to the next printed section.
- Ctrl+J still opens the worksheet, Alt+1 still inserts a snippet, and Esc still reverts a field.
- The collision guard passes.
- Palette filtering stays under 10 ms for 1,500 entries.
test_fields_directory.py: every field id in field_index.json is present, with its label.
- Depends on: S0a and S0b. Wave 1: develop in parallel with S1-S4, S6 and E2. Run its final key tests after S1 merges, because the palette lists S1's commands. api.py: its own new route only.

### S6 — Inline problem markers on by default, with their explanation card (T-507)

- Tasks: markers.js:
- In shell mode, when localStorage uad-marks is unset, set S.showMarks=true before start(). A stored choice wins.
- postMarks object items with gc / scope, via S0b. Frames get marks through frames.send to:'all'.
- On 'mark-at', draw the parent-side card at the frame's rect plus the field's rect: severity, every S.review item on that fid / gc, H-1 id, plain message, rule logic.
- Buttons: 'Fix: <label>' (applyFixButton) when item.fix exists, 'Rule & guidance' (focus the field), 'Show in list' (when S4 is present), 'Next ▸ F8'.
- Close on mark-off, scroll or Esc (stack).
- Nothing changes in EDIT_CSS / form.py.
- test_checkbox_centre: one line, unchecking #rf-marks at the start of its 'boxes alone, no problem shown' phase, as it already does with #rf-gaps. Same intent, state made explicit.
- Files: /home/user/UAD-3.6-DEVELOPMENT/engine/app/ui/shell/markers.js, /home/user/UAD-3.6-DEVELOPMENT/engine/app/ui/shell/markers.css, /home/user/UAD-3.6-DEVELOPMENT/engine/tests/test_problem_markers.py (new), /home/user/UAD-3.6-DEVELOPMENT/engine/tests/test_checkbox_centre.py (one explicit uncheck)
- Tests: test_problem_markers.py:
- Setup: an SF1 copy, As Is, plus a repair defect (the T-510 U10.1 setup).
- With a fresh profile, markers are on. Hovering the outlined field shows a card with 'U10.1', the message and 'Make it “Subject to Repair”'.
- Clicking it sends the PATCH; U10.1 leaves S.review, the outline goes and the card closes.
- On a blank report, a Fatal UAD#### shows its id and plain message.
- A comparable finding with gc outlines only that column.
- With marks toggled off there is no card, and the choice survives a reload.
- test_checkbox_centre passes on all its samples.
This is also the first committed browser test of the T-510 usability fix, which the HANDOFF mentioned but engine/tests lacked.
- Depends on: S0a and S0b. Wave 1: runs in parallel with S1-S5 and E2.

### E2 — Fix suggestions in the engine (T-508, engine half)

- Tasks: 1) engine/uad/fixes.py: suggest(tree, finding) -> {field_id, value, label, route?, scope?, ordinal?, key?, kind:'write', confirm?} | None, for these classes only:
   - an enumeration value matching exactly one A-1 value ignoring case and spacing;
   - a single near-miss within edit distance 2 (confirm:true);
   - a malformed stored date or number that parses unambiguously into A-1's format (parser shared with T-278);
   - values computed only by existing authorities (rent_math, grid_math).
   No new arithmetic, and nothing a person must judge.
2) A one-line hook in review._compliance_items: fix=fixes.suggest(tree, f), using E1's instance for route and scope.
3) engine/uad/gates.py: a read-only gate_for(tree, fid) naming the answered question that hides a field, built on form.edit_hides. No form.py edit.
4) /guide passes the new fixes through.
5) A CATALOG entry and a knowledge note.
6) kind:'repair' for XSD stays unimplemented. It is reserved for epic-brahmagupta's T-1201 route; tell them the fix shape on the board.
- Files: /home/user/UAD-3.6-DEVELOPMENT/engine/uad/fixes.py (new), /home/user/UAD-3.6-DEVELOPMENT/engine/uad/gates.py (new), /home/user/UAD-3.6-DEVELOPMENT/engine/uad/review.py (one line), /home/user/UAD-3.6-DEVELOPMENT/engine/app/api.py (guide passthrough only), /home/user/UAD-3.6-DEVELOPMENT/engine/tests/test_fixes.py (new), /home/user/UAD-3.6-DEVELOPMENT/knowledge/errors/CATALOG.md
- Tests: test_fixes.py:
- On all 12 D-1 samples: zero suggestions, and findings unchanged.
- For each class, a mutated sample copy raises the finding with a fix. Writing it through the real PATCH route clears it, adds no new finding and stays XSD-valid.
- A near-miss carries confirm:true; an ambiguous case (two candidates) gets no fix.
- gate_for names the gate on a known gated field (from tests/test_every_choice_saves.py KNOWN entries) and returns None on an ungated one.
Also run:
- test_usability;
- test_owner_checks;
- test_applicable_findings;
- test_field_guide;
- harness 12.
- Depends on: E1, because both edit review.py. Needs keen-turing's agreement on the board. Runs in parallel with every Wave 1 UI step.

### S7 — An honest 'Fix this' everywhere, landing on the exact unit or comparable (T-508, UI half)

- Tasks: 1) index.html applyFixButton:
   - honour fx.route (PATCH that route with value plus scope / ordinal / key) and fx.confirm (UADDialog.confirm first);
   - expose it as UADShell.fix.apply for the panel, the card, Guidance, the palette and Ctrl+.
2) findingRow (Review Master), problems.js rows and the markers.js card use one action builder, taking the first that applies:
   - 'Fix: <label>';
   - 'Go to field' (located = field);
   - 'Go to section';
   - 'Show section' (optional section off: #secsw-on then go);
   - 'Go to <gate question>' (E2 gates);
   - 'Open in Additional Data';
   otherwise the plain reason (Does Not Display / not counted (B-1) / XSD software defect, T-1201).
3) Retire the navigate-only 'Fix this' label.
4) Pass E1's where into locate (scope / comp / unit) everywhere.
- Files: /home/user/UAD-3.6-DEVELOPMENT/engine/app/ui/index.html (applyFixButton and findingRow only), /home/user/UAD-3.6-DEVELOPMENT/engine/app/ui/shell/problems.js (row actions), /home/user/UAD-3.6-DEVELOPMENT/engine/app/ui/shell/markers.js (card actions), /home/user/UAD-3.6-DEVELOPMENT/engine/tests/test_fix_this.py (new)
- Tests: test_fix_this.py, on blank SF and blank 2-4 reports plus E2's mutated copies. 'Never a no-op':
- For every Fatal and Warning row in the panel and the Review Master, the primary action either changes the document (200, then the row clears) or moves focus to a visible element in the frame (goto found, gate focused, or section switched on). Zero no-ops.
- A confirm fix shows the dialog, and Cancel writes nothing.
- A route fix on a grid cell writes that comparable's value.
- On the mutated copies, clicking the unit-2 row focuses unit 2's copy, and the comparable-2 row focuses the data-gc=2 cell.
Also run:
- test_usability's fix assertions;
- test_problem_markers;
- test_problems_panel;
- ?shell=0 Review Master.
- Depends on: S4, S6 and E2 (and E1). Wave 2. It edits problems.js and markers.js, so it starts only after S4 and S6 are merged. Runs in parallel with S8, because it touches no flow.py and S8 touches no index.html.

### S8 — Split view: the same report in two live, editable panes (T-275; stage 2 window T-1208)

- Tasks: 1) split.js:
   - modes off / side / stacked;
   - Ctrl+\ and Home›View›Split ▾; stacked from the ribbon and palette.
2) .reportform becomes a CSS grid with areas. #rf2 (?pane=2) and the gutter are appended; #rf and #rf-body are never moved. Ratio splitter (iframes pointer-events:none while dragging). The ratio and pane 2's section are remembered.
3) Pane 2's header: a section picker (goto), close, swap, orientation.
4) flow.py /* shell:sync */ block:
   - BroadcastChannel('uad-case-'+id) publishing each successful write {seq, src, fid | tf+tk | gf+gc, iscope, ordinal, shown};
   - on receive, patch unless focused or .saving; update [data-derived];
   - ignore its own src token.
5) Parent:
   - payload-less 'saved', relayout, reshaped, structure and media → checkFresh('form') for pane 1, and split.js's own swap for pane 2 (busy rules from swapFrame, scroll copied);
   - 'fresh' from #rf2 swaps pane 2;
   - frames.replay for pane 2;
   - forward pane 2's worksheet and ws-esc;
   - pane 2 inert during the fill run;
   - goto / F8 / insert / add-go to the active pane.
6) Stage 2 (T-1208), as its own sub-step: a detached window ?pane=solo on the same channel.
- Files: /home/user/UAD-3.6-DEVELOPMENT/engine/app/ui/shell/split.js, /home/user/UAD-3.6-DEVELOPMENT/engine/app/ui/shell/split.css, /home/user/UAD-3.6-DEVELOPMENT/engine/uad/report/flow.py (the /* shell:sync */ block only), /home/user/UAD-3.6-DEVELOPMENT/engine/tests/test_split_view.py (new)
- Tests: test_split_view.py:
- Side mode: #rf2 and #rf are both visible and do not overlap. Stacked geometry is checked.
- A value typed in pane 2 shows in pane 1 within 1 s, with pane 1's contentWindow unchanged (no reload). Exactly one PATCH per edit (no echo loop).
- Adding a comparable in pane 1 brings pane 2 to the server's render key.
- A worksheet opened from pane 2 docks the drawer.
- F8 and goto act on the last-focused pane.
- Theme and marks reach both panes.
- Closing the split removes #rf2, and #rf keeps the same contentWindow.
- Pane 2 opens in under 1 s on SF1 from the kept layout. Measured and recorded.
- The Esc and Ctrl+J flows still work.
Stage 2: an edit in the detached window reaches the main window.
Also run the 8 browser tests.
- Depends on: S0a, S0b, and S2 merged (both shape the report area's geometry). S1 is optional (ribbon button). Wave 2: runs in parallel with S5 and S7. It is the only later step that edits flow.py, and only inside its own anchored block.

### S9 — Integration, measurement, records, deploy

- Tasks: 1) Merge in this order:
   - S0a + S0b + E1;
   - then S1-S6 and E2;
   - then S7 and S8.
   Run the full suite, harness 12, every test_shell_* / test_problem* / test_fix* / test_split* / test_frame_protocol / test_case_summary / test_fields_directory test, and a ?shell=0 smoke run.
2) Screenshots in light and dark at 1600x1000, 1280x720 and 1920x1080, before and after, into _work/ui/dr/shell-*.png.
3) Measure against T-1064 and record in HANDOFF:
   - the shell adds less than 50 ms to case open;
   - panel toggle under 16 ms;
   - F8 jump under 150 ms;
   - palette open under 50 ms;
   - split pane open under 1 s;
   - page zoom at 1280x720, before and after.
4) Check by hand in the Edge --app window and in Chrome: F11, Ctrl+Tab, F6, Ctrl+S, Ctrl+G, Ctrl+K, Ctrl+F1, Ctrl+., F8. Record each as verified or 'unverified (reason)'.
5) Close with evidence, each as soon as its slice lands: T-272 after S1, T-273 after S2, T-274 and T-276 after S3, T-277 after S5, T-505 after S4, T-507 after S6, T-508 after S7, T-275 after S8, T-1205..T-1208.
6) Register T-1209: retire the classic layout after the owner's acceptance.
7) CATALOG entries for the traps, from E-189, then a newly claimed E-190..E-199 block. A knowledge note with the shell architecture and the postMessage / BroadcastChannel protocol table.
8) Update HANDOFF, AI_HANDOVER §4/§5 and the DESKTOP_REBUILD_PLAN status table.
9) Deploy production at a quiet time. flow.py changed, so every kept report re-lays once on its next open.
- Files: /home/user/UAD-3.6-DEVELOPMENT/TASKS.md, /home/user/UAD-3.6-DEVELOPMENT/_work/HANDOFF.md, /home/user/UAD-3.6-DEVELOPMENT/AI_HANDOVER.md, /home/user/UAD-3.6-DEVELOPMENT/_work/DESKTOP_REBUILD_PLAN.md, /home/user/UAD-3.6-DEVELOPMENT/_work/agents/claude-sleepy-hypatia-e2pzcn.json, /home/user/UAD-3.6-DEVELOPMENT/knowledge/errors/CATALOG.md, /home/user/UAD-3.6-DEVELOPMENT/knowledge/ (shell and protocol note), /home/user/UAD-3.6-DEVELOPMENT/_work/ui/dr/
- Tests: - Full suite: 0 failed.
- harness 12: 88/0/20 or better.
- Every shell test passes, with playwright==1.56.0 and Chromium 1194.
- ?shell=0 smoke: the classic editor opens, edits, signs and exports.
- The manual key checklist is recorded, including what could not be verified (Tauri/WebView2 not available here).
- Depends on: All of the above. Closes in slices as each step lands.
