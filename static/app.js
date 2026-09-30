"use strict";
const $ = (id) => document.getElementById(id);
const state = {principal: "demo-investigator-a", cutoff: "2026-09-30T10:00:00+09:00",
  capture: "", packet: null, sequence: 0, sourceSequence: 0, historySequence: 0,
  reviewPending: false, focusReturn: null};
const typeNames = {inspection_record: "검사 원문", inspection_correction: "검사 정정",
  containment_record: "보류 기록", material_issue_record: "자재 발행",
  action_tracker: "조치 추적", briefing_record: "브리핑",
  investigation_conclusion: "후속 결론"};
function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
}
function clear(node) { node.replaceChildren(); }
function notice(text, error) { $("notice").textContent = text; $("notice").classList.toggle("error", !!error); }
function params(extra) {
  const q = new URLSearchParams({investigator: state.principal, cutoff: state.cutoff});
  if (state.capture) q.set("capture_id", state.capture);
  if (extra) Object.entries(extra).forEach(([key, value]) => q.set(key, value));
  return q;
}
async function getJson(path) {
  const response = await fetch(path, {cache: "no-store"});
  const value = await response.json();
  if (!response.ok) throw new Error(value.error || "read_failed");
  return value;
}
function sourceButton(id, label) {
  const button = el("button", "source-button", label || "원문 열기");
  button.type = "button";
  button.addEventListener("click", () => openSource(id, button));
  return button;
}
async function openSource(id, sourceControl) {
  const turn = ++state.sourceSequence;
  const scope = state.sequence;
  state.focusReturn = sourceControl;
  $("source-title").textContent = "원문 기록 · " + id;
  $("source-meta").textContent = "";
  $("source-error").textContent = "";
  $("source-text").textContent = "원문을 확인하고 있습니다.";
  $("source-dialog").showModal();
  try {
    const row = await getJson("/api/source/" + encodeURIComponent(id) + "?" + params());
    if (turn !== state.sourceSequence || scope !== state.sequence || !$("source-dialog").open) return;
    $("source-meta").textContent = row.case_id + " · " + row.record_type + " · revision " +
      row.revision + " · " + row.source_state + " · 기록상 사건 시각 " + row.event_at +
      " · 자료 가용 시각 " + row.recorded_at + " · 원문 SHA-256 " + row.content_sha256;
    $("source-text").textContent = row.text;
  } catch (error) {
    if (turn !== state.sourceSequence || scope !== state.sequence || !$("source-dialog").open) return;
    $("source-error").textContent = "이 범위에서는 원문을 열 수 없습니다: " + error.message;
    $("source-text").textContent = "";
  }
}
function closeSource() {
  ++state.sourceSequence;
  $("source-dialog").close();
  const control = state.focusReturn;
  state.focusReturn = null;
  if (control && control.isConnected) control.focus();
}
$("close-source").addEventListener("click", closeSource);
$("source-dialog").addEventListener("cancel", () => {
  ++state.sourceSequence;
  const control = state.focusReturn;
  state.focusReturn = null;
  if (control && control.isConnected) setTimeout(() => control.focus(), 0);
});
function renderSummary(packet) {
  if (packet.state === "scope_empty") {
    $("sample-metric").textContent = "접근 가능한 현재 사건 없음";
    $("sample-note").textContent = "";
    $("cause-metric").textContent = "미표시";
    $("cause-note").textContent = "";
    $("handoff-metric").textContent = "범위 없음";
    $("handoff-note").textContent = "숨겨진 원문 수는 제공하지 않습니다.";
    return;
  }
  const sample = packet.typed.sample;
  $("sample-metric").textContent = sample.rate_percent === null ?
    "비율 미확정" : sample.incorrect_units + "/" + sample.inspected_units + " · " + sample.rate_percent + "%";
  $("sample-note").textContent = sample.state === "unknown_due_to_conflict" ?
    "같은 revision 상충 · 원본 조정 필요" :
    sample.state === "inspected_denominator_missing" ? "검사 분모 누락 · 로트 총수량 대체 금지" :
    "검사 표본 비율이며 로트 전체 비율이 아닙니다.";
  $("cause-metric").textContent = packet.typed.current_cause.status === "reported_conclusion_available" ?
    "후속 결론 보고 있음" : "기준 시각에 미확정";
  $("cause-note").textContent = "앱의 독립 검증은 수행하지 않았습니다.";
  $("handoff-metric").textContent = packet.state === "blocked_source_conflict" ?
    (state.principal === "demo-reviewer-a" ?
      "상충 원문 · 수락 보류, 보완 반환 가능" : "상충 원문 · 검토자 확인 필요") :
    (state.principal === "demo-reviewer-a" ?
      "열린 질문과 함께 검토 가능" : "열린 질문 포함 · 검토자 대기");
  $("handoff-note").textContent = "CAPA/로트/원본 상태는 변경되지 않습니다.";
}
function renderTimeline(packet) {
  const list = $("timeline");
  clear(list);
  $("timeline-count").textContent = packet.timeline.length + "개 현재 원문";
  for (const row of packet.timeline) {
    const item = el("li");
    const card = el("article", "card");
    const head = el("div", "card-title");
    head.append(el("span", "", typeNames[row.record_type] || row.record_type),
      el("span", "pill", row.source_id));
    card.append(head, el("p", "times", "기록상 사건 시각 " + row.event_at + " · 자료 가용 시각 " + row.recorded_at));
    card.append(el("p", "", row.text.length > 165 ? row.text.slice(0, 165) + "…" : row.text));
    card.append(sourceButton(row.source_id));
    item.append(card);
    list.append(item);
  }
  const old = $("correction-list");
  clear(old);
  for (const row of packet.corrections) {
    const card = el("article", "card");
    card.append(el("strong", "", "이전 revision " + row.revision + " · " + row.source_id),
      el("p", "meta", "자료 가용 시각 " + row.recorded_at + " · 현재 사실에서 제외"),
      el("p", "", row.text), sourceButton(row.source_id, "이전 원문 열기"));
    old.append(card);
  }
  $("corrections").hidden = packet.corrections.length === 0;
  const conflict = $("conflict-box");
  clear(conflict);
  const conflictRows = packet.conflicted_sources ||
    (packet.conflicted_source_ids || []).map(source_id => ({
      source_id, revision: "원문에서 확인", recorded_at: "원문에서 확인",
    }));
  conflict.hidden = conflictRows.length === 0;
  if (conflictRows.length) {
    conflict.append(el("strong", "", "상충 원문 · 현재 사실에서 격리"));
    conflict.append(el("p", "", "같은 revision의 원문이 달라 인계 수락은 차단됩니다. 각 기록을 열어 검토할 수 있습니다."));
    for (const row of conflictRows) {
      const card = el("div", "conflict-source");
      card.append(el("span", "", row.source_id + " · revision " + row.revision +
        " · 자료 가용 시각 " + row.recorded_at + " · 격리"),
        sourceButton(row.source_id, row.source_id + " 원문 열기"));
      conflict.append(card);
    }
  }
}
function renderComparisons(packet) {
  const box = $("comparisons");
  clear(box);
  $("comparison-count").textContent = packet.comparisons.length + "개 선례";
  for (const item of packet.comparisons) {
    const card = el("article", "compare-card");
    card.append(el("strong", "", item.case_id + " · 과거 사건에만 귀속"));
    const same = "공통: " + (item.same_products.concat(item.same_lines).join(", ") || "표시된 식별자 없음");
    const diff = packet.state === "blocked_source_conflict" &&
      item.unknown_products === undefined ? "확인된 차이: 판정 보류" :
      "확인된 차이: " +
      (item.different_products.concat(item.different_lines).join(", ") || "표시된 차이 없음");
    const unknown = (item.unknown_products || []).concat(item.unknown_lines || []);
    card.append(el("p", "diff", same), el("p", "diff", diff));
    if (unknown.length) card.append(el("p", "diff",
      "현재 사건의 식별자 미확인 · 과거 원문에는 " + unknown.join(", ") + " 표기"));
    card.append(el("p", "hint", "이 사례의 원인·조치는 현재 사건의 확정 사실이 아닙니다."));
    for (const source of item.historical_sources) card.append(sourceButton(source.source_id, source.source_id + " 원문"));
    box.append(card);
  }
  const facts = $("status-facts");
  clear(facts);
  const typed = packet.typed;
  const rows = [
    ["격리", typed.containment.recorded_status === "HOLD" ? "HOLD 기록 · 실물 전수 확인은 미확인" : "기록 미확인"],
    ["라벨 자재", typed.material.issued_id ? typed.material.issued_id + " 발행 · 실제 장착은 미확인" : "발행 기록 미확인"],
    ["조치", typed.action.implementation === "recorded" ? "실행 기록 · 효과성 결과 별개" : "실행 기록 미확인"],
    ["브리핑", typed.briefing.occurrence === "recorded" ? "브리핑 기록 · 개인 참석은 미확인" : "기록 미확인"],
  ];
  for (const [term, value] of rows) facts.append(el("dt", "", term), el("dd", "", value));
}
function renderRequests(packet) {
  const list = $("requests");
  clear(list);
  $("request-count").textContent = packet.requests.length + "개 열림";
  for (const request of packet.requests) {
    const item = el("li", "request-card");
    item.append(el("strong", "", request.request_id + " · 열린 질문"),
      el("p", "", request.question),
      el("p", "meta", "근거: " + request.source.source_id + " · " + request.source.quote));
    item.append(sourceButton(request.source.source_id, "요청 근거 원문"));
    list.append(item);
  }
}
const reviewActors = new Set(["demo-reviewer-a"]);
function updateReviewAction() {
  const packet = state.packet;
  const conflict = packet && packet.state === "blocked_source_conflict";
  const accepted = $("decision").querySelector('[value="accepted_for_handoff"]');
  accepted.disabled = !!conflict;
  if (conflict && $("decision").value === "accepted_for_handoff") $("decision").value = "returned";
  const eligible = packet && reviewActors.has(state.principal) &&
    (packet.state === "reviewer_ready_with_open_questions" ||
      (conflict && $("decision").value === "returned"));
  $("review-button").disabled = !eligible || state.reviewPending;
}
function sameReviewContext(receipt) {
  return !!state.packet && receipt.cutoff === state.cutoff &&
    (receipt.capture_id || "") === state.capture &&
    receipt.packet_fingerprint === state.packet.packet_fingerprint;
}
function renderHistory(receipts) {
  const list = $("review-history");
  clear(list);
  if (!receipts.length) {
    $("history-status").textContent = "이 범위의 검토 기록이 없습니다.";
    return;
  }
  $("history-status").textContent = receipts.length + "개 검토 기록 · 원문과 조회 맥락을 확인하세요.";
  for (const receipt of receipts.slice().reverse()) {
    const item = el("li");
    const same = sameReviewContext(receipt);
    const label = !receipt.fresh ? "원문 변경 · stale" :
      !same ? "다른 조회 맥락" :
      receipt.decision === "accepted_for_handoff" ? "인계 검토 수락 기록" : "보완 반환 기록";
    item.append(el("strong", "", label + " · " + receipt.receipt_id.slice(0, 10)));
    item.append(el("span", "history-meta", "자료 가용 기준 " + receipt.cutoff +
      " · " + (receipt.capture_id || "기본 원문") + " · 기록 시각 " + receipt.at));
    if (receipt.reviewer_note) item.append(el("span", "history-meta", "메모: " + receipt.reviewer_note));
    const button = el("button", "export-button", "검토 패킷 JSON 내려받기");
    button.type = "button";
    button.disabled = !receipt.fresh || !same || receipt.decision !== "accepted_for_handoff";
    button.addEventListener("click", () => exportReceipt(receipt, button));
    item.append(button);
    list.append(item);
  }
}
async function loadHistory(turn = state.sequence) {
  const historyTurn = ++state.historySequence;
  clear($("review-history"));
  if (!reviewActors.has(state.principal) || !state.packet || state.packet.state === "scope_empty") {
    $("history-status").textContent = "현재 조회 범위에는 표시할 검토 기록이 없습니다.";
    return;
  }
  $("history-status").textContent = "검토 이력을 확인하고 있습니다.";
  const investigator = state.principal;
  const q = new URLSearchParams({investigator, reviewer: state.principal});
  try {
    const result = await getJson("/api/reviews?" + q);
    if (turn !== state.sequence || historyTurn !== state.historySequence) return;
    renderHistory(result.reviews);
  } catch (error) {
    if (turn !== state.sequence || historyTurn !== state.historySequence) return;
    $("history-status").textContent = "검토 이력을 확인할 수 없습니다: " + error.message;
  }
}
async function exportReceipt(receipt, button) {
  const turn = state.sequence;
  if (button.disabled || !sameReviewContext(receipt)) return;
  button.disabled = true;
  $("history-status").textContent = "내보내기 전 서버에서 현재 원문과 권한을 다시 확인합니다.";
  const q = new URLSearchParams({investigator: state.principal, reviewer: state.principal});
  try {
    const result = await getJson("/api/export/" + encodeURIComponent(receipt.receipt_id) + "?" + q);
    if (turn !== state.sequence || !sameReviewContext(receipt)) return;
    const blob = new Blob([JSON.stringify(result, null, 2)], {type: "application/json"});
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "fictional-handoff-" + receipt.receipt_id.slice(0, 10) + ".json";
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    $("history-status").textContent = "검토 패킷을 내려받았습니다. 운영 원본은 변경되지 않았습니다.";
  } catch (error) {
    if (turn === state.sequence) $("history-status").textContent =
      "내보내기를 완료하지 못했습니다: " + error.message + ". 이력을 다시 확인하세요.";
  } finally {
    if (turn === state.sequence) button.disabled = !receipt.fresh ||
      !sameReviewContext(receipt) || receipt.decision !== "accepted_for_handoff";
  }
}
$("refresh-history").addEventListener("click", () => loadHistory());
$("decision").addEventListener("change", updateReviewAction);
function render(packet) {
  state.packet = packet;
  $("scope-readout").textContent = "자료 가용 기준 " + state.cutoff + " · 범위 " + state.principal +
    (state.capture ? " · 추가 캡처 " + state.capture : " · 기본 원문");
  renderSummary(packet);
  if (packet.state === "scope_empty") {
    for (const id of ["timeline", "correction-list", "comparisons", "status-facts", "requests"]) clear($(id));
    $("timeline-count").textContent = "0개"; $("comparison-count").textContent = "0개";
    $("request-count").textContent = "0개"; $("corrections").hidden = true;
    $("conflict-box").hidden = true;
  } else {
    renderTimeline(packet); renderComparisons(packet); renderRequests(packet);
  }
  updateReviewAction();
  $("review-result").textContent = "";
}
function clearScopeView() {
  state.packet = null;
  $("scope-readout").textContent = "자료 가용 기준 " + state.cutoff + " · 범위 " + state.principal +
    (state.capture ? " · 추가 캡처 " + state.capture : " · 기본 원문");
  $("sample-metric").textContent = "자료 조회 중";
  $("sample-note").textContent = "";
  $("cause-metric").textContent = "—";
  $("cause-note").textContent = "";
  $("handoff-metric").textContent = "—";
  $("handoff-note").textContent = "";
  for (const id of ["timeline", "correction-list", "comparisons", "status-facts", "requests"]) clear($(id));
  $("timeline-count").textContent = "0개";
  $("comparison-count").textContent = "0개";
  $("request-count").textContent = "0개";
  $("corrections").hidden = true;
  $("conflict-box").hidden = true;
  $("review-result").textContent = "";
  $("review-button").disabled = true;
  ++state.historySequence;
  clear($("review-history"));
  $("history-status").textContent = "조회 범위를 확인하고 있습니다.";
}
function persistScope() {
  try {
    sessionStorage.setItem("fictional-quality-scope", JSON.stringify({
      principal: state.principal, cutoff: state.cutoff, capture: state.capture,
    }));
  } catch { /* Storage is optional; server still checks every request. */ }
}
function restoreScope() {
  try {
    const saved = JSON.parse(sessionStorage.getItem("fictional-quality-scope") || "{}");
    for (const id of ["principal", "cutoff"]) {
      const value = saved[id];
      if (typeof value === "string" && [...$(id).options].some(option => option.value === value)) {
        $(id).value = value;
        state[id] = value;
      }
    }
    if (typeof saved.capture === "string" && saved.capture.length <= 100) state.capture = saved.capture;
  } catch { /* Invalid saved UI state is ignored. */ }
}
async function load() {
  const turn = ++state.sequence;
  ++state.sourceSequence;
  if ($("source-dialog").open) $("source-dialog").close();
  state.focusReturn = null;
  clearScopeView();
  notice("허용된 원문과 기준 시각을 확인하고 있습니다.");
  const q = new URLSearchParams({investigator: state.principal, cutoff: state.cutoff});
  try {
    const scenarios = await getJson("/api/scenarios?" + q);
    if (turn !== state.sequence) return;
    const captureSelect = $("capture");
    const saved = state.capture;
    clear(captureSelect);
    captureSelect.append(new Option("기본 원문만", ""));
    for (const row of scenarios.captures) {
      captureSelect.append(new Option(row.capture_id + " · " +
        (typeNames[row.record_type] || row.record_type), row.capture_id));
    }
    state.capture = [...captureSelect.options].some(option => option.value === saved) ? saved : "";
    captureSelect.value = state.capture;
    persistScope();
    const packet = await getJson("/api/view?" + params());
    if (turn !== state.sequence) return;
    render(packet);
    void loadHistory(turn);
    notice(packet.state === "scope_empty" ? "현재 사건에 접근 가능한 원문이 없습니다." :
      packet.state === "blocked_source_conflict" ? "상충 원문 때문에 검토 인계 수락이 차단됐습니다." :
      "허용된 원문으로 시간선과 열린 근거 요청을 구성했습니다.");
  } catch (error) {
    if (turn !== state.sequence) return;
    $("sample-metric").textContent = "조회 실패";
    $("history-status").textContent = "조회 실패 · 이전 검토 이력을 표시하지 않습니다.";
    notice("원문 범위를 불러올 수 없습니다: " + error.message, true);
    $("review-button").disabled = true;
  }
}
for (const id of ["principal", "cutoff", "capture"]) {
  $(id).addEventListener("change", () => {
    state.principal = $("principal").value;
    state.cutoff = $("cutoff").value;
    state.capture = $("capture").value;
    persistScope();
    load();
  });
}
$("review-button").addEventListener("click", async () => {
  const packet = state.packet;
  if (!packet || $("review-button").disabled) return;
  const turn = state.sequence;
  const payload = {
    investigator: state.principal, reviewer: state.principal,
    cutoff: state.cutoff, capture_id: state.capture || null,
    packet_fingerprint: packet.packet_fingerprint,
    decision: $("decision").value, reviewer_note: $("review-note").value,
  };
  const reviewButton = $("review-button");
  const keyboardFocus = document.activeElement === reviewButton;
  state.reviewPending = true;
  updateReviewAction();
  $("review-result").textContent = "서버에서 현재 원문과 인계 내용을 다시 확인 중입니다.";
  try {
    const response = await fetch("/api/review", {method: "POST",
      headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload)});
    const result = await response.json();
    if (turn !== state.sequence) return;
    if (!response.ok) throw new Error(result.error || "review_failed");
    $("review-result").textContent = (result.decision === "accepted_for_handoff" ?
      "인계 검토 수락 · 미해결 질문 " + packet.requests.length + "건 포함" : "보완 반환 기록됨") +
      " · " + result.receipt_id.slice(0, 10) + " · 운영 원본은 변경되지 않았습니다.";
    void loadHistory(turn);
  } catch (error) {
    if (turn !== state.sequence) return;
    $("review-result").textContent = "기록 결과를 확인할 수 없습니다: " + error.message +
      ". 재시도 전 아래 검토 이력을 다시 확인하세요.";
    void loadHistory(turn);
  } finally {
    state.reviewPending = false;
    updateReviewAction();
    if (turn === state.sequence && keyboardFocus && !reviewButton.disabled &&
        document.activeElement === document.body) reviewButton.focus();
  }
});
restoreScope();
load();
