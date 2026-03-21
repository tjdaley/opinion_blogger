import { useState, useRef, useCallback, useMemo, useEffect } from "react";

// ── Utility ─────────────────────────────────────────────────────────────────

const slugify = (text) =>
  text.toLowerCase().replace(/[^a-z0-9\s-]/g, "").replace(/[\s-]+/g, "-").slice(0, 120);

const SAMPLE_DATA = [
  {
    cluster_id: 0,
    canonical_question: "How much is maximum guideline child support in Texas?",
    subject: "Child Support",
    member_count: 3,
    needs_review: true,
    members: [
      { court_opinion_id: 1, question_index: 0, question_text: "What is the highest amount of child support under the Texas Family Code?", case_name: "In re Smith", slug: "smith-child-support" },
      { court_opinion_id: 2, question_index: 0, question_text: "What is the most a parent might have to pay for child support?", case_name: "In re Jones", slug: "jones-support-max" },
      { court_opinion_id: 3, question_index: 1, question_text: "What is maximum guideline child support in Texas?", case_name: "In re Davis", slug: "davis-guidelines" },
    ],
  },
  {
    cluster_id: 1,
    canonical_question: "Can a court modify child support after the divorce is final?",
    subject: "Child Support",
    member_count: 2,
    needs_review: true,
    members: [
      { court_opinion_id: 4, question_index: 0, question_text: "Is it possible to change child support after the decree?", case_name: "In re Taylor", slug: "taylor-modification" },
      { court_opinion_id: 5, question_index: 2, question_text: "When can child support be modified post-divorce?", case_name: "In re Wilson", slug: "wilson-mod-support" },
    ],
  },
  {
    cluster_id: 2,
    canonical_question: "Does voluntary payment of a debt moot a pending appeal in Texas?",
    subject: "Appeals Process",
    member_count: 2,
    needs_review: true,
    members: [
      { court_opinion_id: 131, question_index: 0, question_text: "Does the voluntary payment of delinquent taxes moot a pending foreclosure appeal in Texas?", case_name: "Wylie ISD v. Schuiteman", slug: "wylie-isd-v-schuiteman" },
      { court_opinion_id: 132, question_index: 1, question_text: "Can paying off a judgment kill the other side's appeal?", case_name: "In re Henderson", slug: "henderson-mootness" },
    ],
  },
  {
    cluster_id: 3,
    canonical_question: "How does a court divide community property in a Texas divorce?",
    subject: "Property Division",
    member_count: 1,
    needs_review: true,
    members: [
      { court_opinion_id: 10, question_index: 0, question_text: "How is community property split in a Texas divorce?", case_name: "In re Martinez", slug: "martinez-property" },
    ],
  },
];

// ── Icons (inline SVG to avoid deps) ────────────────────────────────────────

const Icon = ({ d, size = 16, className = "" }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth="2" strokeLinecap="round"
    strokeLinejoin="round" className={className}>
    <path d={d} />
  </svg>
);

const Icons = {
  upload: "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4 M17 8l-5-5-5 5 M12 3v12",
  download: "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4 M7 10l5 5 5-5 M12 15V3",
  check: "M20 6L9 17l-5-5",
  x: "M18 6L6 18 M6 6l12 12",
  edit: "M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7 M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z",
  merge: "M8 6H5a2 2 0 0 0-2 2v7 M18 6h3a2 2 0 0 1 2 2v7 M12 2v20 M9 18l3 3 3-3",
  trash: "M3 6h18 M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2",
  move: "M5 9l-3 3 3 3 M9 5l3-3 3 3 M15 19l3 3 3-3 M19 9l3 3-3 3 M2 12h20 M12 2v20",
  search: "M11 17.25a6.25 6.25 0 1 1 0-12.5 6.25 6.25 0 0 1 0 12.5z M16 16l4.5 4.5",
  chevDown: "M6 9l6 6 6-6",
  chevRight: "M9 18l6-6-6-6",
  filter: "M22 3H2l8 9.46V19l4 2v-8.54L22 3z",
  split: "M16 3h5v5 M8 3H3v5 M12 22V8 M21 3l-9 9 M3 3l9 9",
  grip: "M9 5h0 M9 12h0 M9 19h0 M15 5h0 M15 12h0 M15 19h0",
};

