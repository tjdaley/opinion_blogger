import { useState, useRef, useCallback, useMemo, useEffect } from "react";

// ── Utility ─────────────────────────────────────────────────────────────────

const slugify = (text) =>
  text.toLowerCase().replace(/[^a-z0-9\s-]/g, "").replace(/[\s-]+/g, "-").slice(0, 120);

const SAMPLE_DATA = [
  {
    cluster_id: 0, canonical_question: "How much is maximum guideline child support in Texas?",
    subject: "Child Support", member_count: 3, needs_review: true,
    members: [
      { court_opinion_id: 1, question_index: 0, question_text: "What is the highest amount of child support under the Texas Family Code?", case_name: "In re Smith", slug: "smith-child-support" },
      { court_opinion_id: 2, question_index: 0, question_text: "What is the most a parent might have to pay for child support?", case_name: "In re Jones", slug: "jones-support-max" },
      { court_opinion_id: 3, question_index: 1, question_text: "What is maximum guideline child support in Texas?", case_name: "In re Davis", slug: "davis-guidelines" },
    ],
  },
  {
    cluster_id: 1, canonical_question: "Can a court modify child support after the divorce is final?",
    subject: "Child Support", member_count: 2, needs_review: true,
    members: [
      { court_opinion_id: 4, question_index: 0, question_text: "Is it possible to change child support after the decree?", case_name: "In re Taylor", slug: "taylor-modification" },
      { court_opinion_id: 5, question_index: 2, question_text: "When can child support be modified post-divorce?", case_name: "In re Wilson", slug: "wilson-mod-support" },
    ],
  },
  {
    cluster_id: 2, canonical_question: "Does voluntary payment of a debt moot a pending appeal in Texas?",
    subject: "Appeals Process", member_count: 2, needs_review: true,
    members: [
      { court_opinion_id: 131, question_index: 0, question_text: "Does the voluntary payment of delinquent taxes moot a pending foreclosure appeal in Texas?", case_name: "Wylie ISD v. Schuiteman", slug: "wylie-isd-v-schuiteman" },
      { court_opinion_id: 132, question_index: 1, question_text: "Can paying off a judgment kill the other side's appeal?", case_name: "In re Henderson", slug: "henderson-mootness" },
    ],
  },
  {
    cluster_id: 3, canonical_question: "How does a court divide community property in a Texas divorce?",
    subject: "Property Division", member_count: 1, needs_review: true,
    members: [
      { court_opinion_id: 10, question_index: 0, question_text: "How is community property split in a Texas divorce?", case_name: "In re Martinez", slug: "martinez-property" },
    ],
  },
  {
    cluster_id: 4, canonical_question: "What happens to separate property claims if you commingle funds?",
    subject: "Property Division", member_count: 1, needs_review: true,
    members: [
      { court_opinion_id: 11, question_index: 0, question_text: "Does mixing separate and community funds forfeit separate property?", case_name: "In re Nguyen", slug: "nguyen-commingling" },
    ],
  },
];

// ── Icons ───────────────────────────────────────────────────────────────────

const Icon = ({ d, size = 16, className = "" }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth="2" strokeLinecap="round"
    strokeLinejoin="round" className={className}><path d={d} /></svg>
);
const I = {
  upload: "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4 M17 8l-5-5-5 5 M12 3v12",
  clipboard: "M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2 M9 2h6a1 1 0 0 1 1 1v1a1 1 0 0 1-1 1H9a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1z",
  check: "M20 6L9 17l-5-5",
  x: "M18 6L6 18 M6 6l12 12",
  edit: "M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7 M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z",
  merge: "M8 6H5a2 2 0 0 0-2 2v7 M18 6h3a2 2 0 0 1 2 2v7 M12 2v20 M9 18l3 3 3-3",
  trash: "M3 6h18 M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2",
  move: "M5 9l-3 3 3 3 M9 5l3-3 3 3 M15 19l3 3 3-3 M19 9l3 3-3 3 M2 12h20 M12 2v20",
  search: "M11 17.25a6.25 6.25 0 1 1 0-12.5 6.25 6.25 0 0 1 0 12.5z M16 16l4.5 4.5",
  chevDown: "M6 9l6 6 6-6",
  chevRight: "M9 18l6-6-6-6",
  split: "M16 3h5v5 M8 3H3v5 M12 22V8 M21 3l-9 9 M3 3l9 9",
  save: "M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z M17 21v-8H7v8 M7 3v5h8",
  folder: "M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z",
  layers: "M12 2L2 7l10 5 10-5-10-5z M2 17l10 5 10-5 M2 12l10 5 10-5",
  restore: "M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8 M3 3v5h5",
};

