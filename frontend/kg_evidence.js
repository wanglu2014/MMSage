   
                                                                                                
   
(function (global) {
  const HOP_LABELS = {
    microbe_metabolite: "Microbe–Metabolite",
    metabolite_disease: "Metabolite–Disease",
    microbe_disease: "Microbe–Disease",
  };

  let _boundCy = null;
  let _getContext = () => ({});

  function escapeHtml(s) {
    if (s == null) return "";
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function formatKgLabel(s) {
    const acronyms = new Set(["ibd", "ibs", "crc", "uc", "cd", "nafld", "t2d"]);
    return String(s || "")
      .replace(/_/g, " ")
      .split(/\s+/)
      .filter(Boolean)
      .map((word) => {
        const lower = word.toLowerCase();
        if (acronyms.has(lower)) return lower.toUpperCase();
        return word.charAt(0).toUpperCase() + word.slice(1);
      })
      .join(" ");
  }

  function pmidLink(pmid) {
    const id = escapeHtml(pmid);
    return `<a href="https://pubmed.ncbi.nlm.nih.gov/${id}/" target="_blank" rel="noopener" class="text-indigo-600 hover:underline font-mono text-xs">PMID ${id}</a>`;
  }

  function renderEdgeEvidence(edges) {
    if (!edges || !edges.length) {
      return '<p class="text-gray-400 text-xs">No KG edge literature for this node.</p>';
    }
    return edges
      .map((e) => {
        const arrow = e.direction === "outgoing" ? "→" : "←";
        const rel = escapeHtml((e.relation || "related_to").replace(/_/g, " "));
        const desc = e.description ? `<p class="text-gray-600 mt-1">${escapeHtml(e.description)}</p>` : "";
        const pmids = (e.pmids || []).map(pmidLink).join(" · ");
        const meta = [];
        if (e.impact_factor) meta.push(`IF ${e.impact_factor}`);
        if (e.citation_count) meta.push(`${e.citation_count} citations`);
        const metaHtml = meta.length
          ? `<p class="text-gray-400 text-xs mt-1">${meta.join(" · ")}</p>`
          : "";
        return `<div class="border border-gray-100 rounded-lg p-3 mb-2 bg-gray-50/80">
          <p class="font-medium text-gray-800 text-xs">${e.pair_label ? escapeHtml(e.pair_label) : escapeHtml(formatKgLabel(e.neighbor_label)) + ' <span class="text-gray-400">' + arrow + '</span>'}</p>
          <p class="text-xs text-gray-500 mt-0.5">${rel}</p>
          ${desc}
          ${pmids ? `<p class="mt-2 flex flex-wrap gap-2">${pmids}</p>` : '<p class="text-gray-400 text-xs mt-1">No PMID on this edge</p>'}
          ${metaHtml}
        </div>`;
      })
      .join("");
  }

  function renderHopEvidence(hops) {
    if (!hops || !hops.length) return "";
    return `<div class="mb-4">
      <h4 class="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Archived agent evidence</h4>
      ${hops
        .map((h) => {
          const title = HOP_LABELS[h.hop_type] || h.hop_type;
          const sources = (h.sources || [])
            .map((s) => `<li class="text-gray-700">${escapeHtml(s)}</li>`)
            .join("");
          const dbHits = h.db_hits
            ? Object.entries(h.db_hits)
                .filter(([, v]) => v)
                .map(([k]) => k)
                .join(", ")
            : "";
          return `<div class="border-l-4 border-indigo-400 pl-3 mb-3">
            ${h.pair_label ? `<p class="font-semibold text-gray-900 text-sm">${escapeHtml(h.pair_label)}</p>` : ""}
            <p class="font-medium text-gray-800 text-sm">${escapeHtml(title)}</p>
            <p class="text-xs text-gray-500 mt-0.5">PubMed hits: <span class="font-mono">${escapeHtml(h.pubmed_count ?? "Unavailable")}</span>${dbHits ? ` · Database hits: ${escapeHtml(dbHits)}` : ""}</p>
            ${h.query_used ? `<p class="text-xs text-gray-500 mt-1 break-words">Query: <a class="text-indigo-600 hover:underline" href="https://pubmed.ncbi.nlm.nih.gov/?term=${encodeURIComponent(h.query_used)}" target="_blank" rel="noopener">${escapeHtml(h.query_used)}</a></p>` : ""}
            ${sources ? `<ul class="list-disc list-inside text-xs mt-2 space-y-1">${sources}</ul>` : ""}
          </div>`;
        })
        .join("")}
    </div>`;
  }

  function renderArticles(articles) {
    if (!articles || !articles.length) return "";
    return `<div>
      <h4 class="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Linked abstracts</h4>
      ${articles
        .map((a) => {
          const title = escapeHtml(a.title || "(no title)");
          const journal = [a.journal, a.year].filter(Boolean).join(", ");
          const abs = a.abstract
            ? `<p class="text-gray-600 text-xs mt-1 line-clamp-3">${escapeHtml(a.abstract)}</p>`
            : "";
          return `<div class="mb-3 pb-3 border-b border-gray-100 last:border-0">
            <p class="text-sm font-medium text-gray-900">${title}</p>
            <p class="text-xs mt-1">${pmidLink(a.pmid)}${journal ? ` · <span class="text-gray-500">${escapeHtml(journal)}</span>` : ""}</p>
            ${abs}
          </div>`;
        })
        .join("")}
    </div>`;
  }

  function renderPayload(data) {
    const node = data.node || {};
    const typeLabel = escapeHtml(node.type || "?");
    const role = node.core_role ? `<span class="text-emerald-700 font-medium"> · ${escapeHtml(node.core_role)}</span>` : "";
    let html = `<div class="mb-3">
      <p class="text-base font-semibold text-gray-900">${escapeHtml(formatKgLabel(node.label || node.id))}</p>
      <p class="text-xs text-gray-500">${typeLabel}${role}</p>`;
    if (node.description) {
      html += `<p class="text-sm text-gray-600 mt-2">${escapeHtml(node.description)}</p>`;
    }
    if (node.kegg_id) {
      html += `<p class="mt-1"><a href="https://www.kegg.jp/entry/${escapeHtml(node.kegg_id)}" target="_blank" class="text-indigo-600 hover:underline text-xs">KEGG ${escapeHtml(node.kegg_id)}</a></p>`;
    }
    html += `</div>`;

    html += renderHopEvidence(data.hop_evidence);
    html += `<div class="mb-4">
      <h4 class="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">KG edge literature (${(data.edge_evidence || []).length})</h4>
      ${renderEdgeEvidence(data.edge_evidence)}
    </div>`;
    html += renderArticles(data.articles);
    return html;
  }

  async function showNode(nodeId, nodeData) {
    const panel = document.getElementById("kg-evidence-panel");
    const content = document.getElementById("kg-evidence-content");
    if (!panel || !content) return;

    panel.classList.remove("hidden");
    content.innerHTML = '<p class="text-gray-400 text-sm py-2">Loading evidence...</p>';

    const ctx = _getContext() || {};
    const params = new URLSearchParams({
      node_id: nodeId,
      bacteria: ctx.bacteria || "",
      metabolite: ctx.metabolite || "",
      disease: ctx.disease || "IBD",
      node_type: nodeData.type || "",
      core_role: nodeData.core_role || "",
    });
    if (ctx.run_id) params.set("run_id", ctx.run_id);

    try {
      const base = ctx.api_base || "";
      const res = await fetch(`${base}/api/graph/node-evidence?${params}`);
      const data = await res.json();
      if (!res.ok || data.error) throw new Error(data.error || res.statusText);
      content.innerHTML = renderPayload(data);
    } catch (err) {
      content.innerHTML = `<p class="text-red-600 text-sm">${escapeHtml(err.message || "Failed to load evidence")}</p>`;
    }
  }

  function onNodeTap(evt) {
    const node = evt.target;
    if (!node.isNode()) return;
    showNode(node.id(), node.data());
  }

  function bind(cy, getContext) {
    if (!cy) return;
    if (_boundCy && _boundCy !== cy) {
      _boundCy.off("tap", "node", onNodeTap);
    }
    _boundCy = cy;
    _getContext = typeof getContext === "function" ? getContext : () => ({});
    cy.off("tap", "node", onNodeTap);
    cy.on("tap", "node", onNodeTap);
  }

  function clearPanel() {
    const panel = document.getElementById("kg-evidence-panel");
    const content = document.getElementById("kg-evidence-content");
    if (panel) panel.classList.add("hidden");
    if (content) content.innerHTML = "";
  }

  // Reserve the center for the selected candidate. Put each neighbor near the
  // core entities it shares an edge with; type alone says nothing about its role.
  function agentNodePositions(container, graph) {
    const compact = container.clientWidth > 0 && container.clientWidth < 540;
    const width = compact ? 350 : 710;
    const height = compact ? 425 : 370;
    const positions = new Map();
    const anchors = {
      disease: { x: width * .25, y: height * .43 },
      bacteria: { x: width * .65, y: height * .39 },
      metabolite: { x: width * .57, y: height * .74 },
    };
    for (const [role, id] of Object.entries(graph.core)) {
      if (id && anchors[role]) positions.set(id, anchors[role]);
    }

    const neighbors = graph.nodes.map(n => n.data).filter(n => !positions.has(n.id));
    const count = neighbors.length;
    if (!count) return positions;
    // Top and bottom include the corners. Side rows use the intervening space.
    const columns = Math.min(Math.ceil(count / 2), Math.max(2, Math.round(count * (compact ? .24 : .33))));
    const top = Math.min(columns, count);
    const bottom = Math.min(columns, count - top);
    const left = Math.ceil((count - top - bottom) / 2);
    const right = count - top - bottom - left;
    const slots = [];
    for (const [n, y] of [[top, 0], [bottom, height]]) {
      for (let i = 0; i < n; i++) slots.push({ x: n === 1 ? width / 2 : i * width / (n - 1), y });
    }
    for (const [n, x] of [[left, 0], [right, width]]) {
      for (let i = 0; i < n; i++) slots.push({ x, y: (i + 1) * height / (n + 1) });
    }
    const preferences = neighbors.map(node => {
      const linked = new Set();
      for (const { data: edge } of graph.edges) {
        if (edge.source === node.id && positions.has(edge.target)) linked.add(positions.get(edge.target));
        if (edge.target === node.id && positions.has(edge.source)) linked.add(positions.get(edge.source));
      }
      return { node, linked: [...linked] };
    });
    preferences.sort((a, b) => b.linked.length - a.linked.length || a.node.id.localeCompare(b.node.id));
    for (const { node, linked } of preferences) {
      const distance = point => linked.reduce((sum, p) => sum + Math.hypot(point.x - p.x, point.y - p.y), 0);
      let best = 0;
      for (let i = 1; i < slots.length; i++) {
        if (distance(slots[i]) < distance(slots[best])) best = i;
      }
      positions.set(node.id, slots.splice(best, 1)[0]);
    }
    return positions;
  }

  function renderAgentGraph(container, graph) {
    const positions = agentNodePositions(container, graph);
    const colors = { microbe: "#567bb8", metabolite: "#e3a32c", disease: "#ca594c", pathway: "#56a37d", enzyme: "#f97316", receptor: "#06b6d4" };
    const shapes = { microbe: "ellipse", metabolite: "round-rectangle", disease: "hexagon", pathway: "diamond", enzyme: "triangle", receptor: "vee" };
    const nodes = graph.nodes.map(({ data }) => {
      const name = String(data.label || data.id).replace(/_/g, " ");
      return { data: { ...data, label: name.charAt(0).toUpperCase() + name.slice(1) }, position: positions.get(data.id) };
    });
    const labels = new Map(nodes.map(({ data }) => [data.id, data.label]));
    const cy = cytoscape({
      container, elements: [...nodes, ...graph.edges],
      layout: { name: "preset", padding: 18 },
      style: [
        { selector: "node", style: {
          label: "data(label)", width: 29, height: 29,
          shape: el => shapes[el.data("type")] || "ellipse",
          "background-color": el => colors[el.data("type")] || "#929aa6",
          "font-size": 13, color: "#172033", "font-family": "Arial, sans-serif",
          "text-wrap": "wrap", "text-max-width": 107, "text-overflow-wrap": "whitespace",
          "text-valign": "bottom", "text-margin-y": 4,
          "text-background-color": "#f9fafb", "text-background-opacity": .88,
        } },
        { selector: "node[?is_core]", style: {
          width: 48, height: 44, "border-color": "#334368", "border-width": 1.5,
          "font-size": 16, "font-weight": "bold", "text-max-width": 130,
        } },
        { selector: 'node[core_role = "bacteria"]', style: {
          "font-style": "italic", "text-valign": "top", "text-margin-y": -4,
        } },
        { selector: "edge", style: {
          label: el => String(el.data("relation") || "").replace(/_/g, " "),
          width: 1.4, "line-color": "#acbad0", "target-arrow-color": "#99a9c1",
          "curve-style": "bezier", "source-arrow-shape": "none", "target-arrow-shape": "none",
          "arrow-scale": .85, "font-size": 11, color: "#435771", "font-style": "italic",
          "text-background-color": "#f9fafb", "text-background-opacity": .95,
          "text-background-padding": 1.5, "text-rotation": "autorotate",
        } },
        { selector: "edge[?directed]", style: { "target-arrow-shape": "triangle" } },
        { selector: "edge[?is_chain]", style: {
          width: 2, "line-color": "#8499b8", "target-arrow-color": "#8499b8", "font-weight": "bold",
        } },
        { selector: 'edge[evidence_source = "agent"]', style: { "line-style": "dashed" } },
        { selector: "node:selected", style: { "border-width": 3, "border-color": "#312e81" } },
        { selector: "edge:selected", style: { width: 3, "line-color": "#4338ca", "target-arrow-color": "#4338ca" } },
      ],
    });
    let previousWidth = container.clientWidth;
    cy.on("resize", () => {
      if (!container.clientWidth || previousWidth === container.clientWidth) return;
      previousWidth = container.clientWidth;
      const updated = agentNodePositions(container, graph);
      cy.nodes().positions(node => updated.get(node.id()));
      cy.fit(undefined, 18);
    });
    cy.on("tap", "node, edge", event => {
      const panel = document.getElementById("kg-evidence-panel");
      const content = document.getElementById("kg-evidence-content");
      if (!panel || !content) return;
      const item = event.target;
      const data = item.data();
      const isNode = item.isNode();
      const selected = isNode
        ? graph.edges.map(edge => edge.data).filter(edge => edge.source === data.id || edge.target === data.id)
        : [data];
      const pair = edge => labels.get(edge.source) + (edge.directed ? " → " : " – ") + labels.get(edge.target);
      const hops = new Map();
      for (const edge of selected) {
        if (!edge.hop_evidence) continue;
        // Multiple literature relations can carry the same pairwise agent query.
        const key = JSON.stringify([[edge.source, edge.target].sort(), edge.hop_evidence.hop_type]);
        hops.set(key, { ...edge.hop_evidence, pair_label: labels.get(edge.source) + " – " + labels.get(edge.target) });
      }
      const title = isNode ? data.label : pair(data);
      const literature = selected.filter(edge => edge.evidence_source === "gml").map(edge => ({
        ...edge, pair_label: pair(edge),
        pmids: String(edge.pmid || "").split(/[,;\s]+/).filter(id => /^\d+$/.test(id)),
      }));
      let html = '<p class="font-semibold mb-2">' + escapeHtml(title) + '</p>';
      if (isNode && data.type === "publication" && data.description) {
        html += '<p class="text-sm text-gray-700 mb-2">' + escapeHtml(data.description) + '</p>';
      }
      if (literature.length) {
        html += '<h4 class="text-xs font-semibold text-gray-500 uppercase mb-2">Knowledge graph literature</h4>'
          + renderEdgeEvidence(literature);
      }
      html += renderHopEvidence([...hops.values()]);
      if (!literature.length && !hops.size) html += '<p>No archived evidence for this selection.</p>';
      content.innerHTML = html;
      panel.classList.remove("hidden");
    });
    return cy;
  }

  global.KgEvidence = { bind, showNode, clearPanel, renderPayload, renderAgentGraph };
})(typeof window !== "undefined" ? window : global);