// ── Main App ────────────────────────────────────────────────────────────────

export default function ClusterEditor() {
  const [clusters, setClusters] = useState(null);
  const [fileName, setFileName] = useState("");
  const [search, setSearch] = useState("");
  const [subjectFilter, setSubjectFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [expandedClusters, setExpandedClusters] = useState(new Set());
  const [selectedMembers, setSelectedMembers] = useState(new Map()); // clusterId -> Set<memberKey>
  const [editingQuestion, setEditingQuestion] = useState(null); // clusterId
  const [editingSubject, setEditingSubject] = useState(null);
  const [mergeTarget, setMergeTarget] = useState(null); // { sourceId, targetId }
  const [moveTarget, setMoveTarget] = useState(null); // clusterId to move selected into
  const [showMoveModal, setShowMoveModal] = useState(false);
  const [showMergeModal, setShowMergeModal] = useState(null); // sourceClusterId
  const [toast, setToast] = useState(null);
  const fileRef = useRef();

  const showToast = useCallback((msg, type = "info") => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 2800);
  }, []);

  // ── File I/O ──────────────────────────────────────────────────────────────

  const handleFileLoad = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    setFileName(file.name);
    const reader = new FileReader();
    reader.onload = (ev) => {
      try {
        const data = JSON.parse(ev.target.result);
        setClusters(data);
        setExpandedClusters(new Set());
        setSelectedMembers(new Map());
        showToast(`Loaded ${data.length} clusters`, "success");
      } catch {
        showToast("Invalid JSON file", "error");
      }
    };
    reader.readAsText(file);
  };

  const handleLoadSample = () => {
    setClusters(JSON.parse(JSON.stringify(SAMPLE_DATA)));
    setFileName("sample_data.json");
    setExpandedClusters(new Set());
    setSelectedMembers(new Map());
    showToast("Loaded sample data", "success");
  };

  const handleExport = () => {
    if (!clusters) return;
    const out = clusters.map((c) => ({
      ...c,
      member_count: c.members.length,
    }));
    const blob = new Blob([JSON.stringify(out, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = fileName ? fileName.replace(".json", "_edited.json") : "cluster_review_edited.json";
    a.click();
    URL.revokeObjectURL(url);
    showToast("Exported successfully", "success");
  };

  // ── Cluster operations ────────────────────────────────────────────────────

  const toggleExpand = (id) => {
    setExpandedClusters((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const expandAll = () => setExpandedClusters(new Set((clusters || []).map(c => c.cluster_id)));
  const collapseAll = () => setExpandedClusters(new Set());

  const toggleApprove = (clusterId) => {
    setClusters((prev) =>
      prev.map((c) =>
        c.cluster_id === clusterId ? { ...c, needs_review: !c.needs_review } : c
      )
    );
  };

  const approveAll = () => {
    setClusters((prev) => prev.map((c) => ({ ...c, needs_review: false })));
    showToast("All clusters approved", "success");
  };

  const updateCanonical = (clusterId, question) => {
    setClusters((prev) =>
      prev.map((c) => (c.cluster_id === clusterId ? { ...c, canonical_question: question } : c))
    );
    setEditingQuestion(null);
  };

  const updateSubject = (clusterId, subject) => {
    setClusters((prev) =>
      prev.map((c) => (c.cluster_id === clusterId ? { ...c, subject } : c))
    );
    setEditingSubject(null);
  };

  const deleteCluster = (clusterId) => {
    setClusters((prev) => prev.filter((c) => c.cluster_id !== clusterId));
    showToast("Cluster deleted", "info");
  };

  const removeMember = (clusterId, memberKey) => {
    setClusters((prev) =>
      prev.map((c) => {
        if (c.cluster_id !== clusterId) return c;
        const updated = {
          ...c,
          members: c.members.filter((m) => `${m.court_opinion_id}-${m.question_index}` !== memberKey),
        };
        updated.member_count = updated.members.length;
        return updated;
      }).filter(c => c.members.length > 0)
    );
  };

  // ── Member selection ──────────────────────────────────────────────────────

  const memberKey = (m) => `${m.court_opinion_id}-${m.question_index}`;

  const toggleMemberSelect = (clusterId, mk) => {
    setSelectedMembers((prev) => {
      const next = new Map(prev);
      const set = new Set(next.get(clusterId) || []);
      set.has(mk) ? set.delete(mk) : set.add(mk);
      if (set.size === 0) next.delete(clusterId); else next.set(clusterId, set);
      return next;
    });
  };

  const totalSelected = useMemo(() => {
    let n = 0;
    selectedMembers.forEach((s) => (n += s.size));
    return n;
  }, [selectedMembers]);

  // ── Move selected members to another cluster ─────────────────────────────

  const executeMove = (targetClusterId) => {
    setClusters((prev) => {
      let movingMembers = [];
      // Extract selected members from their source clusters
      let updated = prev.map((c) => {
        const sel = selectedMembers.get(c.cluster_id);
        if (!sel || sel.size === 0) return c;
        const kept = [];
        c.members.forEach((m) => {
          const mk = memberKey(m);
          if (sel.has(mk)) movingMembers.push(m);
          else kept.push(m);
        });
        return { ...c, members: kept, member_count: kept.length };
      });
      // Add to target
      updated = updated.map((c) => {
        if (c.cluster_id !== targetClusterId) return c;
        const merged = [...c.members, ...movingMembers];
        return { ...c, members: merged, member_count: merged.length };
      });
      // Remove empty clusters
      return updated.filter((c) => c.members.length > 0);
    });
    setSelectedMembers(new Map());
    setShowMoveModal(false);
    showToast(`Moved ${totalSelected} question(s)`, "success");
  };

  // ── Create new cluster from selected ──────────────────────────────────────

  const splitToNew = () => {
    if (totalSelected === 0) return;
    const newId = Math.max(...clusters.map((c) => c.cluster_id)) + 1;
    let movingMembers = [];
    setClusters((prev) => {
      let updated = prev.map((c) => {
        const sel = selectedMembers.get(c.cluster_id);
        if (!sel || sel.size === 0) return c;
        const kept = [];
        c.members.forEach((m) => {
          const mk = memberKey(m);
          if (sel.has(mk)) movingMembers.push(m);
          else kept.push(m);
        });
        return { ...c, members: kept, member_count: kept.length };
      });
      updated = updated.filter((c) => c.members.length > 0);
      updated.push({
        cluster_id: newId,
        canonical_question: "(new cluster — edit this question)",
        subject: "Uncategorized",
        member_count: movingMembers.length,
        needs_review: true,
        members: movingMembers,
      });
      return updated;
    });
    setSelectedMembers(new Map());
    setExpandedClusters((prev) => new Set([...prev, newId]));
    showToast(`Created new cluster with ${totalSelected} question(s)`, "success");
  };

  // ── Merge clusters ────────────────────────────────────────────────────────

  const executeMerge = (sourceId, targetId) => {
    setClusters((prev) => {
      const source = prev.find((c) => c.cluster_id === sourceId);
      if (!source) return prev;
      return prev
        .map((c) => {
          if (c.cluster_id === targetId) {
            const merged = [...c.members, ...source.members];
            return { ...c, members: merged, member_count: merged.length };
          }
          return c;
        })
        .filter((c) => c.cluster_id !== sourceId);
    });
    setShowMergeModal(null);
    showToast("Clusters merged", "success");
  };

  // ── Derived data ──────────────────────────────────────────────────────────

  const subjects = useMemo(() => {
    if (!clusters) return [];
    const s = new Set(clusters.map((c) => c.subject));
    return [...s].sort();
  }, [clusters]);

  const filtered = useMemo(() => {
    if (!clusters) return [];
    return clusters.filter((c) => {
      if (subjectFilter !== "all" && c.subject !== subjectFilter) return false;
      if (statusFilter === "approved" && c.needs_review) return false;
      if (statusFilter === "pending" && !c.needs_review) return false;
      if (search) {
        const q = search.toLowerCase();
        const inCanonical = c.canonical_question.toLowerCase().includes(q);
        const inMembers = c.members.some(
          (m) =>
            m.question_text.toLowerCase().includes(q) ||
            m.case_name.toLowerCase().includes(q)
        );
        if (!inCanonical && !inMembers) return false;
      }
      return true;
    });
  }, [clusters, subjectFilter, statusFilter, search]);

  const stats = useMemo(() => {
    if (!clusters) return {};
    return {
      total: clusters.length,
      approved: clusters.filter((c) => !c.needs_review).length,
      pending: clusters.filter((c) => c.needs_review).length,
      totalMembers: clusters.reduce((n, c) => n + c.members.length, 0),
      subjects: new Set(clusters.map((c) => c.subject)).size,
    };
  }, [clusters]);

  // ── Render ────────────────────────────────────────────────────────────────

  if (!clusters) return <LandingScreen onLoad={handleFileLoad} onSample={handleLoadSample} fileRef={fileRef} />;

  return (
    <div style={{ fontFamily: "'IBM Plex Sans', 'SF Pro Text', system-ui, sans-serif" }}
      className="min-h-screen bg-stone-950 text-stone-200">

      {/* Toast */}
      {toast && (
        <div className={`fixed top-4 right-4 z-50 px-4 py-2 rounded-lg text-sm font-medium shadow-lg transition-all
          ${toast.type === "success" ? "bg-emerald-600 text-white" :
            toast.type === "error" ? "bg-red-600 text-white" : "bg-stone-700 text-stone-100"}`}>
          {toast.msg}
        </div>
      )}

      {/* Header */}
      <header className="sticky top-0 z-40 border-b border-stone-800 bg-stone-950/95 backdrop-blur-sm">
        <div className="max-w-7xl mx-auto px-4 py-3">
          <div className="flex items-center justify-between mb-3">
            <div>
              <h1 className="text-lg font-semibold tracking-tight text-stone-100"
                style={{ fontFamily: "'IBM Plex Mono', monospace" }}>
                Cluster Review Editor
              </h1>
              <p className="text-xs text-stone-500 mt-0.5">{fileName}</p>
            </div>
            <div className="flex items-center gap-2">
              <button onClick={approveAll}
                className="px-3 py-1.5 text-xs font-medium rounded-md bg-emerald-700/30 text-emerald-400 border border-emerald-700/40 hover:bg-emerald-700/50 transition-colors">
                <Icon d={Icons.check} size={13} className="inline -mt-0.5 mr-1" />
                Approve All
              </button>
              <button onClick={() => { setClusters(null); setFileName(""); }}
                className="px-3 py-1.5 text-xs font-medium rounded-md bg-stone-800 text-stone-400 border border-stone-700 hover:bg-stone-700 transition-colors">
                Load New
              </button>
              <button onClick={handleExport}
                className="px-3 py-1.5 text-xs font-medium rounded-md bg-amber-700/30 text-amber-400 border border-amber-700/40 hover:bg-amber-700/50 transition-colors">
                <Icon d={Icons.download} size={13} className="inline -mt-0.5 mr-1" />
                Export JSON
              </button>
            </div>
          </div>

          {/* Stats bar */}
          <div className="flex items-center gap-4 text-xs text-stone-500 mb-3">
            <span><b className="text-stone-300">{stats.total}</b> clusters</span>
            <span><b className="text-emerald-400">{stats.approved}</b> approved</span>
            <span><b className="text-amber-400">{stats.pending}</b> pending</span>
            <span><b className="text-stone-300">{stats.totalMembers}</b> questions</span>
            <span><b className="text-stone-300">{stats.subjects}</b> subjects</span>
          </div>

          {/* Filters */}
          <div className="flex items-center gap-3">
            <div className="relative flex-1 max-w-xs">
              <Icon d={Icons.search} size={14} className="absolute left-2.5 top-2 text-stone-600" />
              <input value={search} onChange={(e) => setSearch(e.target.value)}
                placeholder="Search questions, cases..."
                className="w-full pl-8 pr-3 py-1.5 text-xs bg-stone-900 border border-stone-800 rounded-md text-stone-300 placeholder:text-stone-600 focus:outline-none focus:border-stone-600" />
            </div>
            <select value={subjectFilter} onChange={(e) => setSubjectFilter(e.target.value)}
              className="text-xs bg-stone-900 border border-stone-800 rounded-md px-2 py-1.5 text-stone-300 focus:outline-none focus:border-stone-600">
              <option value="all">All subjects ({subjects.length})</option>
              {subjects.map((s) => (
                <option key={s} value={s}>{s} ({clusters.filter(c => c.subject === s).length})</option>
              ))}
            </select>
            <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}
              className="text-xs bg-stone-900 border border-stone-800 rounded-md px-2 py-1.5 text-stone-300 focus:outline-none focus:border-stone-600">
              <option value="all">All statuses</option>
              <option value="pending">Pending review</option>
              <option value="approved">Approved</option>
            </select>
            <div className="flex gap-1 ml-auto">
              <button onClick={expandAll}
                className="px-2 py-1.5 text-xs text-stone-500 hover:text-stone-300 transition-colors">
                Expand all
              </button>
              <button onClick={collapseAll}
                className="px-2 py-1.5 text-xs text-stone-500 hover:text-stone-300 transition-colors">
                Collapse all
              </button>
            </div>
          </div>

          {/* Selection toolbar */}
          {totalSelected > 0 && (
            <div className="mt-3 flex items-center gap-2 p-2 rounded-md bg-sky-950/50 border border-sky-800/40">
              <span className="text-xs text-sky-300 font-medium">{totalSelected} selected</span>
              <button onClick={() => setShowMoveModal(true)}
                className="px-2 py-1 text-xs rounded bg-sky-800/40 text-sky-300 hover:bg-sky-800/60 transition-colors">
                <Icon d={Icons.move} size={12} className="inline -mt-0.5 mr-1" />Move to cluster
              </button>
              <button onClick={splitToNew}
                className="px-2 py-1 text-xs rounded bg-sky-800/40 text-sky-300 hover:bg-sky-800/60 transition-colors">
                <Icon d={Icons.split} size={12} className="inline -mt-0.5 mr-1" />Split to new cluster
              </button>
              <button onClick={() => setSelectedMembers(new Map())}
                className="ml-auto px-2 py-1 text-xs rounded text-stone-500 hover:text-stone-300 transition-colors">
                Clear selection
              </button>
            </div>
          )}
        </div>
      </header>

      {/* Clusters list */}
      <main className="max-w-7xl mx-auto px-4 py-4 space-y-2">
        {filtered.length === 0 && (
          <p className="text-center text-stone-600 py-12 text-sm">No clusters match your filters.</p>
        )}
        {filtered.map((cluster) => (
          <ClusterCard
            key={cluster.cluster_id}
            cluster={cluster}
            expanded={expandedClusters.has(cluster.cluster_id)}
            onToggleExpand={() => toggleExpand(cluster.cluster_id)}
            onToggleApprove={() => toggleApprove(cluster.cluster_id)}
            onDelete={() => deleteCluster(cluster.cluster_id)}
            editingQuestion={editingQuestion === cluster.cluster_id}
            onEditQuestion={() => setEditingQuestion(cluster.cluster_id)}
            onSaveQuestion={(q) => updateCanonical(cluster.cluster_id, q)}
            onCancelEdit={() => setEditingQuestion(null)}
            editingSubject={editingSubject === cluster.cluster_id}
            onEditSubject={() => setEditingSubject(cluster.cluster_id)}
            onSaveSubject={(s) => updateSubject(cluster.cluster_id, s)}
            onCancelSubjectEdit={() => setEditingSubject(null)}
            subjects={subjects}
            selectedKeys={selectedMembers.get(cluster.cluster_id) || new Set()}
            onToggleMember={(mk) => toggleMemberSelect(cluster.cluster_id, mk)}
            onRemoveMember={(mk) => removeMember(cluster.cluster_id, mk)}
            memberKeyFn={memberKey}
            onMerge={() => setShowMergeModal(cluster.cluster_id)}
          />
        ))}
      </main>

      {/* Move modal */}
      {showMoveModal && (
        <Modal onClose={() => setShowMoveModal(false)} title="Move selected questions to...">
          <div className="space-y-1 max-h-80 overflow-y-auto">
            {clusters.filter(c => {
              // Don't show clusters that are entirely selected
              const sel = selectedMembers.get(c.cluster_id);
              return !(sel && sel.size === c.members.length);
            }).map((c) => (
              <button key={c.cluster_id} onClick={() => executeMove(c.cluster_id)}
                className="w-full text-left px-3 py-2 rounded-md text-xs hover:bg-stone-800 transition-colors">
                <span className="text-stone-300">{c.canonical_question}</span>
                <span className="text-stone-600 ml-2">({c.subject} · {c.members.length})</span>
              </button>
            ))}
          </div>
        </Modal>
      )}

      {/* Merge modal */}
      {showMergeModal !== null && (
        <Modal onClose={() => setShowMergeModal(null)} title="Merge this cluster into...">
          <p className="text-xs text-stone-500 mb-3">
            The source cluster will be deleted and its members added to the target.
          </p>
          <div className="space-y-1 max-h-80 overflow-y-auto">
            {clusters.filter((c) => c.cluster_id !== showMergeModal).map((c) => (
              <button key={c.cluster_id} onClick={() => executeMerge(showMergeModal, c.cluster_id)}
                className="w-full text-left px-3 py-2 rounded-md text-xs hover:bg-stone-800 transition-colors">
                <span className="text-stone-300">{c.canonical_question}</span>
                <span className="text-stone-600 ml-2">({c.subject} · {c.members.length})</span>
              </button>
            ))}
          </div>
        </Modal>
      )}
    </div>
  );
}

// ── Landing Screen ──────────────────────────────────────────────────────────

function LandingScreen({ onLoad, onSample, fileRef }) {
  return (
    <div style={{ fontFamily: "'IBM Plex Sans', 'SF Pro Text', system-ui, sans-serif" }}
      className="min-h-screen bg-stone-950 text-stone-200 flex items-center justify-center">
      <div className="text-center max-w-md">
        <h1 className="text-2xl font-semibold tracking-tight mb-2"
          style={{ fontFamily: "'IBM Plex Mono', monospace" }}>
          Cluster Review Editor
        </h1>
        <p className="text-sm text-stone-500 mb-8">
          Load the cluster_review.json from the clustering pipeline to review,
          edit, merge, and approve canonical question groups.
        </p>
        <div className="space-y-3">
          <label className="block cursor-pointer">
            <input type="file" accept=".json" onChange={onLoad} ref={fileRef} className="hidden" />
            <div className="px-6 py-4 rounded-lg border-2 border-dashed border-stone-700 hover:border-stone-500 transition-colors">
              <Icon d={Icons.upload} size={24} className="mx-auto mb-2 text-stone-500" />
              <p className="text-sm font-medium text-stone-300">Load cluster_review.json</p>
              <p className="text-xs text-stone-600 mt-1">Drop or click to select</p>
            </div>
          </label>
          <button onClick={onSample}
            className="text-xs text-stone-600 hover:text-stone-400 underline underline-offset-2 transition-colors">
            or load sample data to explore
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Cluster Card ────────────────────────────────────────────────────────────

function ClusterCard({
  cluster, expanded, onToggleExpand, onToggleApprove, onDelete,
  editingQuestion, onEditQuestion, onSaveQuestion, onCancelEdit,
  editingSubject, onEditSubject, onSaveSubject, onCancelSubjectEdit,
  subjects, selectedKeys, onToggleMember, onRemoveMember, memberKeyFn, onMerge,
}) {
  const [draftQuestion, setDraftQuestion] = useState(cluster.canonical_question);
  const [draftSubject, setDraftSubject] = useState(cluster.subject);

  useEffect(() => { setDraftQuestion(cluster.canonical_question); }, [cluster.canonical_question]);
  useEffect(() => { setDraftSubject(cluster.subject); }, [cluster.subject]);

  const statusColor = cluster.needs_review
    ? "border-l-amber-500/60"
    : "border-l-emerald-500/60";

  return (
    <div className={`rounded-lg border border-stone-800/80 bg-stone-900/50 border-l-4 ${statusColor} overflow-hidden`}>
      {/* Header row */}
      <div className="flex items-start gap-3 px-4 py-3 cursor-pointer hover:bg-stone-800/30 transition-colors"
        onClick={onToggleExpand}>
        <Icon d={expanded ? Icons.chevDown : Icons.chevRight} size={14}
          className="mt-1 text-stone-600 flex-shrink-0" />

        <div className="flex-1 min-w-0">
          {/* Canonical question */}
          {editingQuestion ? (
            <div className="flex gap-2" onClick={(e) => e.stopPropagation()}>
              <input value={draftQuestion} onChange={(e) => setDraftQuestion(e.target.value)}
                className="flex-1 px-2 py-1 text-sm bg-stone-800 border border-stone-700 rounded text-stone-200 focus:outline-none focus:border-stone-500"
                autoFocus onKeyDown={(e) => { if (e.key === "Enter") onSaveQuestion(draftQuestion); if (e.key === "Escape") onCancelEdit(); }} />
              <button onClick={() => onSaveQuestion(draftQuestion)}
                className="px-2 py-1 text-xs bg-emerald-800/40 text-emerald-400 rounded hover:bg-emerald-800/60">Save</button>
              <button onClick={onCancelEdit}
                className="px-2 py-1 text-xs text-stone-500 hover:text-stone-300">Cancel</button>
            </div>
          ) : (
            <h3 className="text-sm font-medium text-stone-200 leading-snug pr-2">
              {cluster.canonical_question}
            </h3>
          )}

          {/* Subject + meta */}
          <div className="flex items-center gap-2 mt-1">
            {editingSubject ? (
              <div className="flex gap-1 items-center" onClick={(e) => e.stopPropagation()}>
                <input value={draftSubject} onChange={(e) => setDraftSubject(e.target.value)}
                  list={`subj-list-${cluster.cluster_id}`}
                  className="px-1.5 py-0.5 text-xs bg-stone-800 border border-stone-700 rounded text-stone-300 focus:outline-none focus:border-stone-500 w-40"
                  autoFocus onKeyDown={(e) => { if (e.key === "Enter") onSaveSubject(draftSubject); if (e.key === "Escape") onCancelSubjectEdit(); }} />
                <datalist id={`subj-list-${cluster.cluster_id}`}>
                  {subjects.map((s) => <option key={s} value={s} />)}
                </datalist>
                <button onClick={() => onSaveSubject(draftSubject)}
                  className="text-xs text-emerald-400 hover:text-emerald-300">✓</button>
                <button onClick={onCancelSubjectEdit}
                  className="text-xs text-stone-500 hover:text-stone-300">✕</button>
              </div>
            ) : (
              <span className="inline-flex items-center gap-1 px-1.5 py-0.5 text-xs rounded bg-stone-800 text-stone-400 cursor-pointer hover:bg-stone-700"
                onClick={(e) => { e.stopPropagation(); onEditSubject(); }}>
                {cluster.subject}
                <Icon d={Icons.edit} size={10} className="opacity-50" />
              </span>
            )}
            <span className="text-xs text-stone-600">{cluster.members.length} question{cluster.members.length !== 1 ? "s" : ""}</span>
            <span className={`text-xs font-medium ${cluster.needs_review ? "text-amber-500/70" : "text-emerald-500/70"}`}>
              {cluster.needs_review ? "pending" : "approved"}
            </span>
          </div>
        </div>

        {/* Action buttons */}
        <div className="flex items-center gap-1 flex-shrink-0" onClick={(e) => e.stopPropagation()}>
          <button onClick={onEditQuestion} title="Edit question"
            className="p-1.5 rounded hover:bg-stone-700 text-stone-500 hover:text-stone-300 transition-colors">
            <Icon d={Icons.edit} size={13} />
          </button>
          <button onClick={onToggleApprove} title={cluster.needs_review ? "Approve" : "Unapprove"}
            className={`p-1.5 rounded transition-colors ${cluster.needs_review ? "hover:bg-emerald-900/40 text-stone-500 hover:text-emerald-400" : "bg-emerald-900/30 text-emerald-400 hover:bg-emerald-900/50"}`}>
            <Icon d={Icons.check} size={13} />
          </button>
          <button onClick={onMerge} title="Merge into another cluster"
            className="p-1.5 rounded hover:bg-stone-700 text-stone-500 hover:text-stone-300 transition-colors">
            <Icon d={Icons.merge} size={13} />
          </button>
          <button onClick={onDelete} title="Delete cluster"
            className="p-1.5 rounded hover:bg-red-900/40 text-stone-500 hover:text-red-400 transition-colors">
            <Icon d={Icons.trash} size={13} />
          </button>
        </div>
      </div>

      {/* Expanded member list */}
      {expanded && (
        <div className="border-t border-stone-800/60">
          {cluster.members.map((m) => {
            const mk = memberKeyFn(m);
            const isSelected = selectedKeys.has(mk);
            return (
              <div key={mk}
                className={`flex items-start gap-3 px-4 py-2.5 text-xs border-b border-stone-800/30 last:border-b-0 transition-colors
                  ${isSelected ? "bg-sky-950/30" : "hover:bg-stone-800/20"}`}>
                <input type="checkbox" checked={isSelected}
                  onChange={() => onToggleMember(mk)}
                  className="mt-0.5 accent-sky-500 flex-shrink-0 cursor-pointer" />
                <div className="flex-1 min-w-0">
                  <p className="text-stone-300 leading-relaxed">{m.question_text}</p>
                  <p className="text-stone-600 mt-0.5">
                    {m.case_name}
                    <span className="mx-1.5">·</span>
                    opinion #{m.court_opinion_id}, q[{m.question_index}]
                  </p>
                </div>
                <button onClick={() => onRemoveMember(mk)} title="Remove from cluster"
                  className="p-1 rounded text-stone-700 hover:text-red-400 hover:bg-red-900/20 transition-colors flex-shrink-0">
                  <Icon d={Icons.x} size={12} />
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ── Modal ───────────────────────────────────────────────────────────────────

function Modal({ onClose, title, children }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={onClose}>
      <div className="bg-stone-900 border border-stone-700 rounded-xl shadow-2xl w-full max-w-lg mx-4 overflow-hidden"
        onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between px-4 py-3 border-b border-stone-800">
          <h2 className="text-sm font-semibold text-stone-200">{title}</h2>
          <button onClick={onClose} className="p-1 rounded hover:bg-stone-700 text-stone-500 hover:text-stone-300">
            <Icon d={Icons.x} size={16} />
          </button>
        </div>
        <div className="p-4">{children}</div>
      </div>
    </div>
  );
}