// ── Persistent storage helpers ──────────────────────────────────────────────

const STORAGE_KEY = "cluster-editor-autosave";

async function autoSave(clusters, fileName) {
  try {
    if (window.storage && clusters) {
      await window.storage.set(STORAGE_KEY, JSON.stringify({ clusters, fileName, savedAt: Date.now() }));
    }
  } catch (e) { /* silent */ }
}

async function loadAutoSave() {
  try {
    if (window.storage) {
      const result = await window.storage.get(STORAGE_KEY);
      if (result && result.value) return JSON.parse(result.value);
    }
  } catch (e) { /* silent */ }
  return null;
}

async function clearAutoSave() {
  try {
    if (window.storage) await window.storage.delete(STORAGE_KEY);
  } catch (e) { /* silent */ }
}

// ── Main App ────────────────────────────────────────────────────────────────

export default function ClusterEditor() {
  const [clusters, setClusters] = useState(null);
  const [fileName, setFileName] = useState("");
  const [search, setSearch] = useState("");
  const [subjectFilter, setSubjectFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [expandedClusters, setExpandedClusters] = useState(new Set());
  const [selectedMembers, setSelectedMembers] = useState(new Map());
  const [editingQuestion, setEditingQuestion] = useState(null);
  const [editingSubject, setEditingSubject] = useState(null);
  const [showMoveModal, setShowMoveModal] = useState(false);
  const [showMergeModal, setShowMergeModal] = useState(null);
  const [showSubjectMgr, setShowSubjectMgr] = useState(false);
  const [showJsonPreview, setShowJsonPreview] = useState(false);
  const [toast, setToast] = useState(null);
  const [autoSaveStatus, setAutoSaveStatus] = useState(null); // "saved" | "saving" | null
  const [recoveryAvailable, setRecoveryAvailable] = useState(null);
  const [activeTab, setActiveTab] = useState("clusters"); // "clusters" | "subjects"
  const fileRef = useRef();

  // ── Check for auto-saved data on mount ──────────────────────────────────

  useEffect(() => {
    loadAutoSave().then((data) => {
      if (data && data.clusters) {
        setRecoveryAvailable(data);
      }
    });
  }, []);

  // ── Auto-save on every edit ─────────────────────────────────────────────

  useEffect(() => {
    if (!clusters) return;
    setAutoSaveStatus("saving");
    const t = setTimeout(() => {
      autoSave(clusters, fileName).then(() => setAutoSaveStatus("saved"));
    }, 1000); // debounce 1s
    return () => clearTimeout(t);
  }, [clusters, fileName]);

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
        setRecoveryAvailable(null);
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
    setRecoveryAvailable(null);
    showToast("Loaded sample data", "success");
  };

  const handleRecover = () => {
    if (!recoveryAvailable) return;
    setClusters(recoveryAvailable.clusters);
    setFileName(recoveryAvailable.fileName || "recovered.json");
    setExpandedClusters(new Set());
    setSelectedMembers(new Map());
    setRecoveryAvailable(null);
    showToast("Recovered auto-saved session", "success");
  };

  const getExportJson = () => {
    if (!clusters) return "";
    const out = clusters.map((c) => ({ ...c, member_count: c.members.length }));
    return JSON.stringify(out, null, 2);
  };

  const handleCopyToClipboard = async () => {
    const json = getExportJson();
    try {
      await navigator.clipboard.writeText(json);
      showToast("JSON copied to clipboard — paste into a .json file", "success");
    } catch {
      // Fallback: show the JSON in a preview modal for manual copy
      setShowJsonPreview(true);
    }
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
      prev.map((c) => c.cluster_id === clusterId ? { ...c, needs_review: !c.needs_review } : c)
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

  const removeMember = (clusterId, mk) => {
    setClusters((prev) =>
      prev.map((c) => {
        if (c.cluster_id !== clusterId) return c;
        const updated = { ...c, members: c.members.filter((m) => `${m.court_opinion_id}-${m.question_index}` !== mk) };
        updated.member_count = updated.members.length;
        return updated;
      }).filter(c => c.members.length > 0)
    );
  };

  // ── Member selection ──────────────────────────────────────────────────────

  const mKey = (m) => `${m.court_opinion_id}-${m.question_index}`;

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

  // ── Move members ──────────────────────────────────────────────────────────

  const executeMove = (targetClusterId) => {
    setClusters((prev) => {
      let moving = [];
      let updated = prev.map((c) => {
        const sel = selectedMembers.get(c.cluster_id);
        if (!sel || sel.size === 0) return c;
        const kept = [];
        c.members.forEach((m) => { (sel.has(mKey(m)) ? moving : kept).push(m); });
        return { ...c, members: kept, member_count: kept.length };
      });
      updated = updated.map((c) => {
        if (c.cluster_id !== targetClusterId) return c;
        const merged = [...c.members, ...moving];
        return { ...c, members: merged, member_count: merged.length };
      });
      return updated.filter((c) => c.members.length > 0);
    });
    setSelectedMembers(new Map());
    setShowMoveModal(false);
    showToast(`Moved ${totalSelected} question(s)`, "success");
  };

  const splitToNew = () => {
    if (totalSelected === 0) return;
    const newId = Math.max(0, ...clusters.map((c) => c.cluster_id)) + 1;
    let moving = [];
    setClusters((prev) => {
      let updated = prev.map((c) => {
        const sel = selectedMembers.get(c.cluster_id);
        if (!sel || sel.size === 0) return c;
        const kept = [];
        c.members.forEach((m) => { (sel.has(mKey(m)) ? moving : kept).push(m); });
        return { ...c, members: kept, member_count: kept.length };
      }).filter(c => c.members.length > 0);
      updated.push({
        cluster_id: newId, canonical_question: "(new cluster — edit this question)",
        subject: "Uncategorized", member_count: moving.length, needs_review: true, members: moving,
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

  // ── Subject-level operations ──────────────────────────────────────────────

  const renameSubject = (oldName, newName) => {
    if (!newName.trim() || oldName === newName) return;
    setClusters((prev) => prev.map((c) => c.subject === oldName ? { ...c, subject: newName.trim() } : c));
    showToast(`Renamed "${oldName}" → "${newName.trim()}"`, "success");
  };

  const mergeSubjects = (sourceName, targetName) => {
    setClusters((prev) => prev.map((c) => c.subject === sourceName ? { ...c, subject: targetName } : c));
    showToast(`Merged "${sourceName}" into "${targetName}"`, "success");
  };

  const deleteSubjectClusters = (subjectName) => {
    const count = clusters.filter(c => c.subject === subjectName).length;
    setClusters((prev) => prev.filter((c) => c.subject !== subjectName));
    showToast(`Deleted ${count} clusters under "${subjectName}"`, "info");
  };

  // ── Derived data ──────────────────────────────────────────────────────────

  const subjects = useMemo(() => {
    if (!clusters) return [];
    const map = {};
    clusters.forEach((c) => {
      if (!map[c.subject]) map[c.subject] = { name: c.subject, clusterCount: 0, questionCount: 0, approved: 0 };
      map[c.subject].clusterCount++;
      map[c.subject].questionCount += c.members.length;
      if (!c.needs_review) map[c.subject].approved++;
    });
    return Object.values(map).sort((a, b) => a.name.localeCompare(b.name));
  }, [clusters]);

  const subjectNames = useMemo(() => subjects.map(s => s.name), [subjects]);

  const filtered = useMemo(() => {
    if (!clusters) return [];
    return clusters.filter((c) => {
      if (subjectFilter !== "all" && c.subject !== subjectFilter) return false;
      if (statusFilter === "approved" && c.needs_review) return false;
      if (statusFilter === "pending" && !c.needs_review) return false;
      if (search) {
        const q = search.toLowerCase();
        const hit = c.canonical_question.toLowerCase().includes(q) ||
          c.members.some((m) => m.question_text.toLowerCase().includes(q) || m.case_name.toLowerCase().includes(q));
        if (!hit) return false;
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

  // ── Render: Landing ───────────────────────────────────────────────────────

  if (!clusters) {
    return (
      <div style={{ fontFamily: "'IBM Plex Sans', system-ui, sans-serif" }}
        className="min-h-screen bg-stone-950 text-stone-200 flex items-center justify-center">
        <div className="text-center max-w-md px-4">
          <h1 className="text-2xl font-semibold tracking-tight mb-1" style={{ fontFamily: "'IBM Plex Mono', monospace" }}>
            Cluster Review Editor
          </h1>
          <p className="text-sm text-stone-500 mb-8">
            Load cluster_review.json to review, edit, merge, and approve canonical question groups.
          </p>
          <div className="space-y-3">
            <label className="block cursor-pointer">
              <input type="file" accept=".json" onChange={handleFileLoad} ref={fileRef} className="hidden" />
              <div className="px-6 py-4 rounded-lg border-2 border-dashed border-stone-700 hover:border-stone-500 transition-colors">
                <Icon d={I.upload} size={24} className="mx-auto mb-2 text-stone-500" />
                <p className="text-sm font-medium text-stone-300">Load cluster_review.json</p>
                <p className="text-xs text-stone-600 mt-1">Click to select file</p>
              </div>
            </label>
            {recoveryAvailable && (
              <button onClick={handleRecover}
                className="w-full px-4 py-3 rounded-lg border-2 border-amber-700/50 bg-amber-950/30 hover:bg-amber-950/50 transition-colors text-left">
                <div className="flex items-center gap-2">
                  <Icon d={I.restore} size={18} className="text-amber-400" />
                  <div>
                    <p className="text-sm font-medium text-amber-300">Recover auto-saved session</p>
                    <p className="text-xs text-amber-600 mt-0.5">
                      {recoveryAvailable.clusters?.length} clusters · saved {new Date(recoveryAvailable.savedAt).toLocaleString()}
                    </p>
                  </div>
                </div>
              </button>
            )}
            <button onClick={handleLoadSample}
              className="text-xs text-stone-600 hover:text-stone-400 underline underline-offset-2 transition-colors">
              or load sample data to explore
            </button>
          </div>
        </div>
      </div>
    );
  }

  // ── Render: Editor ────────────────────────────────────────────────────────

  return (
    <div style={{ fontFamily: "'IBM Plex Sans', system-ui, sans-serif" }}
      className="min-h-screen bg-stone-950 text-stone-200">

      {toast && (
        <div className={`fixed top-4 right-4 z-50 px-4 py-2 rounded-lg text-sm font-medium shadow-lg
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
              <div className="flex items-center gap-2 mt-0.5">
                <p className="text-xs text-stone-500">{fileName}</p>
                {autoSaveStatus === "saved" && (
                  <span className="text-xs text-emerald-700 flex items-center gap-1">
                    <Icon d={I.save} size={10} />auto-saved
                  </span>
                )}
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button onClick={approveAll}
                className="px-3 py-1.5 text-xs font-medium rounded-md bg-emerald-700/30 text-emerald-400 border border-emerald-700/40 hover:bg-emerald-700/50 transition-colors">
                <Icon d={I.check} size={13} className="inline -mt-0.5 mr-1" />Approve All
              </button>
              <button onClick={() => { setClusters(null); setFileName(""); }}
                className="px-3 py-1.5 text-xs font-medium rounded-md bg-stone-800 text-stone-400 border border-stone-700 hover:bg-stone-700 transition-colors">
                Load New
              </button>
              <button onClick={handleCopyToClipboard}
                className="px-3 py-1.5 text-xs font-medium rounded-md bg-amber-700/30 text-amber-400 border border-amber-700/40 hover:bg-amber-700/50 transition-colors">
                <Icon d={I.clipboard} size={13} className="inline -mt-0.5 mr-1" />Copy JSON
              </button>
            </div>
          </div>

          {/* Stats */}
          <div className="flex items-center gap-4 text-xs text-stone-500 mb-3">
            <span><b className="text-stone-300">{stats.total}</b> clusters</span>
            <span><b className="text-emerald-400">{stats.approved}</b> approved</span>
            <span><b className="text-amber-400">{stats.pending}</b> pending</span>
            <span><b className="text-stone-300">{stats.totalMembers}</b> questions</span>
            <span><b className="text-stone-300">{stats.subjects}</b> subjects</span>
          </div>

          {/* Tabs */}
          <div className="flex items-center gap-4 mb-3 border-b border-stone-800">
            <button onClick={() => setActiveTab("clusters")}
              className={`pb-2 text-xs font-medium border-b-2 transition-colors ${activeTab === "clusters" ? "border-stone-400 text-stone-200" : "border-transparent text-stone-500 hover:text-stone-400"}`}>
              <Icon d={I.layers} size={13} className="inline -mt-0.5 mr-1" />Clusters
            </button>
            <button onClick={() => setActiveTab("subjects")}
              className={`pb-2 text-xs font-medium border-b-2 transition-colors ${activeTab === "subjects" ? "border-stone-400 text-stone-200" : "border-transparent text-stone-500 hover:text-stone-400"}`}>
              <Icon d={I.folder} size={13} className="inline -mt-0.5 mr-1" />Subjects ({subjects.length})
            </button>
          </div>

          {/* Filters (clusters tab only) */}
          {activeTab === "clusters" && (
            <>
              <div className="flex items-center gap-3">
                <div className="relative flex-1 max-w-xs">
                  <Icon d={I.search} size={14} className="absolute left-2.5 top-2 text-stone-600" />
                  <input value={search} onChange={(e) => setSearch(e.target.value)}
                    placeholder="Search questions, cases..."
                    className="w-full pl-8 pr-3 py-1.5 text-xs bg-stone-900 border border-stone-800 rounded-md text-stone-300 placeholder:text-stone-600 focus:outline-none focus:border-stone-600" />
                </div>
                <select value={subjectFilter} onChange={(e) => setSubjectFilter(e.target.value)}
                  className="text-xs bg-stone-900 border border-stone-800 rounded-md px-2 py-1.5 text-stone-300 focus:outline-none focus:border-stone-600">
                  <option value="all">All subjects ({subjects.length})</option>
                  {subjects.map((s) => (
                    <option key={s.name} value={s.name}>{s.name} ({s.clusterCount})</option>
                  ))}
                </select>
                <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}
                  className="text-xs bg-stone-900 border border-stone-800 rounded-md px-2 py-1.5 text-stone-300 focus:outline-none focus:border-stone-600">
                  <option value="all">All statuses</option>
                  <option value="pending">Pending review</option>
                  <option value="approved">Approved</option>
                </select>
                <div className="flex gap-1 ml-auto">
                  <button onClick={expandAll} className="px-2 py-1.5 text-xs text-stone-500 hover:text-stone-300">Expand all</button>
                  <button onClick={collapseAll} className="px-2 py-1.5 text-xs text-stone-500 hover:text-stone-300">Collapse all</button>
                </div>
              </div>

              {totalSelected > 0 && (
                <div className="mt-3 flex items-center gap-2 p-2 rounded-md bg-sky-950/50 border border-sky-800/40">
                  <span className="text-xs text-sky-300 font-medium">{totalSelected} selected</span>
                  <button onClick={() => setShowMoveModal(true)}
                    className="px-2 py-1 text-xs rounded bg-sky-800/40 text-sky-300 hover:bg-sky-800/60">
                    <Icon d={I.move} size={12} className="inline -mt-0.5 mr-1" />Move to cluster
                  </button>
                  <button onClick={splitToNew}
                    className="px-2 py-1 text-xs rounded bg-sky-800/40 text-sky-300 hover:bg-sky-800/60">
                    <Icon d={I.split} size={12} className="inline -mt-0.5 mr-1" />Split to new
                  </button>
                  <button onClick={() => setSelectedMembers(new Map())}
                    className="ml-auto px-2 py-1 text-xs text-stone-500 hover:text-stone-300">Clear</button>
                </div>
              )}
            </>
          )}
        </div>
      </header>

      {/* Main content */}
      <main className="max-w-7xl mx-auto px-4 py-4">

        {/* ── Clusters Tab ──────────────────────────────────────────────── */}
        {activeTab === "clusters" && (
          <div className="space-y-2">
            {filtered.length === 0 && (
              <p className="text-center text-stone-600 py-12 text-sm">No clusters match your filters.</p>
            )}
            {filtered.map((cluster) => (
              <ClusterCard key={cluster.cluster_id} cluster={cluster}
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
                subjects={subjectNames}
                selectedKeys={selectedMembers.get(cluster.cluster_id) || new Set()}
                onToggleMember={(mk) => toggleMemberSelect(cluster.cluster_id, mk)}
                onRemoveMember={(mk) => removeMember(cluster.cluster_id, mk)}
                memberKeyFn={mKey}
                onMerge={() => setShowMergeModal(cluster.cluster_id)}
              />
            ))}
          </div>
        )}

        {/* ── Subjects Tab ─────────────────────────────────────────────── */}
        {activeTab === "subjects" && (
          <SubjectManager
            subjects={subjects}
            allSubjectNames={subjectNames}
            onRename={renameSubject}
            onMerge={mergeSubjects}
            onDelete={deleteSubjectClusters}
            onFilterBySubject={(name) => { setSubjectFilter(name); setActiveTab("clusters"); }}
          />
        )}
      </main>

      {/* Move modal */}
      {showMoveModal && (
        <Modal onClose={() => setShowMoveModal(false)} title="Move selected questions to...">
          <MoveTargetList clusters={clusters} selectedMembers={selectedMembers}
            mKey={mKey} onSelect={executeMove} subjectFilter={subjectFilter} />
        </Modal>
      )}

      {/* Merge modal */}
      {showMergeModal !== null && (
        <Modal onClose={() => setShowMergeModal(null)} title="Merge this cluster into...">
          <p className="text-xs text-stone-500 mb-3">Source cluster will be deleted; members move to target.</p>
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

      {/* JSON Preview modal (fallback if clipboard fails) */}
      {showJsonPreview && (
        <Modal onClose={() => setShowJsonPreview(false)} title="Copy JSON manually">
          <p className="text-xs text-stone-500 mb-2">Clipboard access was blocked. Select all and copy from below:</p>
          <textarea readOnly value={getExportJson()}
            className="w-full h-80 text-xs bg-stone-950 border border-stone-700 rounded-md p-3 text-stone-300 font-mono focus:outline-none"
            onFocus={(e) => e.target.select()} />
        </Modal>
      )}
    </div>
  );
}

// ── Subject Manager Panel ───────────────────────────────────────────────────

function SubjectManager({ subjects, allSubjectNames, onRename, onMerge, onDelete, onFilterBySubject }) {
  const [renaming, setRenaming] = useState(null); // subject name
  const [renameDraft, setRenameDraft] = useState("");
  const [merging, setMerging] = useState(null); // source subject name
  const [confirmDelete, setConfirmDelete] = useState(null);

  return (
    <div className="space-y-1">
      <p className="text-xs text-stone-500 mb-3">
        Manage subjects across all clusters. Renaming a subject updates every cluster under it.
        Merging moves all clusters from one subject into another.
      </p>
      {subjects.map((s) => (
        <div key={s.name} className="flex items-center gap-3 px-4 py-3 rounded-lg border border-stone-800/80 bg-stone-900/50 hover:bg-stone-800/30 transition-colors">
          {renaming === s.name ? (
            <div className="flex items-center gap-2 flex-1">
              <input value={renameDraft} onChange={(e) => setRenameDraft(e.target.value)}
                className="flex-1 px-2 py-1 text-sm bg-stone-800 border border-stone-700 rounded text-stone-200 focus:outline-none focus:border-stone-500"
                autoFocus onKeyDown={(e) => {
                  if (e.key === "Enter") { onRename(s.name, renameDraft); setRenaming(null); }
                  if (e.key === "Escape") setRenaming(null);
                }} />
              <button onClick={() => { onRename(s.name, renameDraft); setRenaming(null); }}
                className="px-2 py-1 text-xs bg-emerald-800/40 text-emerald-400 rounded hover:bg-emerald-800/60">Save</button>
              <button onClick={() => setRenaming(null)}
                className="px-2 py-1 text-xs text-stone-500">Cancel</button>
            </div>
          ) : merging === s.name ? (
            <div className="flex items-center gap-2 flex-1">
              <span className="text-xs text-stone-400">Merge "{s.name}" into:</span>
              <select onChange={(e) => { if (e.target.value) { onMerge(s.name, e.target.value); setMerging(null); } }}
                defaultValue=""
                className="text-xs bg-stone-800 border border-stone-700 rounded px-2 py-1 text-stone-300 focus:outline-none">
                <option value="" disabled>Select target...</option>
                {allSubjectNames.filter(n => n !== s.name).map(n => (
                  <option key={n} value={n}>{n}</option>
                ))}
              </select>
              <button onClick={() => setMerging(null)} className="px-2 py-1 text-xs text-stone-500">Cancel</button>
            </div>
          ) : confirmDelete === s.name ? (
            <div className="flex items-center gap-2 flex-1">
              <span className="text-xs text-red-400">Delete all {s.clusterCount} clusters under "{s.name}"?</span>
              <button onClick={() => { onDelete(s.name); setConfirmDelete(null); }}
                className="px-2 py-1 text-xs bg-red-800/40 text-red-400 rounded hover:bg-red-800/60">Yes, delete</button>
              <button onClick={() => setConfirmDelete(null)}
                className="px-2 py-1 text-xs text-stone-500">Cancel</button>
            </div>
          ) : (
            <>
              <div className="flex-1">
                <button onClick={() => onFilterBySubject(s.name)}
                  className="text-sm font-medium text-stone-200 hover:text-amber-400 transition-colors text-left">
                  {s.name}
                </button>
                <div className="flex items-center gap-3 mt-0.5 text-xs text-stone-600">
                  <span>{s.clusterCount} clusters</span>
                  <span>{s.questionCount} questions</span>
                  <span className="text-emerald-700">{s.approved} approved</span>
                </div>
              </div>
              <div className="flex items-center gap-1">
                <button onClick={() => { setRenaming(s.name); setRenameDraft(s.name); }} title="Rename"
                  className="p-1.5 rounded hover:bg-stone-700 text-stone-500 hover:text-stone-300 transition-colors">
                  <Icon d={I.edit} size={13} />
                </button>
                <button onClick={() => setMerging(s.name)} title="Merge into another subject"
                  className="p-1.5 rounded hover:bg-stone-700 text-stone-500 hover:text-stone-300 transition-colors">
                  <Icon d={I.merge} size={13} />
                </button>
                <button onClick={() => setConfirmDelete(s.name)} title="Delete subject and all its clusters"
                  className="p-1.5 rounded hover:bg-red-900/40 text-stone-500 hover:text-red-400 transition-colors">
                  <Icon d={I.trash} size={13} />
                </button>
              </div>
            </>
          )}
        </div>
      ))}
    </div>
  );
}

// ── Move Target List (with subject grouping) ────────────────────────────────

function MoveTargetList({ clusters, selectedMembers, mKey, onSelect, subjectFilter }) {
  const [filterText, setFilterText] = useState("");

  const eligible = clusters.filter(c => {
    const sel = selectedMembers.get(c.cluster_id);
    if (sel && sel.size === c.members.length) return false; // fully selected
    if (filterText) {
      const q = filterText.toLowerCase();
      return c.canonical_question.toLowerCase().includes(q) || c.subject.toLowerCase().includes(q);
    }
    return true;
  });

  // Group by subject
  const grouped = {};
  eligible.forEach(c => {
    if (!grouped[c.subject]) grouped[c.subject] = [];
    grouped[c.subject].push(c);
  });

  return (
    <div>
      <input value={filterText} onChange={(e) => setFilterText(e.target.value)}
        placeholder="Filter clusters..."
        className="w-full px-3 py-1.5 text-xs bg-stone-900 border border-stone-800 rounded-md text-stone-300 placeholder:text-stone-600 focus:outline-none focus:border-stone-600 mb-3" />
      <div className="space-y-3 max-h-80 overflow-y-auto">
        {Object.keys(grouped).sort().map(subject => (
          <div key={subject}>
            <p className="text-xs font-medium text-stone-500 uppercase tracking-wide mb-1 px-1">{subject}</p>
            <div className="space-y-0.5">
              {grouped[subject].map(c => (
                <button key={c.cluster_id} onClick={() => onSelect(c.cluster_id)}
                  className="w-full text-left px-3 py-2 rounded-md text-xs hover:bg-stone-800 transition-colors">
                  <span className="text-stone-300">{c.canonical_question}</span>
                  <span className="text-stone-600 ml-2">({c.members.length})</span>
                </button>
              ))}
            </div>
          </div>
        ))}
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
  const [draftQ, setDraftQ] = useState(cluster.canonical_question);
  const [draftS, setDraftS] = useState(cluster.subject);

  useEffect(() => { setDraftQ(cluster.canonical_question); }, [cluster.canonical_question]);
  useEffect(() => { setDraftS(cluster.subject); }, [cluster.subject]);

  const borderColor = cluster.needs_review ? "border-l-amber-500/60" : "border-l-emerald-500/60";

  return (
    <div className={`rounded-lg border border-stone-800/80 bg-stone-900/50 border-l-4 ${borderColor} overflow-hidden`}>
      <div className="flex items-start gap-3 px-4 py-3 cursor-pointer hover:bg-stone-800/30 transition-colors"
        onClick={onToggleExpand}>
        <Icon d={expanded ? I.chevDown : I.chevRight} size={14} className="mt-1 text-stone-600 flex-shrink-0" />
        <div className="flex-1 min-w-0">
          {editingQuestion ? (
            <div className="flex gap-2" onClick={(e) => e.stopPropagation()}>
              <input value={draftQ} onChange={(e) => setDraftQ(e.target.value)}
                className="flex-1 px-2 py-1 text-sm bg-stone-800 border border-stone-700 rounded text-stone-200 focus:outline-none focus:border-stone-500"
                autoFocus onKeyDown={(e) => { if (e.key === "Enter") onSaveQuestion(draftQ); if (e.key === "Escape") onCancelEdit(); }} />
              <button onClick={() => onSaveQuestion(draftQ)} className="px-2 py-1 text-xs bg-emerald-800/40 text-emerald-400 rounded hover:bg-emerald-800/60">Save</button>
              <button onClick={onCancelEdit} className="px-2 py-1 text-xs text-stone-500">Cancel</button>
            </div>
          ) : (
            <h3 className="text-sm font-medium text-stone-200 leading-snug pr-2">{cluster.canonical_question}</h3>
          )}
          <div className="flex items-center gap-2 mt-1">
            {editingSubject ? (
              <div className="flex gap-1 items-center" onClick={(e) => e.stopPropagation()}>
                <input value={draftS} onChange={(e) => setDraftS(e.target.value)}
                  list={`sl-${cluster.cluster_id}`}
                  className="px-1.5 py-0.5 text-xs bg-stone-800 border border-stone-700 rounded text-stone-300 focus:outline-none focus:border-stone-500 w-40"
                  autoFocus onKeyDown={(e) => { if (e.key === "Enter") onSaveSubject(draftS); if (e.key === "Escape") onCancelSubjectEdit(); }} />
                <datalist id={`sl-${cluster.cluster_id}`}>{subjects.map((s) => <option key={s} value={s} />)}</datalist>
                <button onClick={() => onSaveSubject(draftS)} className="text-xs text-emerald-400">✓</button>
                <button onClick={onCancelSubjectEdit} className="text-xs text-stone-500">✕</button>
              </div>
            ) : (
              <span className="inline-flex items-center gap-1 px-1.5 py-0.5 text-xs rounded bg-stone-800 text-stone-400 cursor-pointer hover:bg-stone-700"
                onClick={(e) => { e.stopPropagation(); onEditSubject(); }}>
                {cluster.subject}<Icon d={I.edit} size={10} className="opacity-50" />
              </span>
            )}
            <span className="text-xs text-stone-600">{cluster.members.length} q{cluster.members.length !== 1 ? "'s" : ""}</span>
            <span className={`text-xs font-medium ${cluster.needs_review ? "text-amber-500/70" : "text-emerald-500/70"}`}>
              {cluster.needs_review ? "pending" : "approved"}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-1 flex-shrink-0" onClick={(e) => e.stopPropagation()}>
          <button onClick={onEditQuestion} title="Edit question"
            className="p-1.5 rounded hover:bg-stone-700 text-stone-500 hover:text-stone-300 transition-colors">
            <Icon d={I.edit} size={13} />
          </button>
          <button onClick={onToggleApprove} title={cluster.needs_review ? "Approve" : "Unapprove"}
            className={`p-1.5 rounded transition-colors ${cluster.needs_review ? "hover:bg-emerald-900/40 text-stone-500 hover:text-emerald-400" : "bg-emerald-900/30 text-emerald-400 hover:bg-emerald-900/50"}`}>
            <Icon d={I.check} size={13} />
          </button>
          <button onClick={onMerge} title="Merge into another"
            className="p-1.5 rounded hover:bg-stone-700 text-stone-500 hover:text-stone-300 transition-colors">
            <Icon d={I.merge} size={13} />
          </button>
          <button onClick={onDelete} title="Delete"
            className="p-1.5 rounded hover:bg-red-900/40 text-stone-500 hover:text-red-400 transition-colors">
            <Icon d={I.trash} size={13} />
          </button>
        </div>
      </div>
      {expanded && (
        <div className="border-t border-stone-800/60">
          {cluster.members.map((m) => {
            const mk = memberKeyFn(m);
            const isSel = selectedKeys.has(mk);
            return (
              <div key={mk}
                className={`flex items-start gap-3 px-4 py-2.5 text-xs border-b border-stone-800/30 last:border-b-0 transition-colors ${isSel ? "bg-sky-950/30" : "hover:bg-stone-800/20"}`}>
                <input type="checkbox" checked={isSel} onChange={() => onToggleMember(mk)}
                  className="mt-0.5 accent-sky-500 flex-shrink-0 cursor-pointer" />
                <div className="flex-1 min-w-0">
                  <p className="text-stone-300 leading-relaxed">{m.question_text}</p>
                  <p className="text-stone-600 mt-0.5">{m.case_name} · opinion #{m.court_opinion_id}, q[{m.question_index}]</p>
                </div>
                <button onClick={() => onRemoveMember(mk)} title="Remove"
                  className="p-1 rounded text-stone-700 hover:text-red-400 hover:bg-red-900/20 transition-colors flex-shrink-0">
                  <Icon d={I.x} size={12} />
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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={onClose}>
      <div className="bg-stone-900 border border-stone-700 rounded-xl shadow-2xl w-full max-w-lg mx-4 overflow-hidden"
        onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between px-4 py-3 border-b border-stone-800">
          <h2 className="text-sm font-semibold text-stone-200">{title}</h2>
          <button onClick={onClose} className="p-1 rounded hover:bg-stone-700 text-stone-500 hover:text-stone-300">
            <Icon d={I.x} size={16} />
          </button>
        </div>
        <div className="p-4">{children}</div>
      </div>
    </div>
  );
}
